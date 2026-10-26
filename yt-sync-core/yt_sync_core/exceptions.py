"""Hiérarchie d'exceptions métier pour yt_sync_core."""

from __future__ import annotations


class YtSyncError(Exception):
    """Exception racine pour toutes les erreurs de yt-sync."""


class StorageError(YtSyncError):
    """Erreur liée à la persistence de l'état."""


class StateReadError(StorageError):
    """Impossible de lire le fichier d'état (permissions, I/O…)."""


class StateWriteError(StorageError):
    """Impossible d'écrire le fichier d'état (permissions, disque plein…)."""


class StateCorruptedError(StorageError):
    """Le fichier d'état existe mais son contenu est invalide (JSON malformé, schéma incorrect…)."""
