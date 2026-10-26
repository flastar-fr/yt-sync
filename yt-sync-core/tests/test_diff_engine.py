"""Tests unitaires pour DiffEngine (diff_engine.py).

Pattern : Arrange-Act-Assert (AAA)
DiffEngine est une classe pure : aucun mock réseau nécessaire.
"""

from __future__ import annotations

import pytest

from yt_sync_core.diff_engine import DiffEngine, DiffResult
from yt_sync_core.extractor import RemoteTrack
from yt_sync_core.models import SyncState, TrackSnapshot, TrackStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_remote(video_id: str, title: str, available: bool = True) -> RemoteTrack:
    return RemoteTrack(video_id=video_id, title=title, is_available=available)


def _make_snapshot(
    video_id: str,
    title: str,
    status: TrackStatus = TrackStatus.DOWNLOADED,
) -> TrackSnapshot:
    return TrackSnapshot(video_id=video_id, title=title, status=status)


def _make_state(*snapshots: TrackSnapshot) -> SyncState:
    return SyncState(tracks={s.video_id: s for s in snapshots})


# ---------------------------------------------------------------------------
# DiffResult
# ---------------------------------------------------------------------------


class TestDiffResult:
    """Vérifie la structure de DiffResult."""

    def test_diff_result_has_four_lists(self) -> None:
        # Arrange / Act
        result = DiffResult(
            already_downloaded=[],
            new_tracks=[],
            removed_tracks=[],
            unavailable_tracks=[],
        )
        # Assert
        assert isinstance(result.already_downloaded, list)
        assert isinstance(result.new_tracks, list)
        assert isinstance(result.removed_tracks, list)
        assert isinstance(result.unavailable_tracks, list)

    def test_diff_result_total_count(self) -> None:
        # Arrange
        result = DiffResult(
            already_downloaded=[_make_snapshot("a", "A")],
            new_tracks=[_make_remote("b", "B")],
            removed_tracks=[_make_snapshot("c", "C")],
            unavailable_tracks=[_make_snapshot("d", "D")],
        )
        # Act / Assert
        assert result.total_count == 4


# ---------------------------------------------------------------------------
# DiffEngine.compute — cas simples
# ---------------------------------------------------------------------------


class TestDiffEngineEmptyCases:
    def test_empty_remote_empty_state_returns_all_empty(self) -> None:
        # Arrange
        engine = DiffEngine()
        state = SyncState()
        # Act
        result = engine.compute(remote_tracks=[], current_state=state)
        # Assert
        assert result.already_downloaded == []
        assert result.new_tracks == []
        assert result.removed_tracks == []
        assert result.unavailable_tracks == []

    def test_empty_remote_with_existing_state_marks_all_as_removed(self) -> None:
        # Arrange
        engine = DiffEngine()
        state = _make_state(_make_snapshot("v1", "Track One"))
        # Act
        result = engine.compute(remote_tracks=[], current_state=state)
        # Assert
        assert len(result.removed_tracks) == 1
        assert result.removed_tracks[0].video_id == "v1"

    def test_non_empty_remote_empty_state_marks_all_as_new(self) -> None:
        # Arrange
        engine = DiffEngine()
        state = SyncState()
        remote = [_make_remote("v1", "Track One"), _make_remote("v2", "Track Two")]
        # Act
        result = engine.compute(remote_tracks=remote, current_state=state)
        # Assert
        assert len(result.new_tracks) == 2
        assert result.already_downloaded == []


# ---------------------------------------------------------------------------
# DiffEngine.compute — already_downloaded
# ---------------------------------------------------------------------------


