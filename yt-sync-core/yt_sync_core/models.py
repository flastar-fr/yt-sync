"""Pydantic v2 models for yt_sync_core."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


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


class SyncState(BaseModel):
    """Global synchronization state for a target directory.

    Attributes:
        tracks: Mapping of video_id to TrackSnapshot.
    """

    tracks: dict[str, TrackSnapshot] = Field(default_factory=dict)

    model_config = {"frozen": True}
