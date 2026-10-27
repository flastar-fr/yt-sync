"""Pydantic v2 models for yt_sync_core."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class TrackStatus(str, Enum):
    """Synchronization status of a track."""

    PENDING = "pending"
    DOWNLOADED = "downloaded"
    ERROR = "error"
    SKIPPED = "skipped"


class TrackSnapshot(BaseModel):
    """Immutable representation of a track's state at a given time.

    Attributes:
        video_id: Unique YouTube video identifier (non-empty).
        title: Title of the video (non-empty).
        status: Current synchronization status.
        error_message: Optional error message, populated when status is ERROR.
    """

    video_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    status: TrackStatus = TrackStatus.PENDING
    error_message: str | None = None

    model_config = {"frozen": True}


class SyncConfig(BaseModel):
    """Configuration options for synchronization and audio processing.

    Attributes:
        normalize_audio: Whether to normalize loudness via EBU R128 loudnorm filter.
        target_lufs: Target integrated loudness in LUFS (standard: -14.0 for streaming/web).
        true_peak: Maximum true peak level in dBTP (standard: -1.5 dBTP).
    """

    normalize_audio: bool = True
    target_lufs: float = -14.0
    true_peak: float = -1.5

    model_config = {"frozen": True}


class SyncState(BaseModel):
    """Global synchronization state for a target directory.

    Attributes:
        playlist_url: Optional YouTube playlist URL associated with this folder.
        playlist_name: Optional playlist title.
        last_synced_at: Optional timestamp of the last synchronization.
        tracks: Mapping of video_id to TrackSnapshot.
        config: Synchronization and audio processing configuration.
    """

    playlist_url: str | None = None
    playlist_name: str | None = None
    last_synced_at: str | None = None
    tracks: dict[str, TrackSnapshot] = Field(default_factory=dict)
    config: SyncConfig = Field(default_factory=SyncConfig)

    model_config = {"frozen": True}

    @model_validator(mode="before")
    @classmethod
    def _migrate_flat_config(cls, data: Any) -> Any:
        if isinstance(data, dict):
            flat_keys = ("normalize_audio", "target_lufs", "true_peak")
            if any(k in data for k in flat_keys):
                existing_config = data.get("config")
                cfg_dict: dict[str, Any] = (
                    existing_config.model_dump()
                    if isinstance(existing_config, BaseModel)
                    else (existing_config or {})
                )
                if not isinstance(cfg_dict, dict):
                    cfg_dict = {}
                else:
                    cfg_dict = dict(cfg_dict)
                for k in flat_keys:
                    if k in data:
                        cfg_dict[k] = data.pop(k)
                data["config"] = cfg_dict
        return data

    @property
    def normalize_audio(self) -> bool:
        """Convenience property delegating to config.normalize_audio."""
        return self.config.normalize_audio

    @property
    def target_lufs(self) -> float:
        """Convenience property delegating to config.target_lufs."""
        return self.config.target_lufs

    @property
    def true_peak(self) -> float:
        """Convenience property delegating to config.true_peak."""
        return self.config.true_peak
