"""Command-line interface (CLI) for yt-sync."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from yt_sync_core.diff_engine import DiffEngine, DiffResult
from yt_sync_core.exceptions import ExtractionError, StorageError
from yt_sync_core.extractor import PlaylistExtractor
from yt_sync_core.models import SyncConfig, SyncState, TrackSnapshot, TrackStatus
from yt_sync_core.storage import StateManager


def build_parser() -> argparse.ArgumentParser:
    """Build and configure the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="yt-sync",
        description="Synchronize YouTube playlists with a local destination directory.",
    )
    parser.add_argument(
        "target_dir",
        type=Path,
        help="Target local folder where audio files and state are saved.",
    )
    parser.add_argument(
        "playlist_url",
        type=str,
        nargs="?",
        default=None,
        help="URL of the YouTube playlist to synchronize (optional if already configured in state).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform differential analysis only without downloading tracks.",
    )
    parser.add_argument(
        "--no-normalize",
        action="store_true",
        help="Disable EBU R128 audio loudness normalization.",
    )
    return parser


def display_report(diff: DiffResult) -> None:
    """Display a formatted summary of the differential analysis."""
    print("\n" + "=" * 60)
    print("📊 SYNCHRONIZATION REPORT")
    print("=" * 60)
    print(f"  • Already downloaded / up-to-date : {len(diff.already_downloaded)}")
    print(f"  • New tracks to download          : {len(diff.new_tracks)}")
    print(f"  • Removed from remote playlist    : {len(diff.removed_tracks)}")
    print(f"  • Unavailable / private tracks     : {len(diff.unavailable_tracks)}")
    print("=" * 60)

    if diff.new_tracks:
        print("\n📥 New tracks to download:")
        for track in diff.new_tracks:
            print(f"  [+] [{track.video_id}] {track.title}")

    if diff.unavailable_tracks:
        print("\n⚠️ Unavailable tracks detected (Private / Deleted):")
        for track in diff.unavailable_tracks:
            print(f"  [!] [{track.video_id}] {track.title}")
        print("  💡 Recommended action:")
        print("     These tracks can no longer be retrieved from YouTube.")
        print("     If you already possess a local copy, keep it safely.")
        print("     Otherwise, remove them from your YouTube playlist to clean up state.")

    if diff.removed_tracks:
        print("\n🗑️ Tracks removed from remote playlist:")
        for track in diff.removed_tracks:
            print(f"  [-] [{track.video_id}] {track.title}")
        print("  💡 Recommended action: Local files are kept untouched for safety.")


def progress_hook(status_dict: dict[str, Any]) -> None:
    """yt-dlp progress hook to display download status in real time."""
    status = status_dict.get("status")
    if status == "downloading":
        filename = status_dict.get("filename", "")
        percent = status_dict.get("_percent_str", "").strip()
        speed = status_dict.get("_speed_str", "").strip()
        eta = status_dict.get("_eta_str", "").strip()
        clean_name = Path(filename).name if filename else "in progress"
        sys.stdout.write(f"\r⏳ Downloading: {clean_name[:40]}... {percent} at {speed} (ETA {eta})")
        sys.stdout.flush()
    elif status == "finished":
        sys.stdout.write("\n✅ Download completed, post-processing...\n")
        sys.stdout.flush()


def run_sync(
    target_dir: Path,
    playlist_url: str | None = None,
    *,
    dry_run: bool = False,
    normalize_audio: bool = True,
    extractor: PlaylistExtractor | None = None,
) -> int:
    """Execute the end-to-end synchronization workflow."""
    if extractor is None:
        extractor = PlaylistExtractor(normalize_audio=normalize_audio)

    # 1. Target directory validation and preparation
    target_dir = target_dir.resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    state_manager = StateManager(target_dir=target_dir)

    print(f"📁 Target folder: {target_dir}")

    # 2. Load local state
    try:
        current_state = state_manager.load()
    except StorageError as exc:
        print(f"❌ Error loading local state: {exc}", file=sys.stderr)
        return 1

    # Resolve playlist URL
    effective_url = playlist_url or current_state.playlist_url
    if not effective_url:
        print("❌ Error: Playlist URL must be provided or configured in the local state.", file=sys.stderr)
        return 1

    print(f"🔗 Playlist URL: {effective_url}")

    # 3. Remote extraction and differential analysis
    print("🔍 Checking playlist diff...")
    try:
        remote_tracks = extractor.fetch_playlist(effective_url)
    except ExtractionError as exc:
        print(f"❌ Error extracting playlist: {exc}", file=sys.stderr)
        return 1

    diff_engine = DiffEngine()
    diff = diff_engine.compute(remote_tracks=remote_tracks, current_state=current_state)

    # 4. Display synchronization report
    display_report(diff)

    if dry_run:
        print("\n[DRY RUN] No modifications or downloads performed.")
        return 0

    # 5. Download new tracks
    updated_tracks: dict[str, TrackSnapshot] = dict(current_state.tracks)

    # Register unavailable tracks
    for unavail in diff.unavailable_tracks:
        updated_tracks[unavail.video_id] = unavail

    if diff.new_tracks:
        print(f"\n🚀 Downloading {len(diff.new_tracks)} track(s)...")
        ids_to_download = [t.video_id for t in diff.new_tracks]
        try:
            extractor.download_tracks(
                ids_to_download,
                output_dir=str(target_dir),
                progress_callback=progress_hook,
                normalize_audio=normalize_audio,
            )
            # Mark successfully downloaded tracks
            for new_t in diff.new_tracks:
                updated_tracks[new_t.video_id] = TrackSnapshot(
                    video_id=new_t.video_id,
                    title=new_t.title,
                    status=TrackStatus.DOWNLOADED,
                )
        except Exception as exc:
            print(f"\n❌ Error during download: {exc}", file=sys.stderr)
            # Record failed tracks with ERROR status
            for new_t in diff.new_tracks:
                if (
                    new_t.video_id not in updated_tracks
                    or updated_tracks[new_t.video_id].status != TrackStatus.DOWNLOADED
                ):
                    updated_tracks[new_t.video_id] = TrackSnapshot(
                        video_id=new_t.video_id,
                        title=new_t.title,
                        status=TrackStatus.ERROR,
                        error_message=str(exc),
                    )
    else:
        print("\n✨ Nothing to download, target directory is up-to-date!")

    from datetime import datetime, timezone

    # 6. Save updated synchronization state
    new_state = SyncState(
        playlist_url=effective_url,
        playlist_name=current_state.playlist_name,
        last_synced_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        tracks=updated_tracks,
        config=SyncConfig(normalize_audio=normalize_audio),
    )
    try:
        state_manager.save(new_state)
        print(f"💾 Sync complete. State saved ({len(updated_tracks)} track(s) indexed).")
    except StorageError as exc:
        print(f"❌ Error saving state file: {exc}", file=sys.stderr)
        return 1

    return 0


def main(argv: list[str] | None = None) -> None:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    exit_code = run_sync(
        target_dir=args.target_dir,
        playlist_url=args.playlist_url,
        dry_run=args.dry_run,
        normalize_audio=not args.no_normalize,
    )
    if exit_code != 0:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
