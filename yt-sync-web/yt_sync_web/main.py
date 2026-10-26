"""Application Web FastAPI pour yt-sync avec HTMX 2 et Jinja2."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from yt_sync_core.diff_engine import DiffEngine, DiffResult
from yt_sync_core.exceptions import ExtractionError, StorageError, YtSyncError
from yt_sync_core.extractor import PlaylistExtractor
from yt_sync_core.models import SyncState, TrackSnapshot, TrackStatus
from yt_sync_core.storage import StateManager

app = FastAPI(title="yt-sync web", description="Interface Web pour la synchronisation de playlists YouTube")

# Configuration du dossier des templates Jinja2
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request) -> HTMLResponse:
    """Affiche la page d'accueil avec le formulaire de configuration."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )


@app.post("/analyze", response_class=HTMLResponse)
async def post_analyze(
    request: Request,
    target_dir: str = Form(...),
    playlist_url: str = Form(...),
) -> HTMLResponse:
    """Analyse la playlist distante et retourne le fragment HTML du rapport différentiel."""
    target_path = Path(target_dir).expanduser().resolve()

    try:
        # Création du dossier cible si inexistant
        target_path.mkdir(parents=True, exist_ok=True)
        state_manager = StateManager(target_dir=target_path)
        current_state = state_manager.load()
    except (StorageError, OSError) as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/error.html",
            context={"error_message": f"Erreur d'accès au dossier local : {exc}"},
        )

    extractor = PlaylistExtractor()
    diff_engine = DiffEngine()

    try:
        # Délégation de l'appel bloquant yt-dlp dans un worker thread
        remote_tracks = await asyncio.to_thread(extractor.fetch_playlist, playlist_url)
    except (ExtractionError, Exception) as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/error.html",
            context={"error_message": f"Erreur d'extraction de la playlist : {exc}"},
        )

    diff = diff_engine.compute(remote_tracks=remote_tracks, current_state=current_state)

    return templates.TemplateResponse(
        request=request,
        name="fragments/report.html",
        context={
            "diff": diff,
            "target_dir": str(target_path),
            "playlist_url": playlist_url,
        },
    )


@app.post("/sync", response_class=HTMLResponse)
async def post_sync(
    request: Request,
    target_dir: str = Form(...),
    playlist_url: str = Form(...),
) -> HTMLResponse:
    """Télécharge les nouvelles pistes dans un thread pool et met à jour l'état local."""
    target_path = Path(target_dir).expanduser().resolve()
    target_path.mkdir(parents=True, exist_ok=True)
    state_manager = StateManager(target_dir=target_path)

    try:
        current_state = state_manager.load()
    except StorageError as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/error.html",
            context={"error_message": f"Erreur lors du chargement de l'état : {exc}"},
        )

    extractor = PlaylistExtractor()
    diff_engine = DiffEngine()

    # Ré-analyse pour obtenir le différentiel frais
    try:
        remote_tracks = await asyncio.to_thread(extractor.fetch_playlist, playlist_url)
    except Exception as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/error.html",
            context={"error_message": f"Erreur lors de la récupération : {exc}"},
        )

    diff = diff_engine.compute(remote_tracks=remote_tracks, current_state=current_state)

    updated_tracks: dict[str, TrackSnapshot] = dict(current_state.tracks)

    # 1. Enregistrer les inaccessibles
    for unavail in diff.unavailable_tracks:
        updated_tracks[unavail.video_id] = unavail

    # 2. Télécharger les nouvelles pistes si présentes
    downloaded_count = 0
    if diff.new_tracks:
        ids_to_download = [t.video_id for t in diff.new_tracks]
        try:
            # Exécution dans un thread worker pour ne pas bloquer l'event loop
            await asyncio.to_thread(
                extractor.download_tracks,
                ids_to_download,
                output_dir=str(target_path),
            )
            for new_t in diff.new_tracks:
                updated_tracks[new_t.video_id] = TrackSnapshot(
                    video_id=new_t.video_id,
                    title=new_t.title,
                    status=TrackStatus.DOWNLOADED,
                )
            downloaded_count = len(diff.new_tracks)
        except Exception as exc:
            for new_t in diff.new_tracks:
                if new_t.video_id not in updated_tracks:
                    updated_tracks[new_t.video_id] = TrackSnapshot(
                        video_id=new_t.video_id,
                        title=new_t.title,
                        status=TrackStatus.ERROR,
                        error_message=str(exc),
                    )
            return templates.TemplateResponse(
                request=request,
                name="fragments/error.html",
                context={"error_message": f"Erreur lors du téléchargement : {exc}"},
            )

    # 3. Sauvegarde de l'état
    new_state = SyncState(tracks=updated_tracks)
    try:
        state_manager.save(new_state)
    except StorageError as exc:
        return templates.TemplateResponse(
            request=request,
            name="fragments/error.html",
            context={"error_message": f"Erreur lors de la sauvegarde : {exc}"},
        )

    return templates.TemplateResponse(
        request=request,
        name="fragments/sync_complete.html",
        context={
            "target_dir": str(target_path),
            "playlist_url": playlist_url,
            "downloaded_count": downloaded_count,
            "total_indexed": len(updated_tracks),
        },
    )
