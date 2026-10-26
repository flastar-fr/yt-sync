"""Tests unitaires pour la hiérarchie d'exceptions de yt_sync_core.

Pattern : Arrange-Act-Assert (AAA)
"""

from __future__ import annotations

import pytest

from yt_sync_core.exceptions import (
    StateCorruptedError,
    StateReadError,
    StateWriteError,
    StorageError,
    YtSyncError,
)


class TestExceptionHierarchy:
    """Vérifie que la hiérarchie d'héritage est correcte."""

    def test_yt_sync_error_is_exception(self) -> None:
        assert issubclass(YtSyncError, Exception)

    def test_storage_error_inherits_yt_sync_error(self) -> None:
        assert issubclass(StorageError, YtSyncError)

    def test_state_read_error_inherits_storage_error(self) -> None:
        assert issubclass(StateReadError, StorageError)

    def test_state_write_error_inherits_storage_error(self) -> None:
        assert issubclass(StateWriteError, StorageError)

    def test_state_corrupted_error_inherits_storage_error(self) -> None:
        assert issubclass(StateCorruptedError, StorageError)


class TestExceptionRaising:
    """Vérifie que les exceptions peuvent être levées et interceptées."""

    def test_raise_yt_sync_error(self) -> None:
        # Arrange
        message = "generic yt-sync error"
        # Act / Assert
        with pytest.raises(YtSyncError, match=message):
            raise YtSyncError(message)

    def test_raise_storage_error_caught_as_yt_sync_error(self) -> None:
        # Arrange
        message = "storage failure"
        # Act / Assert
        with pytest.raises(YtSyncError):
            raise StorageError(message)

    def test_raise_state_read_error(self) -> None:
        # Arrange
        message = "cannot read state file"
        # Act / Assert
        with pytest.raises(StateReadError, match=message):
            raise StateReadError(message)

    def test_raise_state_write_error(self) -> None:
        # Arrange
        message = "cannot write state file"
        # Act / Assert
        with pytest.raises(StateWriteError, match=message):
            raise StateWriteError(message)

    def test_raise_state_corrupted_error(self) -> None:
        # Arrange
        message = "state file JSON is invalid"
        # Act / Assert
        with pytest.raises(StateCorruptedError, match=message):
            raise StateCorruptedError(message)

    def test_state_read_error_caught_as_storage_error(self) -> None:
        with pytest.raises(StorageError):
            raise StateReadError("read error")

    def test_state_write_error_caught_as_storage_error(self) -> None:
        with pytest.raises(StorageError):
            raise StateWriteError("write error")

    def test_state_corrupted_error_caught_as_storage_error(self) -> None:
        with pytest.raises(StorageError):
            raise StateCorruptedError("corrupted")
