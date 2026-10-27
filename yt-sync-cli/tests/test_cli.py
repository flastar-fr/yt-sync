"""Unit tests for the yt-sync command-line interface."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from yt_sync_cli import __version__
from yt_sync_cli.__main__ import build_parser, run_sync
from yt_sync_core import __version__ as core_version
from yt_sync_core.exceptions import ExtractionError
from yt_sync_core.extractor import RemoteTrack
from yt_sync_core.models import TrackStatus
from yt_sync_core.storage import STATE_FILENAME, StateManager


def test_cli_version() -> None:
    assert __version__ == "0.1.0"
    assert core_version == "0.1.0"


class TestCLIParser:
    """Validate command-line argument parsing."""

    def test_parser_with_required_args(self) -> None:
        # Arrange
        parser = build_parser()
        args_list = ["/tmp/music", "https://youtube.com/playlist?list=123"]

        # Act
        args = parser.parse_args(args_list)

        # Assert
        assert args.target_dir == Path("/tmp/music")
        assert args.playlist_url == "https://youtube.com/playlist?list=123"
        assert args.dry_run is False

    def test_parser_with_dry_run_flag(self) -> None:
        # Arrange
        parser = build_parser()
        args_list = ["/tmp/music", "https://youtube.com/playlist?list=123", "--dry-run"]

        # Act
        args = parser.parse_args(args_list)

        # Assert
        assert args.dry_run is True

    def test_parser_default_no_normalize_is_false(self) -> None:
        # Arrange
        parser = build_parser()
        args_list = ["/tmp/music"]

        # Act
        args = parser.parse_args(args_list)

        # Assert
        assert args.no_normalize is False

    def test_parser_with_no_normalize_flag(self) -> None:
        # Arrange
        parser = build_parser()
        args_list = ["/tmp/music", "--no-normalize"]

        # Act
        args = parser.parse_args(args_list)

        # Assert
        assert args.no_normalize is True

    def test_parser_default_format_is_m4a(self) -> None:
        # Arrange
        parser = build_parser()
        args_list = ["/tmp/music"]

        # Act
        args = parser.parse_args(args_list)

        # Assert
        assert args.format == "m4a"

    def test_parser_with_mp3_format(self) -> None:
        # Arrange
        parser = build_parser()
        args_list = ["/tmp/music", "--format", "mp3"]

        # Act
        args = parser.parse_args(args_list)

        # Assert
        assert args.format == "mp3"

    def test_parser_with_invalid_format_raises(self) -> None:
        # Arrange
        parser = build_parser()
        args_list = ["/tmp/music", "--format", "wav"]

        # Act / Assert
        with pytest.raises(SystemExit):
            parser.parse_args(args_list)


class TestCLIRunSync:
    """Validate run_sync execution flow."""

    def test_run_sync_creates_directory_and_saves_state(self, tmp_path: Path) -> None:
        # Arrange
        target_dir = tmp_path / "downloads"
        mock_extractor = MagicMock()
        mock_extractor.fetch_playlist.return_value = [
            RemoteTrack(video_id="id1", title="Track 1", is_available=True)
        ]

        # Act
        exit_code = run_sync(
            target_dir=target_dir,
            playlist_url="https://youtube.com/playlist?list=xyz",
            extractor=mock_extractor,
        )

        # Assert
        assert exit_code == 0
        assert target_dir.exists()
        mock_extractor.download_tracks.assert_called_once()
        state_file = target_dir / STATE_FILENAME
        assert state_file.exists()
        manager = StateManager(target_dir=target_dir)
        state = manager.load()
        assert "id1" in state.tracks
        assert state.tracks["id1"].status == TrackStatus.DOWNLOADED

    def test_run_sync_dry_run_does_not_download_or_save(self, tmp_path: Path) -> None:
        # Arrange
        target_dir = tmp_path / "downloads_dry"
        mock_extractor = MagicMock()
        mock_extractor.fetch_playlist.return_value = [
            RemoteTrack(video_id="id1", title="Track 1", is_available=True)
        ]

        # Act
        exit_code = run_sync(
            target_dir=target_dir,
            playlist_url="https://youtube.com/playlist?list=xyz",
            dry_run=True,
            extractor=mock_extractor,
        )

        # Assert
        assert exit_code == 0
        mock_extractor.download_tracks.assert_not_called()
        state_file = target_dir / STATE_FILENAME
        assert not state_file.exists()

    def test_run_sync_handles_unavailable_tracks(self, tmp_path: Path) -> None:
        # Arrange
        target_dir = tmp_path / "downloads_unavail"
        mock_extractor = MagicMock()
        mock_extractor.fetch_playlist.return_value = [
            RemoteTrack(video_id="priv1", title="[Private video]", is_available=False)
        ]

        # Act
        exit_code = run_sync(
            target_dir=target_dir,
            playlist_url="https://youtube.com/playlist?list=xyz",
            extractor=mock_extractor,
        )

        # Assert
        assert exit_code == 0
        mock_extractor.download_tracks.assert_not_called()
        manager = StateManager(target_dir=target_dir)
        state = manager.load()
        assert "priv1" in state.tracks
        assert state.tracks["priv1"].status == TrackStatus.ERROR

    def test_run_sync_extraction_error_returns_code_1(self, tmp_path: Path) -> None:
        # Arrange
        target_dir = tmp_path / "downloads_err"
        mock_extractor = MagicMock()
        mock_extractor.fetch_playlist.side_effect = ExtractionError("Extraction failed")

        # Act
        exit_code = run_sync(
            target_dir=target_dir,
            playlist_url="https://invalid-url",
            extractor=mock_extractor,
        )

        # Assert
        assert exit_code == 1

    def test_run_sync_with_no_normalize_flag_disables_loudnorm_and_saves_config(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        target_dir = tmp_path / "downloads_no_norm"
        mock_extractor = MagicMock()
        mock_extractor.fetch_playlist.return_value = [
            RemoteTrack(video_id="id1", title="Track 1", is_available=True)
        ]

        # Act
        exit_code = run_sync(
            target_dir=target_dir,
            playlist_url="https://youtube.com/playlist?list=xyz",
            normalize_audio=False,
            extractor=mock_extractor,
        )

        # Assert
        assert exit_code == 0
        call_kwargs = mock_extractor.download_tracks.call_args[1]
        assert call_kwargs["normalize_audio"] is False
        manager = StateManager(target_dir=target_dir)
        state = manager.load()
        assert state.config.normalize_audio is False

    def test_run_sync_with_mp3_format_passes_format_and_saves_config(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        target_dir = tmp_path / "downloads_mp3"
        mock_extractor = MagicMock()
        mock_extractor.fetch_playlist.return_value = [
            RemoteTrack(video_id="id1", title="Track 1", is_available=True)
        ]

        # Act
        exit_code = run_sync(
            target_dir=target_dir,
            playlist_url="https://youtube.com/playlist?list=xyz",
            audio_format="mp3",
            extractor=mock_extractor,
        )

        # Assert
        assert exit_code == 0
        call_kwargs = mock_extractor.download_tracks.call_args[1]
        assert call_kwargs["audio_format"] == "mp3"
        manager = StateManager(target_dir=target_dir)
        state = manager.load()
        assert state.config.audio_format == "mp3"
