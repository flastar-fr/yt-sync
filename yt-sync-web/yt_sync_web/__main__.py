"""FastAPI web dashboard for folder-scoped YouTube playlist synchronization."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from yt_sync_core.diff_engine import DiffEngine, DiffResult
from yt_sync_core.exceptions import ExtractionError, StorageError, YtSyncError
from yt_sync_core.extractor import PlaylistExtractor, RemoteTrack
from yt_sync_core.models import SyncConfig, SyncState, TrackSnapshot, TrackStatus
from yt_sync_core.storage import STATE_FILENAME, StateManager

app = FastAPI(
    title="yt-sync web",
    description="Folder-scoped web dashboard for YouTube playlist synchronization",
)

# Template setup
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Initialize default target_dir from environment variable if present
_env_target = os.environ.get("YT_SYNC_TARGET_DIR")
app.state.target_dir = Path(_env_target).resolve() if _env_target else None


# ---------------------------------------------------------------------------
# View Models & Helpers
# ---------------------------------------------------------------------------


@dataclass
class TrackViewItem:
    """Formatted item for dashboard tracklist presentation."""

    video_id: str
    title: str
    status: str  # 'downloaded', 'new', 'unavailable', 'removed', 'skipped'
    original_title: str | None = None
    error_message: str | None = None
    can_ignore: bool = False
    trim_start: str | None = None
    trim_end: str | None = None


def _get_target_dir(request: Request) -> Path:
    """Retrieve and validate the target directory from application state."""
    target_dir: Path | None = getattr(request.app.state, "target_dir", None)
    if target_dir is None:
        raise HTTPException(
            status_code=500,
            detail="No target directory configured. Start the server with a target folder argument.",
        )
    return target_dir


def _build_dashboard_context(
    state: SyncState,
    target_dir: Path,
    diff: DiffResult | None = None,
) -> dict[str, Any]:
    """Build unified context dictionary for dashboard rendering."""
    tracks: list[TrackViewItem] = []

    if diff is not None:
        # Build view items from differential analysis
        for t in diff.new_tracks:
            snap = state.tracks.get(t.video_id)
            tracks.append(
                TrackViewItem(
                    video_id=t.video_id,
                    title=t.title,
                    status="new",
                    trim_start=snap.trim_start if snap else None,
                    trim_end=snap.trim_end if snap else None,
                )
            )

        for t in diff.unavailable_tracks:
            tracks.append(
                TrackViewItem(
                    video_id=t.video_id,
                    title=t.title,
                    status="unavailable",
                    original_title=t.title,
                    error_message=t.error_message or "Unavailable on YouTube",
                    can_ignore=True,
                    trim_start=t.trim_start,
                    trim_end=t.trim_end,
                )
            )

        for t in diff.removed_tracks:
            tracks.append(
                TrackViewItem(
                    video_id=t.video_id,
                    title=t.title,
                    status="removed",
                    original_title=t.title,
                    trim_start=t.trim_start,
                    trim_end=t.trim_end,
                )
            )

        for t in diff.already_downloaded:
            status_str = "skipped" if t.status == TrackStatus.SKIPPED else "downloaded"
            tracks.append(
                TrackViewItem(
                    video_id=t.video_id,
                    title=t.title,
                    status=status_str,
                    trim_start=t.trim_start,
                    trim_end=t.trim_end,
                )
            )

        total_count = diff.total_count
        downloaded_count = len(diff.already_downloaded)
        new_count = len(diff.new_tracks)
        unavailable_count = len(diff.unavailable_tracks)

    else:
        # Build view items from local state (zero network calls)
        for snapshot in state.tracks.values():
            if snapshot.status == TrackStatus.DOWNLOADED:
                status_str = "downloaded"
            elif snapshot.status == TrackStatus.PENDING:
                status_str = "new"
            elif snapshot.status == TrackStatus.SKIPPED:
                status_str = "skipped"
            elif snapshot.status == TrackStatus.ERROR:
                status_str = "unavailable"
            else:
                status_str = "downloaded"

            tracks.append(
                TrackViewItem(
                    video_id=snapshot.video_id,
                    title=snapshot.title,
                    status=status_str,
                    original_title=snapshot.title if status_str == "unavailable" else None,
                    error_message=snapshot.error_message,
                    can_ignore=(status_str == "unavailable"),
                    trim_start=snapshot.trim_start,
                    trim_end=snapshot.trim_end,
                )
            )

        total_count = len(state.tracks)
        downloaded_count = sum(
            1 for t in state.tracks.values() if t.status in (TrackStatus.DOWNLOADED, TrackStatus.SKIPPED)
        )
        new_count = sum(1 for t in state.tracks.values() if t.status == TrackStatus.PENDING)
        unavailable_count = sum(1 for t in state.tracks.values() if t.status == TrackStatus.ERROR)

    return {
        "playlist_name": state.playlist_name or "YouTube Playlist",
        "playlist_url": state.playlist_url or "",
        "target_dir": str(target_dir),
        "last_synced_at": state.last_synced_at,
        "total_count": total_count,
        "downloaded_count": downloaded_count,
        "new_count": new_count,
        "unavailable_count": unavailable_count,
        "tracks": tracks,
        "normalize_audio": state.config.normalize_audio,
        "target_lufs": state.config.target_lufs,
        "true_peak": state.config.true_peak,
        "audio_format": state.config.audio_format,
        "audio_quality": state.config.audio_quality,
        "enable_sponsorblock": state.config.enable_sponsorblock,
        "cookies_browser": state.config.cookies_browser,
        "cookies_file": state.config.cookies_file,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request) -> HTMLResponse:
    """Render home layout.

    If .yt_sync_state.json exists, loads local state with ZERO network calls.
    Otherwise, displays the initialization screen to enter playlist URL.
    """
    target_dir = getattr(request.app.state, "target_dir", None)
    if target_dir is None:
        target_dir = Path.cwd().resolve()
        request.app.state.target_dir = target_dir

    target_dir.mkdir(parents=True, exist_ok=True)
    state_file = target_dir / STATE_FILENAME

    if not state_file.exists():
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "init_needed": True,
                "target_dir": str(target_dir),
            },
        )

    state_manager = StateManager(target_dir=target_dir)
    try:
        current_state = state_manager.load()
    except StorageError as exc:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "init_needed": True,
                "target_dir": str(target_dir),
                "error_message": f"Could not read state file: {exc}",
            },
        )

    if not current_state.playlist_url and not current_state.tracks:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "init_needed": True,
                "target_dir": str(target_dir),
            },
        )

    context = _build_dashboard_context(current_state, target_dir)
    context["init_needed"] = False
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context=context,
    )


@app.post("/initialize", response_class=HTMLResponse)
async def post_initialize(
    request: Request,
    playlist_url: str = Form(...),
    normalize_audio: str | None = Form(default=None),
    audio_format: str | None = Form(default=None),
    enable_sponsorblock: str | None = Form(default=None),
    cookies_browser: str | None = Form(default=None),
    cookies_file: str | None = Form(default=None),
    init_form: str | None = Form(default=None),
) -> HTMLResponse:
    """Initialize state for target directory by querying remote playlist metadata."""
    target_dir = _get_target_dir(request)
    target_dir.mkdir(parents=True, exist_ok=True)
    state_manager = StateManager(target_dir=target_dir)

    if init_form is not None:
        should_normalize = (
            normalize_audio is not None
            and normalize_audio.lower() in ("true", "1", "on")
        )
        should_sponsorblock = (
            enable_sponsorblock is not None
            and enable_sponsorblock.lower() in ("true", "1", "on")
        )
    elif normalize_audio is not None:
        should_normalize = normalize_audio.lower() in ("true", "1", "on")
        should_sponsorblock = (
            enable_sponsorblock.lower() in ("true", "1", "on")
            if enable_sponsorblock is not None
            else True
        )
    else:
        should_normalize = True
        should_sponsorblock = True

    should_format = audio_format if audio_format in ("m4a", "mp3") else "m4a"

    clean_cookies_browser = (
        cookies_browser.strip()
        if cookies_browser and cookies_browser.strip() not in ("none", "None", "")
        else None
    )
    clean_cookies_file = (
        cookies_file.strip()
        if cookies_file and cookies_file.strip()
        else None
    )

    extractor = PlaylistExtractor(
        normalize_audio=should_normalize,
        audio_format=should_format,
        enable_sponsorblock=should_sponsorblock,
        cookies_browser=clean_cookies_browser,
        cookies_file=clean_cookies_file,
    )
    try:
        # Offload yt-dlp metadata extraction to thread pool
        title, remote_tracks = await asyncio.to_thread(
            extractor.fetch_playlist_details, playlist_url
        )
    except Exception as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/error.html",
            context={"error_message": f"Failed to retrieve playlist info: {exc}"},
        )

    # Compute initial diff against empty state
    diff_engine = DiffEngine()
    diff = diff_engine.compute(remote_tracks=remote_tracks, current_state=SyncState())

    # Build initial state with pending tracks
    initial_tracks: dict[str, TrackSnapshot] = {}
    for track in remote_tracks:
        if track.is_available:
            initial_tracks[track.video_id] = TrackSnapshot(
                video_id=track.video_id,
                title=track.title,
                status=TrackStatus.PENDING,
            )
        else:
            initial_tracks[track.video_id] = TrackSnapshot(
                video_id=track.video_id,
                title=track.title,
                status=TrackStatus.ERROR,
                error_message="Unavailable on YouTube",
            )

    new_state = SyncState(
        playlist_url=playlist_url,
        playlist_name=title,
        last_synced_at=None,
        tracks=initial_tracks,
        config=SyncConfig(
            normalize_audio=should_normalize,
            audio_format=should_format,
            enable_sponsorblock=should_sponsorblock,
            cookies_browser=clean_cookies_browser,
            cookies_file=clean_cookies_file,
        ),
    )

    try:
        state_manager.save(new_state)
    except StorageError as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/error.html",
            context={"error_message": f"Failed to save state file: {exc}"},
        )

    context = _build_dashboard_context(new_state, target_dir, diff=diff)
    return templates.TemplateResponse(
        request=request,
        name="fragments/dashboard.html",
        context=context,
    )


@app.post("/refresh", response_class=HTMLResponse)
async def post_refresh(request: Request) -> HTMLResponse:
    """Manual polling (Anti-quota burn): checks remote playlist for updates."""
    target_dir = _get_target_dir(request)
    state_manager = StateManager(target_dir=target_dir)

    try:
        current_state = state_manager.load()
    except StorageError as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/error.html",
            context={"error_message": f"Could not load state: {exc}"},
        )

    if not current_state.playlist_url:
        return templates.TemplateResponse(
            request=request,
            name="fragments/error.html",
            context={"error_message": "No playlist URL linked to this folder."},
        )

    extractor = PlaylistExtractor(
        config=current_state.config,
    )
    diff_engine = DiffEngine()

    try:
        # Offload yt-dlp network extraction to thread pool
        title, remote_tracks = await asyncio.to_thread(
            extractor.fetch_playlist_details, current_state.playlist_url
        )
    except Exception as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/error.html",
            context={"error_message": f"Failed to refresh playlist: {exc}"},
        )

    diff = diff_engine.compute(remote_tracks=remote_tracks, current_state=current_state)

    # Update playlist title if updated
    if title and title != current_state.playlist_name:
        updated_state = SyncState(
            playlist_url=current_state.playlist_url,
            playlist_name=title,
            last_synced_at=current_state.last_synced_at,
            tracks=current_state.tracks,
            config=current_state.config,
        )
        try:
            state_manager.save(updated_state)
            current_state = updated_state
        except StorageError:
            pass

    context = _build_dashboard_context(current_state, target_dir, diff=diff)
    return templates.TemplateResponse(
        request=request,
        name="fragments/dashboard.html",
        context=context,
    )


@app.post("/sync", response_class=HTMLResponse)
async def post_sync(
    request: Request,
    normalize_audio: str | None = Form(default=None),
    audio_format: str | None = Form(default=None),
    enable_sponsorblock: str | None = Form(default=None),
    cookies_browser: str | None = Form(default=None),
    cookies_file: str | None = Form(default=None),
    sync_form: str | None = Form(default=None),
) -> HTMLResponse:
    """Download missing tracks in background thread pool and update local state."""
    target_dir = _get_target_dir(request)
    state_manager = StateManager(target_dir=target_dir)

    try:
        current_state = state_manager.load()
    except StorageError as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/error.html",
            context={"error_message": f"Could not load state: {exc}"},
        )

    if not current_state.playlist_url:
        return templates.TemplateResponse(
            request=request,
            name="fragments/error.html",
            context={"error_message": "No playlist URL configured."},
        )

    if sync_form is not None:
        should_normalize = (
            normalize_audio is not None
            and normalize_audio.lower() in ("true", "1", "on")
        )
        should_sponsorblock = (
            enable_sponsorblock is not None
            and enable_sponsorblock.lower() in ("true", "1", "on")
        )
    elif normalize_audio is not None:
        should_normalize = normalize_audio.lower() in ("true", "1", "on")
        should_sponsorblock = (
            enable_sponsorblock.lower() in ("true", "1", "on")
            if enable_sponsorblock is not None
            else current_state.config.enable_sponsorblock
        )
    else:
        should_normalize = current_state.config.normalize_audio
        should_sponsorblock = current_state.config.enable_sponsorblock

    if audio_format is not None and audio_format in ("m4a", "mp3"):
        should_format = audio_format
    else:
        should_format = current_state.config.audio_format

    if cookies_browser is not None:
        clean_cookies_browser = (
            cookies_browser.strip()
            if cookies_browser.strip() not in ("none", "None", "")
            else None
        )
    else:
        clean_cookies_browser = current_state.config.cookies_browser

    if cookies_file is not None:
        clean_cookies_file = (
            cookies_file.strip()
            if cookies_file.strip()
            else None
        )
    else:
        clean_cookies_file = current_state.config.cookies_file

    extractor = PlaylistExtractor(
        normalize_audio=should_normalize,
        audio_format=should_format,
        enable_sponsorblock=should_sponsorblock,
    )
    diff_engine = DiffEngine()

    try:
        # Query remote playlist in worker thread
        title, remote_tracks = await asyncio.to_thread(
            extractor.fetch_playlist_details, current_state.playlist_url
        )
    except Exception as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/error.html",
            context={"error_message": f"Failed to inspect playlist: {exc}"},
        )

    diff = diff_engine.compute(remote_tracks=remote_tracks, current_state=current_state)

    updated_tracks: dict[str, TrackSnapshot] = dict(current_state.tracks)

    # Record unavailable tracks
    for unavail in diff.unavailable_tracks:
        updated_tracks[unavail.video_id] = unavail

    # Download new tracks
    if diff.new_tracks:
        ids_to_download = [t.video_id for t in diff.new_tracks]
        try:
            # Run download inside thread pool to avoid blocking the event loop
            await asyncio.to_thread(
                extractor.download_tracks,
                ids_to_download,
                output_dir=str(target_dir),
                enable_sponsorblock=should_sponsorblock,
                cookies_browser=clean_cookies_browser,
                cookies_file=clean_cookies_file,
                track_trims=current_state.tracks,
            )
            for new_t in diff.new_tracks:
                existing_t = current_state.tracks.get(new_t.video_id)
                updated_tracks[new_t.video_id] = TrackSnapshot(
                    video_id=new_t.video_id,
                    title=new_t.title,
                    status=TrackStatus.DOWNLOADED,
                    trim_start=existing_t.trim_start if existing_t else None,
                    trim_end=existing_t.trim_end if existing_t else None,
                )
        except Exception as exc:
            for new_t in diff.new_tracks:
                if new_t.video_id not in updated_tracks:
                    existing_t = current_state.tracks.get(new_t.video_id)
                    updated_tracks[new_t.video_id] = TrackSnapshot(
                        video_id=new_t.video_id,
                        title=new_t.title,
                        status=TrackStatus.ERROR,
                        error_message=str(exc),
                        trim_start=existing_t.trim_start if existing_t else None,
                        trim_end=existing_t.trim_end if existing_t else None,
                    )

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    new_state = SyncState(
        playlist_url=current_state.playlist_url,
        playlist_name=title or current_state.playlist_name,
        last_synced_at=now_iso,
        tracks=updated_tracks,
        config=SyncConfig(
            normalize_audio=should_normalize,
            target_lufs=current_state.config.target_lufs,
            true_peak=current_state.config.true_peak,
            audio_format=should_format,
            audio_quality=current_state.config.audio_quality,
            enable_sponsorblock=should_sponsorblock,
            cookies_browser=clean_cookies_browser,
            cookies_file=clean_cookies_file,
        ),
    )

    try:
        state_manager.save(new_state)
    except StorageError as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/error.html",
            context={"error_message": f"Failed to save state: {exc}"},
        )

    # Re-evaluate diff post-sync
    post_diff = diff_engine.compute(remote_tracks=remote_tracks, current_state=new_state)
    context = _build_dashboard_context(new_state, target_dir, diff=post_diff)
    return templates.TemplateResponse(
        request=request,
        name="fragments/dashboard.html",
        context=context,
    )


@app.post("/settings/cookies", response_class=HTMLResponse)
async def post_settings_cookies(
    request: Request,
    cookies_browser: str | None = Form(default=None),
    cookies_file: str | None = Form(default=None),
) -> HTMLResponse:
    """Configure or update browser/file cookies authentication."""
    target_dir = _get_target_dir(request)
    state_manager = StateManager(target_dir=target_dir)

    try:
        current_state = state_manager.load()
    except StorageError as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/error.html",
            context={"error_message": f"Could not load state: {exc}"},
        )

    clean_cookies_browser = (
        cookies_browser.strip()
        if cookies_browser and cookies_browser.strip() not in ("none", "None", "")
        else None
    )
    clean_cookies_file = (
        cookies_file.strip()
        if cookies_file and cookies_file.strip()
        else None
    )

    new_config = SyncConfig(
        normalize_audio=current_state.config.normalize_audio,
        target_lufs=current_state.config.target_lufs,
        true_peak=current_state.config.true_peak,
        audio_format=current_state.config.audio_format,
        audio_quality=current_state.config.audio_quality,
        enable_sponsorblock=current_state.config.enable_sponsorblock,
        cookies_browser=clean_cookies_browser,
        cookies_file=clean_cookies_file,
    )

    new_state = SyncState(
        playlist_url=current_state.playlist_url,
        playlist_name=current_state.playlist_name,
        last_synced_at=current_state.last_synced_at,
        tracks=current_state.tracks,
        config=new_config,
    )

    try:
        state_manager.save(new_state)
    except StorageError as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/error.html",
            context={"error_message": f"Failed to save state: {exc}"},
        )

    context = _build_dashboard_context(new_state, target_dir)
    return templates.TemplateResponse(
        request=request,
        name="fragments/dashboard.html",
        context=context,
    )


@app.post("/track/{video_id}/trim", response_class=HTMLResponse)
async def post_track_trim(
    request: Request,
    video_id: str,
    trim_start: str | None = Form(default=None),
    trim_end: str | None = Form(default=None),
) -> HTMLResponse:
    """Configure or update surgical trim for a specific track."""
    target_dir = _get_target_dir(request)
    state_manager = StateManager(target_dir=target_dir)

    try:
        current_state = state_manager.load()
    except StorageError as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/error.html",
            context={"error_message": f"Could not load state: {exc}"},
        )

    clean_start = trim_start.strip() if trim_start and trim_start.strip() else None
    clean_end = trim_end.strip() if trim_end and trim_end.strip() else None

    updated_tracks = dict(current_state.tracks)
    if video_id in updated_tracks:
        old_track = updated_tracks[video_id]
        updated_tracks[video_id] = TrackSnapshot(
            video_id=old_track.video_id,
            title=old_track.title,
            status=old_track.status,
            error_message=old_track.error_message,
            trim_start=clean_start,
            trim_end=clean_end,
        )
    else:
        updated_tracks[video_id] = TrackSnapshot(
            video_id=video_id,
            title=video_id,
            status=TrackStatus.PENDING,
            trim_start=clean_start,
            trim_end=clean_end,
        )

    new_state = SyncState(
        playlist_url=current_state.playlist_url,
        playlist_name=current_state.playlist_name,
        last_synced_at=current_state.last_synced_at,
        tracks=updated_tracks,
        config=current_state.config,
    )

    try:
        state_manager.save(new_state)
    except StorageError as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/error.html",
            context={"error_message": f"Failed to save state: {exc}"},
        )

    context = _build_dashboard_context(new_state, target_dir)
    return templates.TemplateResponse(
        request=request,
        name="fragments/dashboard.html",
        context=context,
    )


@app.post("/ignore/{video_id}", response_class=HTMLResponse)
async def post_ignore_track(request: Request, video_id: str) -> HTMLResponse:
    """Mark an unavailable or error track as SKIPPED to silence warnings."""
    target_dir = _get_target_dir(request)
    state_manager = StateManager(target_dir=target_dir)

    try:
        current_state = state_manager.load()
    except StorageError as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/error.html",
            context={"error_message": f"Could not load state: {exc}"},
        )

    updated_tracks = dict(current_state.tracks)
    if video_id in updated_tracks:
        old_track = updated_tracks[video_id]
        updated_tracks[video_id] = TrackSnapshot(
            video_id=old_track.video_id,
            title=old_track.title,
            status=TrackStatus.SKIPPED,
            error_message=old_track.error_message,
            trim_start=old_track.trim_start,
            trim_end=old_track.trim_end,
        )

        new_state = SyncState(
            playlist_url=current_state.playlist_url,
            playlist_name=current_state.playlist_name,
            last_synced_at=current_state.last_synced_at,
            tracks=updated_tracks,
            config=current_state.config,
        )
        try:
            state_manager.save(new_state)
            current_state = new_state
        except StorageError as exc:
            return templates.TemplateResponse(
                request=request,
                name="fragments/error.html",
                context={"error_message": f"Failed to save state: {exc}"},
            )

    context = _build_dashboard_context(current_state, target_dir)
    return templates.TemplateResponse(
        request=request,
        name="fragments/dashboard.html",
        context=context,
    )


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for scoped folder server startup."""
    parser = argparse.ArgumentParser(
        prog="yt-sync-web",
        description="Run the yt-sync Web Dashboard scoped to a target directory.",
    )
    parser.add_argument(
        "target_dir",
        type=Path,
        nargs="?",
        default=None,
        help="Target folder where audio files and state are stored.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host address to bind the web server (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port number to bind the web server (default: 8000).",
    )
    return parser.parse_args(argv)


def main() -> None:
    """Start the uvicorn web server scoped to the specified target directory."""
    args = parse_args()
    if args.target_dir:
        resolved_dir = args.target_dir.resolve()
        resolved_dir.mkdir(parents=True, exist_ok=True)
        app.state.target_dir = resolved_dir
    else:
        app.state.target_dir = Path.cwd().resolve()

    print(f"🎵 Starting yt-sync Web Dashboard scoped to: {app.state.target_dir}")
    print(f"🌐 Server available at: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
