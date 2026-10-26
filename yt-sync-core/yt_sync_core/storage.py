"""Persistence layer for synchronization state (StateManager)."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import ValidationError

from yt_sync_core.exceptions import StateCorruptedError, StateReadError, StateWriteError
from yt_sync_core.models import SyncState

STATE_FILENAME: str = ".yt_sync_state.json"


class StateManager:
    """Manages reading and writing state in a target directory.

    The state file is a hidden JSON file named :data:`STATE_FILENAME`
    located directly at the root of ``target_dir``.

    Args:
        target_dir: Path to the target directory (must exist).

    Raises:
        FileNotFoundError: If ``target_dir`` does not exist.
    """

    def __init__(self, *, target_dir: Path) -> None:
        if not target_dir.exists():
            raise FileNotFoundError(f"Target directory does not exist: {target_dir}")
        self._target_dir = target_dir

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def target_dir(self) -> Path:
        """Target directory managed by this instance."""
        return self._target_dir

    @property
    def state_file_path(self) -> Path:
        """Absolute path to the state file."""
        return self._target_dir / STATE_FILENAME

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> SyncState:
        """Load state from the JSON file.

        Returns:
            An empty :class:`SyncState` if the file does not exist,
            or the deserialized state from disk.

        Raises:
            StateReadError: If the file exists but cannot be read.
            StateCorruptedError: If the file contains invalid JSON or schema violations.
        """
        path = self.state_file_path

        if not path.exists():
            return SyncState()

        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise StateReadError(f"Cannot read state file {path}: {exc}") from exc

        try:
            return SyncState.model_validate_json(raw)
        except (ValueError, ValidationError) as exc:
            raise StateCorruptedError(
                f"Corrupted state file ({path}): {exc}"
            ) from exc

    def save(self, state: SyncState) -> None:
        """Persist state to the JSON file.

        Args:
            state: The state instance to persist.

        Raises:
            StateWriteError: If writing to disk fails.
        """
        path = self.state_file_path
        json_bytes = state.model_dump_json(indent=2).encode("utf-8")

        try:
            # Atomic write via a temporary file in the same directory
            tmp_path = path.with_suffix(".tmp")
            tmp_path.write_bytes(json_bytes)
            os.replace(tmp_path, path)
        except OSError as exc:
            raise StateWriteError(f"Cannot write state file {path}: {exc}") from exc
