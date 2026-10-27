"""Tests unitaires pour les modèles Pydantic de yt_sync_core.

Pattern : Arrange-Act-Assert (AAA)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from yt_sync_core.models import SyncConfig, SyncState, TrackSnapshot, TrackStatus


# ---------------------------------------------------------------------------
# TrackStatus
# ---------------------------------------------------------------------------


class TestTrackStatus:
    """Vérifie l'énumération TrackStatus et ses valeurs."""

    def test_pending_value(self) -> None:
        # Arrange / Act
        status = TrackStatus.PENDING
        # Assert
        assert status.value == "pending"

    def test_downloaded_value(self) -> None:
        status = TrackStatus.DOWNLOADED
        assert status.value == "downloaded"

    def test_error_value(self) -> None:
        status = TrackStatus.ERROR
        assert status.value == "error"

    def test_skipped_value(self) -> None:
        status = TrackStatus.SKIPPED
        assert status.value == "skipped"

    def test_all_members_count(self) -> None:
        # S'assure qu'on n'a pas oublié de valeur ou ajouté des surprises
        assert len(TrackStatus) == 4


# ---------------------------------------------------------------------------
# TrackSnapshot
# ---------------------------------------------------------------------------


class TestTrackSnapshotCreation:
    """Vérifie la création et la validation d'un TrackSnapshot."""

    def test_minimal_snapshot_creation(self) -> None:
        # Arrange
        video_id = "dQw4w9WgXcQ"
        title = "Never Gonna Give You Up"
        # Act
        snapshot = TrackSnapshot(video_id=video_id, title=title)
        # Assert
        assert snapshot.video_id == video_id
        assert snapshot.title == title

    def test_default_status_is_pending(self) -> None:
        # Arrange / Act
        snapshot = TrackSnapshot(video_id="abc123", title="Some Track")
        # Assert
        assert snapshot.status == TrackStatus.PENDING

    def test_default_error_message_is_none(self) -> None:
        # Arrange / Act
        snapshot = TrackSnapshot(video_id="abc123", title="Some Track")
        # Assert
        assert snapshot.error_message is None

    def test_snapshot_with_explicit_status(self) -> None:
        # Arrange
        snapshot = TrackSnapshot(
            video_id="abc123",
            title="Some Track",
            status=TrackStatus.DOWNLOADED,
        )
        # Assert
        assert snapshot.status == TrackStatus.DOWNLOADED

    def test_snapshot_with_error_message(self) -> None:
        # Arrange
        error_msg = "HTTP 403: Forbidden"
        # Act
        snapshot = TrackSnapshot(
            video_id="err001",
            title="Broken Track",
            status=TrackStatus.ERROR,
            error_message=error_msg,
        )
        # Assert
        assert snapshot.error_message == error_msg

    def test_snapshot_missing_video_id_raises(self) -> None:
        # Arrange / Act / Assert
        with pytest.raises(ValidationError):
            TrackSnapshot(title="No ID")  # type: ignore[call-arg]

    def test_snapshot_missing_title_raises(self) -> None:
        with pytest.raises(ValidationError):
            TrackSnapshot(video_id="abc123")  # type: ignore[call-arg]

    def test_snapshot_video_id_empty_string_raises(self) -> None:
        with pytest.raises(ValidationError):
            TrackSnapshot(video_id="", title="Some Track")

    def test_snapshot_title_empty_string_raises(self) -> None:
        with pytest.raises(ValidationError):
            TrackSnapshot(video_id="abc123", title="")

    def test_snapshot_invalid_status_raises(self) -> None:
        with pytest.raises(ValidationError):
            TrackSnapshot(video_id="abc123", title="Track", status="unknown")  # type: ignore[arg-type]

    def test_snapshot_serialization_to_dict(self) -> None:
        # Arrange
        snapshot = TrackSnapshot(video_id="abc123", title="My Track")
        # Act
        data = snapshot.model_dump()
        # Assert
        assert data["video_id"] == "abc123"
        assert data["title"] == "My Track"
        assert data["status"] == TrackStatus.PENDING

    def test_snapshot_round_trip_json(self) -> None:
        # Arrange
        original = TrackSnapshot(
            video_id="xyz789",
            title="Round Trip",
            status=TrackStatus.DOWNLOADED,
        )
        # Act
        json_str = original.model_dump_json()
        restored = TrackSnapshot.model_validate_json(json_str)
        # Assert
        assert restored == original