class TestDiffEngineAlreadyDownloaded:
    def test_track_downloaded_in_state_and_present_remote_is_already_downloaded(
        self,
    ) -> None:
        # Arrange
        engine = DiffEngine()
        state = _make_state(_make_snapshot("v1", "Track One", TrackStatus.DOWNLOADED))
        remote = [_make_remote("v1", "Track One")]
        # Act
        result = engine.compute(remote_tracks=remote, current_state=state)
        # Assert
        assert len(result.already_downloaded) == 1
        assert result.already_downloaded[0].video_id == "v1"

    def test_track_with_error_status_still_present_remote_is_treated_as_new(
        self,
    ) -> None:
        # Arrange
        engine = DiffEngine()
        state = _make_state(_make_snapshot("v1", "Track One", TrackStatus.ERROR))
        remote = [_make_remote("v1", "Track One")]
        # Act
        result = engine.compute(remote_tracks=remote, current_state=state)
        # Assert : un track en erreur doit être re-tenté → classé comme new
        assert len(result.new_tracks) == 1
        assert result.already_downloaded == []

    def test_track_pending_in_state_present_remote_is_treated_as_new(self) -> None:
        # Arrange
        engine = DiffEngine()
        state = _make_state(_make_snapshot("v1", "Track One", TrackStatus.PENDING))
        remote = [_make_remote("v1", "Track One")]
        # Act
        result = engine.compute(remote_tracks=remote, current_state=state)
        # Assert
        assert len(result.new_tracks) == 1

    def test_track_skipped_in_state_present_remote_is_already_downloaded(
        self,
    ) -> None:
        # Arrange : SKIPPED = volontairement ignoré, on ne re-télécharge pas
        engine = DiffEngine()
        state = _make_state(_make_snapshot("v1", "Track One", TrackStatus.SKIPPED))
        remote = [_make_remote("v1", "Track One")]
        # Act
        result = engine.compute(remote_tracks=remote, current_state=state)
        # Assert
        assert len(result.already_downloaded) == 1


# ---------------------------------------------------------------------------
# DiffEngine.compute — new_tracks
# ---------------------------------------------------------------------------


class TestDiffEngineNewTracks:
    def test_track_in_remote_not_in_state_is_new(self) -> None:
        # Arrange
        engine = DiffEngine()
        state = SyncState()
        remote = [_make_remote("v99", "Brand New")]
        # Act
        result = engine.compute(remote_tracks=remote, current_state=state)
        # Assert
        assert len(result.new_tracks) == 1
        assert result.new_tracks[0].video_id == "v99"

    def test_available_new_tracks_not_classified_as_unavailable(self) -> None:
        # Arrange
        engine = DiffEngine()
        state = SyncState()
        remote = [_make_remote("v1", "Title", available=True)]
        # Act
        result = engine.compute(remote_tracks=remote, current_state=state)
        # Assert
        assert result.unavailable_tracks == []


# ---------------------------------------------------------------------------
# DiffEngine.compute — removed_tracks
# ---------------------------------------------------------------------------


class TestDiffEngineRemovedTracks:
    def test_track_in_state_not_in_remote_is_removed(self) -> None:
        # Arrange
        engine = DiffEngine()
        state = _make_state(_make_snapshot("old_v", "Old Track"))
        remote = [_make_remote("new_v", "New Track")]
        # Act
        result = engine.compute(remote_tracks=remote, current_state=state)
        # Assert
        assert len(result.removed_tracks) == 1
        assert result.removed_tracks[0].video_id == "old_v"

    def test_removed_track_preserves_original_title_from_snapshot(self) -> None:
        # Arrange
        engine = DiffEngine()
        original_title = "Original Title From Snapshot"
        state = _make_state(_make_snapshot("v_old", original_title))
        remote: list[RemoteTrack] = []
        # Act
        result = engine.compute(remote_tracks=remote, current_state=state)
        # Assert : le titre vient bien du snapshot, pas d'une source distante
        assert result.removed_tracks[0].title == original_title

    def test_multiple_tracks_removed_all_captured(self) -> None:
        # Arrange
        engine = DiffEngine()
        state = _make_state(
            _make_snapshot("v1", "Track One"),
            _make_snapshot("v2", "Track Two"),
            _make_snapshot("v3", "Track Three"),
        )
        remote: list[RemoteTrack] = []
        # Act
        result = engine.compute(remote_tracks=remote, current_state=state)
        # Assert
        assert len(result.removed_tracks) == 3


# ---------------------------------------------------------------------------
# DiffEngine.compute — unavailable_tracks
# ---------------------------------------------------------------------------


