"""Tests unitaires pour StateManager (storage.py).

Pattern : Arrange-Act-Assert (AAA)
Fixtures : tmp_path (pytest built-in) pour simuler les fichiers temporaires.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from yt_sync_core.exceptions import StateCorruptedError, StateReadError, StateWriteError
from yt_sync_core.models import SyncState, TrackSnapshot, TrackStatus
from yt_sync_core.storage import STATE_FILENAME, StateManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_target_dir(tmp_path: Path) -> Path:
    """Dossier cible vide (sans fichier d'état)."""
    return tmp_path / "playlist"


@pytest.fixture
def target_dir_with_state(tmp_path: Path) -> Path:
    """Dossier cible contenant un fichier d'état valide pré-écrit."""
    target = tmp_path / "playlist_with_state"
    target.mkdir()

    state = SyncState(
        tracks={
            "abc": TrackSnapshot(video_id="abc", title="Track ABC", status=TrackStatus.DOWNLOADED),
        }
    )
    state_file = target / STATE_FILENAME
    state_file.write_text(state.model_dump_json(), encoding="utf-8")
    return target


@pytest.fixture
def target_dir_with_corrupted_state(tmp_path: Path) -> Path:
    """Dossier cible contenant un fichier JSON invalide."""
    target = tmp_path / "corrupted"
    target.mkdir()
    (target / STATE_FILENAME).write_text("{ not valid json !!!", encoding="utf-8")
    return target


@pytest.fixture
def manager(empty_target_dir: Path) -> StateManager:
    """StateManager pointant vers un dossier vide."""
    empty_target_dir.mkdir()
    return StateManager(target_dir=empty_target_dir)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestStateManagerInit:
    def test_init_stores_target_dir(self, tmp_path: Path) -> None:
        # Arrange
        target = tmp_path / "music"
        target.mkdir()
        # Act
        manager = StateManager(target_dir=target)
        # Assert
        assert manager.target_dir == target

    def test_state_file_path_uses_constant(self, manager: StateManager) -> None:
        # Arrange / Act
        state_path = manager.state_file_path
        # Assert
        assert state_path.name == STATE_FILENAME
        assert state_path.parent == manager.target_dir

    def test_init_with_nonexistent_dir_raises(self, tmp_path: Path) -> None:
        # Arrange
        missing = tmp_path / "does_not_exist"
        # Act / Assert
        with pytest.raises(FileNotFoundError):
            StateManager(target_dir=missing)


# ---------------------------------------------------------------------------
# Lecture (load)
# ---------------------------------------------------------------------------


class TestStateManagerLoad:
    def test_load_returns_empty_state_when_no_file(self, manager: StateManager) -> None:
        # Arrange — fichier d'état absent
        # Act
        state = manager.load()
        # Assert
        assert isinstance(state, SyncState)
        assert state.tracks == {}

    def test_load_returns_valid_state_from_file(self, tmp_path: Path, target_dir_with_state: Path) -> None:
        # Arrange
        manager = StateManager(target_dir=target_dir_with_state)
        # Act
        state = manager.load()
        # Assert
        assert "abc" in state.tracks
        assert state.tracks["abc"].title == "Track ABC"

    def test_load_raises_state_corrupted_error_on_invalid_json(
        self, target_dir_with_corrupted_state: Path
    ) -> None:
        # Arrange
        manager = StateManager(target_dir=target_dir_with_corrupted_state)
        # Act / Assert
        with pytest.raises(StateCorruptedError):
            manager.load()

    def test_load_raises_state_read_error_on_permission_denied(
        self, manager: StateManager
    ) -> None:
        # Arrange — crée le fichier puis retire les droits de lecture
        state_file = manager.state_file_path
        state_file.write_text("{}", encoding="utf-8")
        state_file.chmod(0o000)
        # Act / Assert
        try:
            with pytest.raises(StateReadError):
                manager.load()
        finally:
            state_file.chmod(0o644)  # cleanup pour éviter de polluer tmp


# ---------------------------------------------------------------------------
# Écriture (save)
# ---------------------------------------------------------------------------


class TestStateManagerSave:
    def test_save_creates_state_file(self, manager: StateManager) -> None:
        # Arrange
        state = SyncState()
        # Act
        manager.save(state)
        # Assert
        assert manager.state_file_path.exists()

    def test_save_writes_valid_json(self, manager: StateManager) -> None:
        # Arrange
        state = SyncState(
            tracks={"t1": TrackSnapshot(video_id="t1", title="Track One")}
        )
        # Act
        manager.save(state)
        raw = manager.state_file_path.read_text(encoding="utf-8")
        # Assert
        data = json.loads(raw)
        assert "tracks" in data

    def test_save_and_load_round_trip(self, manager: StateManager) -> None:
        # Arrange
        track = TrackSnapshot(video_id="v1", title="Video One", status=TrackStatus.DOWNLOADED)
        original = SyncState(tracks={"v1": track})
        # Act
        manager.save(original)
        restored = manager.load()
        # Assert
        assert restored == original

    def test_save_overwrites_existing_state(self, manager: StateManager) -> None:
        # Arrange — premier état
        first_state = SyncState(
            tracks={"a": TrackSnapshot(video_id="a", title="Alpha")}
        )
        manager.save(first_state)
        # Act — second état (différent)
        second_state = SyncState(
            tracks={"b": TrackSnapshot(video_id="b", title="Beta")}
        )
        manager.save(second_state)
        loaded = manager.load()
        # Assert
        assert "b" in loaded.tracks
        assert "a" not in loaded.tracks

    def test_save_raises_state_write_error_on_permission_denied(
        self, manager: StateManager
    ) -> None:
        # Arrange — rend le dossier non-writable
        manager.target_dir.chmod(0o444)
        state = SyncState()
        # Act / Assert
        try:
            with pytest.raises(StateWriteError):
                manager.save(state)
        finally:
            manager.target_dir.chmod(0o755)


# ---------------------------------------------------------------------------
# Tests paramétrés : états avec plusieurs tracks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tracks_data",
    [
        pytest.param(
            [("id1", "Title One", TrackStatus.PENDING)],
            id="single-pending",
        ),
        pytest.param(
            [
                ("id1", "Title One", TrackStatus.DOWNLOADED),
                ("id2", "Title Two", TrackStatus.ERROR),
            ],
            id="two-tracks",
        ),
        pytest.param(
            [
                ("id1", "Alpha", TrackStatus.DOWNLOADED),
                ("id2", "Beta", TrackStatus.DOWNLOADED),
                ("id3", "Gamma", TrackStatus.SKIPPED),
            ],
            id="three-tracks-mixed",
        ),
    ],
)
def test_save_load_parametrized(
    tmp_path: Path,
    tracks_data: list[tuple[str, str, TrackStatus]],
) -> None:
    """Vérifie que save→load est fidèle pour différentes compositions d'état."""
    # Arrange
    target = tmp_path / "target"
    target.mkdir()
    manager = StateManager(target_dir=target)
    tracks = {
        vid: TrackSnapshot(video_id=vid, title=title, status=status)
        for vid, title, status in tracks_data
    }
    original = SyncState(tracks=tracks)
    # Act
    manager.save(original)
    restored = manager.load()
    # Assert
    assert restored == original