# ---------------------------------------------------------------------------
# SyncState
# ---------------------------------------------------------------------------


class TestSyncStateCreation:
    """Vérifie la création et le comportement de SyncState."""

    def test_empty_sync_state(self) -> None:
        # Arrange / Act
        state = SyncState()
        # Assert
        assert state.tracks == {}

    def test_sync_state_with_one_track(self) -> None:
        # Arrange
        track = TrackSnapshot(video_id="t001", title="Track One")
        # Act
        state = SyncState(tracks={"t001": track})
        # Assert
        assert "t001" in state.tracks
        assert state.tracks["t001"].title == "Track One"

    def test_sync_state_tracks_default_is_empty_dict(self) -> None:
        # Arrange / Act
        state = SyncState()
        # Assert
        assert isinstance(state.tracks, dict)
        assert len(state.tracks) == 0

    def test_sync_state_round_trip_json(self) -> None:
        # Arrange
        track = TrackSnapshot(video_id="t001", title="Track One", status=TrackStatus.DOWNLOADED)
        original = SyncState(tracks={"t001": track})
        # Act
        json_str = original.model_dump_json()
        restored = SyncState.model_validate_json(json_str)
        # Assert
        assert restored == original

    def test_sync_state_two_tracks_preserves_both(self) -> None:
        # Arrange
        track_a = TrackSnapshot(video_id="a001", title="Alpha")
        track_b = TrackSnapshot(video_id="b002", title="Beta", status=TrackStatus.ERROR)
        # Act
        state = SyncState(tracks={"a001": track_a, "b002": track_b})
        # Assert
        assert len(state.tracks) == 2
        assert state.tracks["b002"].status == TrackStatus.ERROR


# ---------------------------------------------------------------------------
# SyncConfig & Normalization
# ---------------------------------------------------------------------------


class TestSyncConfig:
    """Vérifie la configuration de synchronisation et de normalisation audio."""

    def test_default_sync_config_values(self) -> None:
        # Arrange / Act
        config = SyncConfig()
        # Assert
        assert config.normalize_audio is True
        assert config.target_lufs == -14.0
        assert config.true_peak == -1.5

    def test_custom_sync_config_values(self) -> None:
        # Arrange
        normalize_audio = False
        target_lufs = -16.0
        true_peak = -2.0
        # Act
        config = SyncConfig(
            normalize_audio=normalize_audio,
            target_lufs=target_lufs,
            true_peak=true_peak,
        )
        # Assert
        assert config.normalize_audio is False
        assert config.target_lufs == -16.0
        assert config.true_peak == -2.0

    def test_sync_state_default_config_has_normalization_enabled(self) -> None:
        # Arrange / Act
        state = SyncState()
        # Assert
        assert state.config.normalize_audio is True
        assert state.config.target_lufs == -14.0
        assert state.config.true_peak == -1.5
        assert state.normalize_audio is True
        assert state.target_lufs == -14.0
        assert state.true_peak == -1.5

    def test_sync_state_with_custom_config(self) -> None:
        # Arrange
        custom_cfg = SyncConfig(
            normalize_audio=False,
            target_lufs=-18.0,
            true_peak=-1.0,
        )
        # Act
        state = SyncState(config=custom_cfg)
        # Assert
        assert state.config.normalize_audio is False
        assert state.config.target_lufs == -18.0
        assert state.config.true_peak == -1.0
        assert state.normalize_audio is False

    def test_sync_state_serialization_round_trip_with_config(self) -> None:
        # Arrange
        original = SyncState(
            config=SyncConfig(
                normalize_audio=False,
                target_lufs=-16.0,
                true_peak=-2.0,
            )
        )
        # Act
        json_str = original.model_dump_json()
        restored = SyncState.model_validate_json(json_str)
        # Assert
        assert restored == original
        assert restored.config.normalize_audio is False
        assert restored.config.target_lufs == -16.0
        assert restored.config.true_peak == -2.0
