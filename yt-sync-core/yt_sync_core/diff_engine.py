"""Moteur d'analyse différentielle entre état local et playlist distante."""

from __future__ import annotations

from dataclasses import dataclass, field

from yt_sync_core.extractor import RemoteTrack
from yt_sync_core.models import SyncState, TrackSnapshot, TrackStatus

# Statuts considérés comme "déjà traités" → on ne re-télécharge pas
_STABLE_STATUSES: frozenset[TrackStatus] = frozenset(
    {TrackStatus.DOWNLOADED, TrackStatus.SKIPPED}
)


@dataclass
class DiffResult:
    """Résultat de l'analyse différentielle.

    Attributes:
        already_downloaded: Pistes déjà présentes localement (DOWNLOADED ou SKIPPED)
            et toujours disponibles dans la playlist distante.
        new_tracks: Pistes présentes dans la playlist distante mais absentes ou
            en erreur / en attente localement → à télécharger.
        removed_tracks: Pistes connues localement mais absentes de la playlist
            distante (retirées de la playlist par le propriétaire).
        unavailable_tracks: Pistes présentes dans la playlist distante mais
            marquées comme indisponibles (privées, supprimées…).
    """

    already_downloaded: list[TrackSnapshot]
    new_tracks: list[RemoteTrack]
    removed_tracks: list[TrackSnapshot]
    unavailable_tracks: list[TrackSnapshot]

    @property
    def total_count(self) -> int:
        """Nombre total de pistes réparties dans les quatre catégories."""
        return (
            len(self.already_downloaded)
            + len(self.new_tracks)
            + len(self.removed_tracks)
            + len(self.unavailable_tracks)
        )


class DiffEngine:
    """Calcule la différence entre l'état distant et l'état local.

    La classe est **pure** : elle ne lit ni n'écrit aucun fichier, ne fait
    aucun appel réseau et ne produit aucun effet de bord.
    """

    def compute(
        self,
        *,
        remote_tracks: list[RemoteTrack],
        current_state: SyncState,
    ) -> DiffResult:
        """Compare la playlist distante à l'état local et classifie les pistes.

        Args:
            remote_tracks: Liste des pistes telles que vues depuis YouTube.
            current_state: État de synchronisation local courant.

        Returns:
            Un :class:`DiffResult` avec les quatre listes remplies.
        """
        local_snapshots: dict[str, TrackSnapshot] = dict(current_state.tracks)
        remote_by_id: dict[str, RemoteTrack] = {t.video_id: t for t in remote_tracks}

        already_downloaded: list[TrackSnapshot] = []
        new_tracks: list[RemoteTrack] = []
        removed_tracks: list[TrackSnapshot] = []
        unavailable_tracks: list[TrackSnapshot] = []

        # --- Analyse de chaque piste distante ---
        for remote in remote_tracks:
            if not remote.is_available:
                # Récupère le vrai titre via le snapshot si on le connaît
                snapshot = local_snapshots.get(remote.video_id)
                known_title = snapshot.title if snapshot else remote.title
                unavailable_tracks.append(
                    TrackSnapshot(
                        video_id=remote.video_id,
                        title=known_title,
                        status=TrackStatus.ERROR,
                        error_message="Piste indisponible sur YouTube",
                    )
                )
                continue

            snapshot = local_snapshots.get(remote.video_id)

            if snapshot is not None and snapshot.status in _STABLE_STATUSES:
                already_downloaded.append(snapshot)
            else:
                # Absent du state, ou en PENDING / ERROR → à télécharger
                new_tracks.append(remote)

        # --- Pistes locales absentes de la playlist distante ---
        remote_ids: frozenset[str] = frozenset(remote_by_id.keys())
        for video_id, snapshot in local_snapshots.items():
            if video_id not in remote_ids:
                removed_tracks.append(snapshot)

        return DiffResult(
            already_downloaded=already_downloaded,
            new_tracks=new_tracks,
            removed_tracks=removed_tracks,
            unavailable_tracks=unavailable_tracks,
        )
