"""Wrapper autour de yt_dlp pour l'extraction et le téléchargement de pistes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import yt_dlp

from yt_sync_core.exceptions import ExtractionError

# Statuts yt-dlp indiquant qu'une vidéo n'est plus accessible
_UNAVAILABLE_STATUSES: frozenset[str] = frozenset(
    {"private", "unavailable", "needs_auth", "subscriber_only"}
)

# Marqueurs dans les titres générés par yt-dlp pour les vidéos inaccessibles
_UNAVAILABLE_TITLE_MARKERS: tuple[str, ...] = (
    "[private video]",
    "[deleted video]",
    "[removed]",
)


@dataclass(frozen=True)
class RemoteTrack:
    """Piste telle que vue depuis YouTube (distante).

    Attributes:
        video_id: Identifiant YouTube (ex: ``dQw4w9WgXcQ``).
        title: Titre de la vidéo côté YouTube.
        is_available: ``False`` si la vidéo est privée, supprimée ou inaccessible.
    """

    video_id: str
    title: str
    is_available: bool = True


def _is_entry_unavailable(entry: dict[str, Any]) -> bool:
    """Détermine si une entrée de playlist est inaccessible."""
    availability: str = entry.get("availability") or ""
    if availability in _UNAVAILABLE_STATUSES:
        return True
    title: str = (entry.get("title") or "").lower()
    return any(marker in title for marker in _UNAVAILABLE_TITLE_MARKERS)


def _build_remote_track(entry: dict[str, Any]) -> RemoteTrack:
    """Construit un :class:`RemoteTrack` depuis un dict d'entrée yt-dlp."""
    video_id: str = entry["id"]
    title: str = entry.get("title") or video_id
    unavailable = _is_entry_unavailable(entry)
    return RemoteTrack(video_id=video_id, title=title, is_available=not unavailable)


class PlaylistExtractor:
    """Interface de haut niveau vers yt-dlp.

    Toutes les méthodes utilisent ``yt_dlp.YoutubeDL`` via le gestionnaire de
    contexte ; aucun appel réseau n'est déclenché en dehors de ``fetch_playlist``
    et ``download_tracks``.
    """

    # ------------------------------------------------------------------
    # Extraction de métadonnées
    # ------------------------------------------------------------------

    def fetch_playlist(self, url: str) -> list[RemoteTrack]:
        """Récupère la liste des pistes d'une playlist YouTube sans télécharger.

        Args:
            url: URL complète de la playlist YouTube.

        Returns:
            Liste de :class:`RemoteTrack` (peut contenir des pistes indisponibles).

        Raises:
            ExtractionError: Si yt-dlp retourne ``None`` (URL invalide, réseau…).
        """
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "extract_flat": True,
        }

        with yt_dlp.YoutubeDL(opts) as ydl:
            info: dict[str, Any] | None = ydl.extract_info(url, download=False)

        if info is None:
            raise ExtractionError(
                f"yt-dlp n'a pas pu extraire d'informations pour l'URL : {url}"
            )

        entries: list[dict[str, Any]] = info.get("entries") or []
        return [_build_remote_track(e) for e in entries]

    # ------------------------------------------------------------------
    # Téléchargement ciblé
    # ------------------------------------------------------------------

    def download_tracks(
        self,
        video_ids: list[str],
        *,
        output_dir: str,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """Télécharge une liste de vidéos par leurs IDs.

        Args:
            video_ids: Liste d'identifiants YouTube à télécharger.
            output_dir: Dossier de destination des fichiers audio.
            progress_callback: Callable optionnel appelé par yt-dlp à chaque
                progression (hook ``progress_hooks``).
        """
        if not video_ids:
            return

        hooks: list[Callable[[dict[str, Any]], None]] = []
        if progress_callback is not None:
            hooks.append(progress_callback)

        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "outtmpl": f"{output_dir}/%(title)s [%(id)s].%(ext)s",
            "format": "bestaudio/best",
            "progress_hooks": hooks,
        }

        urls = [f"https://www.youtube.com/watch?v={vid}" for vid in video_ids]

        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download(urls)
