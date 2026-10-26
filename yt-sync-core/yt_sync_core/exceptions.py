"""Business exception hierarchy for yt_sync_core."""

from __future__ import annotations


class YtSyncError(Exception):
    """Base exception for all yt-sync errors."""


class StorageError(YtSyncError):
    """Exception related to state persistence."""


class StateReadError(StorageError):
    """Raised when the state file cannot be read (permissions, I/O errors...)."""


class StateWriteError(StorageError):
    """Raised when the state file cannot be written (permissions, disk full...)."""


class StateCorruptedError(StorageError):
    """Raised when the state file exists but contains invalid data (corrupted JSON, invalid schema...)."""


class ExtractionError(YtSyncError):
    """Raised when metadata extraction via yt-dlp fails (invalid URL, network error...)."""