class TestDiffEngineUnavailableTracks:
    def test_unavailable_remote_track_in_state_is_classified_unavailable(
        self,
    ) -> None:
        # Arrange
        engine = DiffEngine()
        state = _make_state(_make_snapshot("v1", "Track One"))
        remote = [_make_remote("v1", "[Private video]", available=False)]
        # Act
        result = engine.compute(remote_tracks=remote, current_state=state)
        # Assert
        assert len(result.unavailable_tracks) == 1
        assert result.unavailable_tracks[0].video_id == "v1"

    def test_unavailable_track_not_in_state_is_still_classified_unavailable(
        self,
    ) -> None:
        # Arrange : un track absent du state ET unavailable → signalé
        engine = DiffEngine()
        state = SyncState()
        remote = [_make_remote("v_ghost", "[Deleted video]", available=False)]
        # Act
        result = engine.compute(remote_tracks=remote, current_state=state)
        # Assert
        assert len(result.unavailable_tracks) == 1

    def test_unavailable_track_is_not_also_in_new_tracks(self) -> None:
        # Arrange
        engine = DiffEngine()
        state = SyncState()
        remote = [_make_remote("v1", "[Deleted]", available=False)]
        # Act
        result = engine.compute(remote_tracks=remote, current_state=state)
        # Assert
        assert result.new_tracks == []

    def test_unavailable_track_title_preserved_from_snapshot_when_known(
        self,
    ) -> None:
        # Arrange
        engine = DiffEngine()
        known_title = "Song I Used To Know"
        state = _make_state(_make_snapshot("v1", known_title))
        remote = [_make_remote("v1", "[Private video]", available=False)]
        # Act
        result = engine.compute(remote_tracks=remote, current_state=state)
        # Assert : on retrouve le vrai nom via le snapshot
        assert result.unavailable_tracks[0].title == known_title


# ---------------------------------------------------------------------------
# DiffEngine.compute — scénarios mixtes (paramétrés)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "remote_tracks, state_snapshots, expected",
    [
        pytest.param(
            # Aucun changement : tout est déjà téléchargé
            [_make_remote("v1", "T1"), _make_remote("v2", "T2")],
            [_make_snapshot("v1", "T1"), _make_snapshot("v2", "T2")],
            {"already": 2, "new": 0, "removed": 0, "unavailable": 0},
            id="no-change",
        ),
        pytest.param(
            # Un nouveau, un existant
            [_make_remote("v1", "T1"), _make_remote("v_new", "New")],
            [_make_snapshot("v1", "T1")],
            {"already": 1, "new": 1, "removed": 0, "unavailable": 0},
            id="one-new-one-existing",
        ),
        pytest.param(
            # Un existant, un supprimé
            [_make_remote("v1", "T1")],
            [_make_snapshot("v1", "T1"), _make_snapshot("v_old", "Old")],
            {"already": 1, "new": 0, "removed": 1, "unavailable": 0},
            id="one-removed",
        ),
        pytest.param(
            # Un disponible, un privé
            [_make_remote("v1", "T1"), _make_remote("v_priv", "[Private]", False)],
            [_make_snapshot("v1", "T1"), _make_snapshot("v_priv", "Real Title")],
            {"already": 1, "new": 0, "removed": 0, "unavailable": 1},
            id="one-unavailable",
        ),
        pytest.param(
            # Combinaison complète
            [
                _make_remote("v1", "T1"),
                _make_remote("v_new", "New"),
                _make_remote("v_priv", "[Private]", False),
            ],
            [
                _make_snapshot("v1", "T1"),
                _make_snapshot("v_old", "Old"),
                _make_snapshot("v_priv", "Real Title"),
            ],
            {"already": 1, "new": 1, "removed": 1, "unavailable": 1},
            id="full-mix",
        ),
    ],
)
def test_diff_engine_parametrized(
    remote_tracks: list[RemoteTrack],
    state_snapshots: list[TrackSnapshot],
    expected: dict[str, int],
) -> None:
    """Vérifie les quatre compteurs pour des combinaisons variées."""
    # Arrange
    engine = DiffEngine()
    state = _make_state(*state_snapshots)
    # Act
    result = engine.compute(remote_tracks=remote_tracks, current_state=state)
    # Assert
    assert len(result.already_downloaded) == expected["already"]
    assert len(result.new_tracks) == expected["new"]
    assert len(result.removed_tracks) == expected["removed"]
    assert len(result.unavailable_tracks) == expected["unavailable"]
