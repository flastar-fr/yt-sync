"""Tests unitaires et d'intégration pour l'application Web FastAPI."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from yt_sync_core import __version__ as core_version
from yt_sync_core.diff_engine import DiffResult
from yt_sync_core.extractor import RemoteTrack
from yt_sync_core.models import TrackSnapshot, TrackStatus
from yt_sync_core.storage import STATE_FILENAME, StateManager
from yt_sync_web import __version__
from yt_sync_web.main import app


def test_web_version() -> None:
    assert __version__ == "0.1.0"
    assert core_version == "0.1.0"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestWebRoutes:
    """Vérifie le comportement des routes FastAPI."""

    def test_get_index_returns_html_page_with_htmx2(self, client: TestClient) -> None:
        # Act
        response = client.get("/")

        # Assert
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "htmx.org@2." in response.text
        assert 'hx-post="/analyze"' in response.text

    @patch("yt_sync_web.main.PlaylistExtractor")
    def test_post_analyze_returns_report_fragment(
        self,
        mock_extractor_class: MagicMock,
        client: TestClient,
        tmp_path: Path,
    ) -> None:
        # Arrange
        mock_extractor = mock_extractor_class.return_value
        mock_extractor.fetch_playlist.return_value = [
            RemoteTrack(video_id="new1", title="New Song", is_available=True),
            RemoteTrack(video_id="unavail1", title="[Private]", is_available=False),
        ]
        target_dir = tmp_path / "music_web"

        # Act
        response = client.post(
            "/analyze",
            data={
                "target_dir": str(target_dir),
                "playlist_url": "https://youtube.com/playlist?list=fake",
            },
        )

        # Assert
        assert response.status_code == 200
        assert "Rapport Différentiel" in response.text
        assert "New Song" in response.text
        assert "Pistes inaccessibles" in response.text
        assert 'hx-post="/sync"' in response.text

    @patch("yt_sync_web.main.PlaylistExtractor")
    def test_post_sync_executes_download_and_saves_state(
        self,
        mock_extractor_class: MagicMock,
        client: TestClient,
        tmp_path: Path,
    ) -> None:
        # Arrange
        mock_extractor = mock_extractor_class.return_value
        mock_extractor.fetch_playlist.return_value = [
            RemoteTrack(video_id="track10", title="Track 10", is_available=True)
        ]
        target_dir = tmp_path / "sync_web_dest"

        # Act
        response = client.post(
            "/sync",
            data={
                "target_dir": str(target_dir),
                "playlist_url": "https://youtube.com/playlist?list=fake",
            },
        )

        # Assert
        assert response.status_code == 200
        assert "Synchronisation terminée avec succès" in response.text
        mock_extractor.download_tracks.assert_called_once()
        state_file = target_dir / STATE_FILENAME
        assert state_file.exists()
        manager = StateManager(target_dir=target_dir)
        state = manager.load()
        assert "track10" in state.tracks
        assert state.tracks["track10"].status == TrackStatus.DOWNLOADED

    @patch("yt_sync_web.main.PlaylistExtractor")
    def test_post_analyze_error_returns_error_fragment(
        self,
        mock_extractor_class: MagicMock,
        client: TestClient,
        tmp_path: Path,
    ) -> None:
        # Arrange
        mock_extractor = mock_extractor_class.return_value
        mock_extractor.fetch_playlist.side_effect = RuntimeError("Extraction crashed")
        target_dir = tmp_path / "err_dir"

        # Act
        response = client.post(
            "/analyze",
            data={
                "target_dir": str(target_dir),
                "playlist_url": "https://invalid",
            },
        )

        # Assert
        assert response.status_code == 200
        assert "Une erreur est survenue" in response.text
        assert "Extraction crashed" in response.text
