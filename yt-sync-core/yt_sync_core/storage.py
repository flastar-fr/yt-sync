"""Persistence de l'état de synchronisation (StateManager)."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import ValidationError

from yt_sync_core.exceptions import StateCorruptedError, StateReadError, StateWriteError
from yt_sync_core.models import SyncState

STATE_FILENAME: str = ".yt_sync_state.json"


class StateManager:
    """Gère la lecture et l'écriture de l'état dans un dossier cible.

    Le fichier d'état est un fichier JSON caché nommé :data:`STATE_FILENAME`
    placé directement à la racine du ``target_dir``.

    Args:
        target_dir: Chemin vers le dossier cible (doit exister).

    Raises:
        FileNotFoundError: Si ``target_dir`` n'existe pas.
    """

    def __init__(self, *, target_dir: Path) -> None:
        if not target_dir.exists():
            raise FileNotFoundError(f"Le dossier cible n'existe pas : {target_dir}")
        self._target_dir = target_dir

    # ------------------------------------------------------------------
    # Propriétés publiques
    # ------------------------------------------------------------------

    @property
    def target_dir(self) -> Path:
        """Dossier cible surveillé par ce manager."""
        return self._target_dir

    @property
    def state_file_path(self) -> Path:
        """Chemin absolu vers le fichier d'état."""
        return self._target_dir / STATE_FILENAME

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def load(self) -> SyncState:
        """Charge l'état depuis le fichier JSON.

        Returns:
            Un :class:`SyncState` vide si le fichier est absent,
            ou l'état désérialisé depuis le fichier.

        Raises:
            StateReadError: Si le fichier existe mais ne peut pas être lu
                (problème de permissions ou d'I/O).
            StateCorruptedError: Si le fichier existe mais son contenu est
                invalide (JSON malformé ou schéma Pydantic non respecté).
        """
        path = self.state_file_path

        if not path.exists():
            return SyncState()

        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise StateReadError(f"Impossible de lire {path}: {exc}") from exc

        try:
            return SyncState.model_validate_json(raw)
        except (ValueError, ValidationError) as exc:
            raise StateCorruptedError(
                f"Fichier d'état corrompu ({path}): {exc}"
            ) from exc

    def save(self, state: SyncState) -> None:
        """Persiste l'état dans le fichier JSON.

        Args:
            state: L'état à sauvegarder.

        Raises:
            StateWriteError: Si l'écriture échoue (permissions, disque plein…).
        """
        path = self.state_file_path
        json_bytes = state.model_dump_json(indent=2).encode("utf-8")

        try:
            # Écriture atomique via un fichier temporaire dans le même dossier
            tmp_path = path.with_suffix(".tmp")
            tmp_path.write_bytes(json_bytes)
            os.replace(tmp_path, path)
        except OSError as exc:
            raise StateWriteError(f"Impossible d'écrire {path}: {exc}") from exc
