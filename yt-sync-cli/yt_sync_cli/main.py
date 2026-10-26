"""Interface en ligne de commande (CLI) pour yt-sync."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from yt_sync_core.diff_engine import DiffEngine, DiffResult
from yt_sync_core.exceptions import ExtractionError, StorageError, YtSyncError
from yt_sync_core.extractor import PlaylistExtractor
from yt_sync_core.models import SyncState, TrackSnapshot, TrackStatus
from yt_sync_core.storage import StateManager


def build_parser() -> argparse.ArgumentParser:
    """Construit et configure l'analyseur d'arguments CLI."""
    parser = argparse.ArgumentParser(
        prog="yt-sync",
        description="Synchroniseur de playlists YouTube vers un dossier local.",
    )
    parser.add_argument(
        "target_dir",
        type=Path,
        help="Dossier cible local où stocker les fichiers audio et l'état.",
    )
    parser.add_argument(
        "playlist_url",
        type=str,
        help="URL de la playlist YouTube à synchroniser.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche uniquement le rapport de diff sans lancer de téléchargement.",
    )
    return parser


def display_report(diff: DiffResult) -> None:
    """Affiche un résumé clair et lisible des pistes analysées."""
    print("\n" + "=" * 60)
    print("📊 RAPPORT DE SYNCHRONISATION")
    print("=" * 60)
    print(f"  • Déjà téléchargées / stables : {len(diff.already_downloaded)}")
    print(f"  • Nouvelles pistes à télécharger : {len(diff.new_tracks)}")
    print(f"  • Pistes supprimées de la playlist : {len(diff.removed_tracks)}")
    print(f"  • Pistes inaccessibles / privées : {len(diff.unavailable_tracks)}")
    print("=" * 60)

    if diff.new_tracks:
        print("\n📥 NOUVELLES PISTES :")
        for track in diff.new_tracks:
            print(f"  [+] [{track.video_id}] {track.title}")

    if diff.unavailable_tracks:
        print("\n⚠️ PISTES INACCESSIBLES (Privées / Supprimées) :")
        for track in diff.unavailable_tracks:
            print(f"  [!] [{track.video_id}] {track.title}")
        print("  💡 Proposition d'action :")
        print("     Ces pistes ne peuvent être récupérées depuis YouTube.")
        print("     Si vous possédez déjà une copie locale, conservez-la.")
        print("     Sinon, retirez-les de votre playlist YouTube pour nettoyer l'état.")

    if diff.removed_tracks:
        print("\n🗑️ PISTES RETIRÉES DE LA PLAYLIST DISTANTE :")
        for track in diff.removed_tracks:
            print(f"  [-] [{track.video_id}] {track.title}")
        print("  💡 Proposition d'action : Les fichiers restent conservés localement par sécurité.")


def progress_hook(status_dict: dict[str, Any]) -> None:
    """Callback pour afficher la progression des téléchargements yt-dlp."""
    status = status_dict.get("status")
    if status == "downloading":
        filename = status_dict.get("filename", "")
        percent = status_dict.get("_percent_str", "").strip()
        speed = status_dict.get("_speed_str", "").strip()
        eta = status_dict.get("_eta_str", "").strip()
        # Affiche une ligne compacte de progression
        clean_name = Path(filename).name if filename else "en cours"
        sys.stdout.write(f"\r⏳ Téléchargement: {clean_name[:40]}... {percent} à {speed} (ETA {eta})")
        sys.stdout.flush()
    elif status == "finished":
        sys.stdout.write("\n✅ Téléchargement terminé, conversion en cours...\n")
        sys.stdout.flush()


def run_sync(
    target_dir: Path,
    playlist_url: str,
    *,
    dry_run: bool = False,
    extractor: PlaylistExtractor | None = None,
) -> int:
    """Exécute le workflow complet de synchronisation."""
    if extractor is None:
        extractor = PlaylistExtractor()

    # 1. Validation du dossier cible
    target_dir = target_dir.resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    state_manager = StateManager(target_dir=target_dir)

    print(f"📁 Dossier cible : {target_dir}")
    print(f"🔗 Playlist : {playlist_url}")

    # 2. Chargement de l'état local
    try:
        current_state = state_manager.load()
    except StorageError as exc:
        print(f"❌ Erreur lors du chargement de l'état local : {exc}", file=sys.stderr)
        return 1

    # 3. Extraction distante & Moteur de diff
    print("🔍 Analyse de la playlist distante...")
    try:
        remote_tracks = extractor.fetch_playlist(playlist_url)
    except ExtractionError as exc:
        print(f"❌ Erreur lors de l'extraction de la playlist : {exc}", file=sys.stderr)
        return 1

    diff_engine = DiffEngine()
    diff = diff_engine.compute(remote_tracks=remote_tracks, current_state=current_state)

    # 4. Affichage du rapport
    display_report(diff)

    if dry_run:
        print("\n[DRY RUN] Aucune modification ni téléchargement effectué.")
        return 0

    # 5. Téléchargement des nouvelles pistes
    updated_tracks: dict[str, TrackSnapshot] = dict(current_state.tracks)

    # Enregistrer les pistes inaccessibles avec leur statut
    for unavail in diff.unavailable_tracks:
        updated_tracks[unavail.video_id] = unavail

    if diff.new_tracks:
        print(f"\n🚀 Lancement du téléchargement de {len(diff.new_tracks)} piste(s)...")
        ids_to_download = [t.video_id for t in diff.new_tracks]
        try:
            extractor.download_tracks(
                ids_to_download,
                output_dir=str(target_dir),
                progress_callback=progress_hook,
            )
            # Marquer les nouvelles pistes comme DOWNLOADED
            for new_t in diff.new_tracks:
                updated_tracks[new_t.video_id] = TrackSnapshot(
                    video_id=new_t.video_id,
                    title=new_t.title,
                    status=TrackStatus.DOWNLOADED,
                )
        except Exception as exc:
            print(f"\n❌ Erreur pendant le téléchargement : {exc}", file=sys.stderr)
            # Marquer les pistes en erreur
            for new_t in diff.new_tracks:
                if new_t.video_id not in updated_tracks or updated_tracks[new_t.video_id].status != TrackStatus.DOWNLOADED:
                    updated_tracks[new_t.video_id] = TrackSnapshot(
                        video_id=new_t.video_id,
                        title=new_t.title,
                        status=TrackStatus.ERROR,
                        error_message=str(exc),
                    )
    else:
        print("\n✨ Rien à télécharger, votre dossier est à jour !")

    # 6. Sauvegarde de l'état mis à jour
    new_state = SyncState(tracks=updated_tracks)
    try:
        state_manager.save(new_state)
        print(f"💾 État sauvegardé avec succès ({len(updated_tracks)} piste(s) indexée(s)).")
    except StorageError as exc:
        print(f"❌ Erreur lors de la sauvegarde de l'état : {exc}", file=sys.stderr)
        return 1

    return 0


def main(argv: list[str] | None = None) -> None:
    """Point d'entrée principal du CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    exit_code = run_sync(
        target_dir=args.target_dir,
        playlist_url=args.playlist_url,
        dry_run=args.dry_run,
    )
    if exit_code != 0:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
