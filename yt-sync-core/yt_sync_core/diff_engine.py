"""Pure differential analysis engine comparing remote playlist with local state."""

from __future__ import annotations

from dataclasses import dataclass

from yt_sync_core.extractor import RemoteTrack
from yt_sync_core.models import SyncState, TrackSnapshot, TrackStatus

# Statuses considered processed and stable -> will not be re-downloaded
_STABLE_STATUSES: frozenset[TrackStatus] = frozenset(
    {TrackStatus.DOWNLOADED, TrackStatus.SKIPPED}
)


@dataclass
class DiffResult:
    """Differential analysis result.

    Attributes:
        already_downloaded: Tracks already present locally (DOWNLOADED or SKIPPED)
            and still present in the remote playlist.
        new_tracks: Tracks present remotely but missing or in error/pending status
            locally -> ready to download.
        removed_tracks: Tracks known locally but no longer present in the remote playlist.
        unavailable_tracks: Tracks present in the remote playlist but flagged as
            unavailable (private, deleted, removed...).
    """

    already_downloaded: list[TrackSnapshot]
    new_tracks: list[RemoteTrack]
    removed_tracks: list[TrackSnapshot]
    unavailable_tracks: list[TrackSnapshot]

    @property
    def total_count(self) -> int:
        """Total count of tracks across all four categories."""
        return (
            len(self.already_downloaded)
            + len(self.new_tracks)
            + len(self.removed_tracks)
            + len(self.unavailable_tracks)
        )


class DiffEngine:
    """Computes differences between remote playlist tracks and local SyncState.

    This engine is pure and deterministic: it does not perform I/O, network calls,
    or mutate any input states.
    """

    def compute(
        self,
        *,
        remote_tracks: list[RemoteTrack],
        current_state: SyncState,
    ) -> DiffResult:
        """Compare the remote playlist against local state and classify tracks.

        Args:
            remote_tracks: List of remote tracks fetched from YouTube.
            current_state: Current local synchronization state.

        Returns:
            A :class:`DiffResult` instance containing classified tracks.
        """
        local_snapshots: dict[str, TrackSnapshot] = dict(current_state.tracks)
        remote_by_id: dict[str, RemoteTrack] = {t.video_id: t for t in remote_tracks}

        already_downloaded: list[TrackSnapshot] = []
        new_tracks: list[RemoteTrack] = []
        removed_tracks: list[TrackSnapshot] = []
        unavailable_tracks: list[TrackSnapshot] = []

        # --- Inspect remote tracks ---
        for remote in remote_tracks:
            if not remote.is_available:
                # Recover original known title from local snapshot if available
                snapshot = local_snapshots.get(remote.video_id)
                known_title = snapshot.title if snapshot else remote.title
                unavailable_tracks.append(
                    TrackSnapshot(
                        video_id=remote.video_id,
                        title=known_title,
                        status=TrackStatus.ERROR,
                        error_message="Track unavailable on YouTube",
                        trim_start=snapshot.trim_start if snapshot else None,
                        trim_end=snapshot.trim_end if snapshot else None,
                    )
                )
                continue

            snapshot = local_snapshots.get(remote.video_id)

            if snapshot is not None and snapshot.status in _STABLE_STATUSES:
                already_downloaded.append(snapshot)
            else:
                # Absent from state, or in PENDING / ERROR status -> download
                new_tracks.append(remote)

        # --- Identify tracks removed from remote playlist ---
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
