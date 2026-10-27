"""Unit and integration tests for the folder-scoped FastAPI web application."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from yt_sync_core import __version__ as core_version
from yt_sync_core.extractor import RemoteTrack
from yt_sync_core.models import SyncConfig, SyncState, TrackSnapshot, TrackStatus
from yt_sync_core.storage import STATE_FILENAME, StateManager
from yt_sync_web import __version__
from yt_sync_web.__main__ import app


def test_web_version() -> None:
    assert __version__ == "0.1.0"
    assert core_version == "0.1.0"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestWebDashboard:
    """Validate folder-scoped dashboard lifecycle and HTMX 2 endpoints."""

    def test_get_index_shows_init_form_when_no_state_exists(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        # Arrange: Scoped to an empty folder without .yt_sync_state.json
        empty_folder = tmp_path / "empty_music"
        empty_folder.mkdir()
        app.state.target_dir = empty_folder

        # Act
        response = client.get("/")

        # Assert
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "htmx.org@2." in response.text
        assert "Initialize Folder Synchronization" in response.text
        assert "Audio Normalization (EBU R128)" in response.text
        assert 'name="audio_format"' in response.text
        assert 'hx-post="/initialize"' in response.text

    @patch("yt_sync_web.__main__.PlaylistExtractor")
    def test_get_index_loads_local_state_without_network_when_state_exists(
        self, mock_extractor_class: MagicMock, client: TestClient, tmp_path: Path
    ) -> None:
        # Arrange: Folder with pre-existing .yt_sync_state.json
        music_folder = tmp_path / "my_music"
        music_folder.mkdir()
        app.state.target_dir = music_folder

        manager = StateManager(target_dir=music_folder)
        existing_state = SyncState(
            playlist_url="https://youtube.com/playlist?list=TEST",
            playlist_name="Saved Local Playlist",
            last_synced_at="2026-10-26 12:00:00 UTC",
            tracks={
                "vid1": TrackSnapshot(video_id="vid1", title="Already Here", status=TrackStatus.DOWNLOADED),
                "vid2": TrackSnapshot(
                    video_id="vid2",
                    title="Archived Old Song",
                    status=TrackStatus.ERROR,
                    error_message="Unavailable on YouTube",
                ),
            },
        )
        manager.save(existing_state)

        # Act
        response = client.get("/")

        # Assert: Loaded purely from local state with ZERO network calls!
        assert response.status_code == 200
        mock_extractor_class.assert_not_called()
        assert "Saved Local Playlist" in response.text
        assert "Already Here" in response.text
        assert "Archived Old Song" in response.text
        assert "Check for Updates" in response.text
        assert 'hx-post="/refresh"' in response.text
        assert "EBU R128 Enabled" in response.text

    @patch("yt_sync_web.__main__.PlaylistExtractor")
    def test_post_initialize_creates_state_and_returns_dashboard(
        self, mock_extractor_class: MagicMock, client: TestClient, tmp_path: Path
    ) -> None:
        # Arrange
        init_folder = tmp_path / "init_music"
        init_folder.mkdir()
        app.state.target_dir = init_folder

        mock_extractor = mock_extractor_class.return_value
        mock_extractor.fetch_playlist_details.return_value = (
            "Rock Classics",
            [
                RemoteTrack(video_id="rk1", title="Bohemian Rhapsody", is_available=True),
                RemoteTrack(video_id="rk2", title="[Private Video]", is_available=False),
            ],
        )

        # Act
        response = client.post(
            "/initialize",
            data={"playlist_url": "https://youtube.com/playlist?list=ROCK"},
        )

        # Assert
        assert response.status_code == 200
        assert "Rock Classics" in response.text
        assert "Bohemian Rhapsody" in response.text
        state_file = init_folder / STATE_FILENAME
        assert state_file.exists()
        loaded = StateManager(target_dir=init_folder).load()
        assert loaded.playlist_name == "Rock Classics"
        assert "rk1" in loaded.tracks
        assert loaded.tracks["rk1"].status == TrackStatus.PENDING
        assert loaded.tracks["rk2"].status == TrackStatus.ERROR

    @patch("yt_sync_web.__main__.PlaylistExtractor")
    def test_post_refresh_manual_polling_returns_diff_dashboard(
        self, mock_extractor_class: MagicMock, client: TestClient, tmp_path: Path
    ) -> None:
        # Arrange: Setup directory with 1 downloaded track
        refresh_folder = tmp_path / "refresh_music"
        refresh_folder.mkdir()
        app.state.target_dir = refresh_folder

        manager = StateManager(target_dir=refresh_folder)
        manager.save(
            SyncState(
                playlist_url="https://youtube.com/playlist?list=PL_TEST",
                playlist_name="Electronic Gems",
                tracks={
                    "el1": TrackSnapshot(video_id="el1", title="Existing Track", status=TrackStatus.DOWNLOADED),
                },
            )
        )

        mock_extractor = mock_extractor_class.return_value
        mock_extractor.fetch_playlist_details.return_value = (
            "Electronic Gems",
            [
                RemoteTrack(video_id="el1", title="Existing Track", is_available=True),
                RemoteTrack(video_id="el2", title="New Drop", is_available=True),
            ],
        )

        # Act: Manual refresh button clicked
        response = client.post("/refresh")

        # Assert
        assert response.status_code == 200
        assert "Existing Track" in response.text
        assert "New Drop" in response.text
        assert "Downloaded" in response.text
        assert "New" in response.text
        assert 'Sync Missing Tracks' in response.text

    @patch("yt_sync_web.__main__.PlaylistExtractor")
    def test_post_sync_downloads_missing_tracks_and_updates_state(
        self, mock_extractor_class: MagicMock, client: TestClient, tmp_path: Path
    ) -> None:
        # Arrange
        sync_folder = tmp_path / "sync_music"
        sync_folder.mkdir()
        app.state.target_dir = sync_folder

        manager = StateManager(target_dir=sync_folder)
        manager.save(
            SyncState(
                playlist_url="https://youtube.com/playlist?list=PL_TEST",
                playlist_name="My Playlist",
                tracks={},
            )
        )

        mock_extractor = mock_extractor_class.return_value
        mock_extractor.fetch_playlist_details.return_value = (
            "My Playlist",
            [RemoteTrack(video_id="new1", title="Track One", is_available=True)],
        )

        # Act
        response = client.post("/sync")

        # Assert
        assert response.status_code == 200
        mock_extractor.download_tracks.assert_called_once_with(["new1"], output_dir=str(sync_folder))
        loaded = manager.load()
        assert loaded.tracks["new1"].status == TrackStatus.DOWNLOADED
        assert loaded.last_synced_at is not None

    @patch("yt_sync_web.__main__.PlaylistExtractor")
    def test_post_sync_with_normalization_disabled_via_form(
        self, mock_extractor_class: MagicMock, client: TestClient, tmp_path: Path
    ) -> None:
        # Arrange
        sync_folder = tmp_path / "sync_music_no_norm"
        sync_folder.mkdir()
        app.state.target_dir = sync_folder

        manager = StateManager(target_dir=sync_folder)
        manager.save(
            SyncState(
                playlist_url="https://youtube.com/playlist?list=PL_TEST",
                playlist_name="My Playlist",
                tracks={},
                config=SyncConfig(normalize_audio=True),
            )
        )

        mock_extractor = mock_extractor_class.return_value
        mock_extractor.fetch_playlist_details.return_value = (
            "My Playlist",
            [RemoteTrack(video_id="new1", title="Track One", is_available=True)],
        )

        # Act: Submitting sync form with checkbox unticked (only sync_form sent)
        response = client.post("/sync", data={"sync_form": "1"})

        # Assert
        assert response.status_code == 200
        mock_extractor_class.assert_called_with(normalize_audio=False, audio_format="m4a")
        loaded = manager.load()
        assert loaded.config.normalize_audio is False
        assert "Audio Normalization (EBU R128)" in response.text

    @patch("yt_sync_web.__main__.PlaylistExtractor")
    def test_post_sync_with_audio_format_mp3(
        self, mock_extractor_class: MagicMock, client: TestClient, tmp_path: Path
    ) -> None:
        # Arrange
        sync_folder = tmp_path / "sync_music_mp3"
        sync_folder.mkdir()
        app.state.target_dir = sync_folder

        manager = StateManager(target_dir=sync_folder)
        manager.save(
            SyncState(
                playlist_url="https://youtube.com/playlist?list=PL_TEST",
                playlist_name="My Playlist",
                tracks={},
                config=SyncConfig(audio_format="m4a"),
            )
        )

        mock_extractor = mock_extractor_class.return_value
        mock_extractor.fetch_playlist_details.return_value = (
            "My Playlist",
            [RemoteTrack(video_id="new1", title="Track One", is_available=True)],
        )

        # Act
        response = client.post(
            "/sync",
            data={"audio_format": "mp3", "sync_form": "1", "normalize_audio": "true"},
        )

        # Assert
        assert response.status_code == 200
        mock_extractor_class.assert_called_with(normalize_audio=True, audio_format="mp3")
        loaded = manager.load()
        assert loaded.config.audio_format == "mp3"
        assert "mp3" in response.text.lower()

    def test_post_ignore_track_marks_status_as_skipped(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        # Arrange
        ignore_folder = tmp_path / "ignore_music"
        ignore_folder.mkdir()
        app.state.target_dir = ignore_folder

        manager = StateManager(target_dir=ignore_folder)
        manager.save(
            SyncState(
                playlist_url="https://youtube.com/playlist?list=PL_TEST",
                playlist_name="Test Playlist",
                tracks={
                    "del1": TrackSnapshot(
                        video_id="del1",
                        title="Deleted Song Title",
                        status=TrackStatus.ERROR,
                        error_message="Unavailable on YouTube",
                    )
                },
            )
        )

        # Act: User clicks "Mark as Skipped"
        response = client.post("/ignore/del1")

        # Assert
        assert response.status_code == 200
        loaded = manager.load()
        assert loaded.tracks["del1"].status == TrackStatus.SKIPPED
        assert "Skipped" in response.text
