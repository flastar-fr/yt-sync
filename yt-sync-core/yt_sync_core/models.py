"""Modèles Pydantic v2 pour yt_sync_core."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class TrackStatus(str, Enum):
    """Statut de synchronisation d'une piste."""

    PENDING = "pending"
    DOWNLOADED = "downloaded"
    ERROR = "error"
    SKIPPED = "skipped"


class TrackSnapshot(BaseModel):
    """Représentation immuable de l'état d'une piste à un instant donné.

    Attributes:
        video_id: Identifiant YouTube unique (non vide).
        title: Titre de la vidéo (non vide).
        status: Statut courant de la piste.
        error_message: Message d'erreur optionnel, présent uniquement si
            ``status == TrackStatus.ERROR``.
    """

    video_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    status: TrackStatus = TrackStatus.PENDING
    error_message: str | None = None

    model_config = {"frozen": True}


class SyncState(BaseModel):
    """État global de synchronisation d'un dossier cible.

    Attributes:
        tracks: Dictionnaire ``{video_id: TrackSnapshot}``.
    """

    tracks: dict[str, TrackSnapshot] = Field(default_factory=dict)

    model_config = {"frozen": True}
