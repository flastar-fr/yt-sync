"""Tests unitaires pour PlaylistExtractor (extractor.py).

Pattern : Arrange-Act-Assert (AAA)
Isolation  : unittest.mock.patch / MagicMock — aucun appel réseau réel.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from yt_sync_core.exceptions import ExtractionError
from yt_sync_core.extractor import PlaylistExtractor, RemoteTrack


# ---------------------------------------------------------------------------
# Helpers / données de test
# ---------------------------------------------------------------------------

PLAYLIST_URL = "https://www.youtube.com/playlist?list=PL_FAKE"

_FAKE_ENTRY_1: dict[str, Any] = {
    "id": "vid001",
    "title": "Track One",
    "availability": "public",
}
_FAKE_ENTRY_2: dict[str, Any] = {
    "id": "vid002",
    "title": "Track Two",
    "availability": "public",
}
_PRIVATE_ENTRY: dict[str, Any] = {
    "id": "vid003",
    "title": "[Private video]",
    "availability": "private",
}
_DELETED_ENTRY: dict[str, Any] = {
    "id": "vid004",
    "title": "[Deleted video]",
    "availability": "unavailable",
}

_FAKE_PLAYLIST_INFO: dict[str, Any] = {
    "id": "PL_FAKE",
    "title": "My Playlist",
    "entries": [_FAKE_ENTRY_1, _FAKE_ENTRY_2],
}


def _make_ydl_mock(info: dict[str, Any] | None = None) -> MagicMock:
    """Retourne un mock de YoutubeDL configuré pour renvoyer ``info``."""
    mock_ydl = MagicMock()
    mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl.__exit__ = MagicMock(return_value=False)
    mock_ydl.extract_info.return_value = info
    return mock_ydl


# ---------------------------------------------------------------------------
# RemoteTrack
# ---------------------------------------------------------------------------


class TestRemoteTrack:
    """Vérifie la structure du dataclass RemoteTrack."""

    def test_remote_track_creation(self) -> None:
        # Arrange / Act
        track = RemoteTrack(video_id="abc", title="My Title")
        # Assert
        assert track.video_id == "abc"
        assert track.title == "My Title"

    def test_remote_track_is_available_by_default(self) -> None:
        track = RemoteTrack(video_id="abc", title="Title")
        assert track.is_available is True

    def test_remote_track_unavailable(self) -> None:
        track = RemoteTrack(video_id="abc", title="[Deleted video]", is_available=False)
        assert track.is_available is False

    def test_two_remote_tracks_with_same_id_are_equal(self) -> None:
        # Arrange
        t1 = RemoteTrack(video_id="x", title="Title")
        t2 = RemoteTrack(video_id="x", title="Title")
        # Assert
        assert t1 == t2


# ---------------------------------------------------------------------------
# PlaylistExtractor — fetch_playlist
# ---------------------------------------------------------------------------


class TestPlaylistExtractorFetchPlaylist:
    """Tests de la méthode fetch_playlist."""

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_fetch_returns_list_of_remote_tracks(self, MockYDL: MagicMock) -> None:
        # Arrange
        MockYDL.return_value = _make_ydl_mock(_FAKE_PLAYLIST_INFO)
        extractor = PlaylistExtractor()
        # Act
        tracks = extractor.fetch_playlist(PLAYLIST_URL)
        # Assert
        assert len(tracks) == 2
        assert all(isinstance(t, RemoteTrack) for t in tracks)

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_fetch_maps_ids_and_titles_correctly(self, MockYDL: MagicMock) -> None:
        # Arrange
        MockYDL.return_value = _make_ydl_mock(_FAKE_PLAYLIST_INFO)
        extractor = PlaylistExtractor()
        # Act
        tracks = extractor.fetch_playlist(PLAYLIST_URL)
        # Assert
        ids = {t.video_id for t in tracks}
        titles = {t.title for t in tracks}
        assert ids == {"vid001", "vid002"}
        assert titles == {"Track One", "Track Two"}

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_fetch_marks_private_entry_as_unavailable(self, MockYDL: MagicMock) -> None:
        # Arrange
        info = {**_FAKE_PLAYLIST_INFO, "entries": [_PRIVATE_ENTRY]}
        MockYDL.return_value = _make_ydl_mock(info)
        extractor = PlaylistExtractor()
        # Act
        tracks = extractor.fetch_playlist(PLAYLIST_URL)
        # Assert
        assert len(tracks) == 1
        assert tracks[0].is_available is False

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_fetch_marks_deleted_entry_as_unavailable(self, MockYDL: MagicMock) -> None:
        # Arrange
        info = {**_FAKE_PLAYLIST_INFO, "entries": [_DELETED_ENTRY]}
        MockYDL.return_value = _make_ydl_mock(info)
        extractor = PlaylistExtractor()
        # Act
        tracks = extractor.fetch_playlist(PLAYLIST_URL)
        # Assert
        assert tracks[0].is_available is False

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_fetch_empty_playlist_returns_empty_list(self, MockYDL: MagicMock) -> None:
        # Arrange
        info = {**_FAKE_PLAYLIST_INFO, "entries": []}
        MockYDL.return_value = _make_ydl_mock(info)
        extractor = PlaylistExtractor()
        # Act
        tracks = extractor.fetch_playlist(PLAYLIST_URL)
        # Assert
        assert tracks == []

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_fetch_raises_extraction_error_when_result_is_none(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        MockYDL.return_value = _make_ydl_mock(None)
        extractor = PlaylistExtractor()
        # Act / Assert
        with pytest.raises(ExtractionError):
            extractor.fetch_playlist(PLAYLIST_URL)

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_fetch_passes_ignoreerrors_option(self, MockYDL: MagicMock) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock(_FAKE_PLAYLIST_INFO)
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor()
        # Act
        extractor.fetch_playlist(PLAYLIST_URL)
        # Assert : le constructeur reçoit bien ignoreerrors=True
        call_kwargs = MockYDL.call_args[0][0]  # premier arg positionnel = opts dict
        assert call_kwargs.get("ignoreerrors") is True

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_fetch_passes_extract_flat_option(self, MockYDL: MagicMock) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock(_FAKE_PLAYLIST_INFO)
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor()
        # Act
        extractor.fetch_playlist(PLAYLIST_URL)
        # Assert
        call_kwargs = MockYDL.call_args[0][0]
        assert call_kwargs.get("extract_flat") is True

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_fetch_calls_extract_info_with_url(self, MockYDL: MagicMock) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock(_FAKE_PLAYLIST_INFO)
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor()
        # Act
        extractor.fetch_playlist(PLAYLIST_URL)
        # Assert
        mock_ydl.extract_info.assert_called_once_with(PLAYLIST_URL, download=False)

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_fetch_playlist_includes_player_client_extractor_args(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock(_FAKE_PLAYLIST_INFO)
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor()
        # Act
        extractor.fetch_playlist(PLAYLIST_URL)
        # Assert
        call_kwargs = MockYDL.call_args[0][0]
        assert "extractor_args" in call_kwargs
        assert call_kwargs["extractor_args"]["youtube"]["player_client"] == ["android", "web"]
        assert "cookiesfrombrowser" not in call_kwargs
        assert "cookiefile" not in call_kwargs

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_fetch_playlist_includes_remote_components_ejs_github(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock(_FAKE_PLAYLIST_INFO)
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor()
        # Act
        extractor.fetch_playlist(PLAYLIST_URL)
        # Assert
        call_kwargs = MockYDL.call_args[0][0]
        assert call_kwargs.get("remote_components") == {"ejs:github"}

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_fetch_playlist_with_cookies_browser(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock(_FAKE_PLAYLIST_INFO)
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor(cookies_browser="firefox")
        # Act
        extractor.fetch_playlist(PLAYLIST_URL)
        # Assert
        call_kwargs = MockYDL.call_args[0][0]
        assert call_kwargs["cookiesfrombrowser"] == ("firefox",)
        assert "cookiefile" not in call_kwargs
        assert call_kwargs.get("extractor_args") == {
            "youtube": {"player_client": ["web"]}
        }

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_fetch_playlist_with_cookies_file(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock(_FAKE_PLAYLIST_INFO)
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor(cookies_file="/path/to/cookies.txt")
        # Act
        extractor.fetch_playlist(PLAYLIST_URL)
        # Assert
        call_kwargs = MockYDL.call_args[0][0]
        assert call_kwargs["cookiefile"] == "/path/to/cookies.txt"
        assert "cookiesfrombrowser" not in call_kwargs
        assert call_kwargs.get("extractor_args") == {
            "youtube": {"player_client": ["web"]}
        }


# ---------------------------------------------------------------------------
# PlaylistExtractor — download_tracks
# ---------------------------------------------------------------------------


class TestPlaylistExtractorDownloadTracks:
    """Tests de la méthode download_tracks."""

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_download_tracks_calls_ydl_download(self, MockYDL: MagicMock) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock()
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor()
        video_ids = ["vid001", "vid002"]
        # Act
        extractor.download_tracks(video_ids, output_dir="/tmp/music")
        # Assert
        mock_ydl.download.assert_called_once()

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_download_tracks_passes_correct_urls(self, MockYDL: MagicMock) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock()
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor()
        video_ids = ["vid001"]
        # Act
        extractor.download_tracks(video_ids, output_dir="/tmp/music")
        # Assert : on vérifie que l'URL YouTube standard est passée
        downloaded_urls: list[str] = mock_ydl.download.call_args[0][0]
        assert "https://www.youtube.com/watch?v=vid001" in downloaded_urls

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_download_tracks_empty_list_does_not_call_download(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock()
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor()
        # Act
        extractor.download_tracks([], output_dir="/tmp/music")
        # Assert
        mock_ydl.download.assert_not_called()

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_download_tracks_progress_callback_is_registered(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock()
        MockYDL.return_value = mock_ydl
        callback = MagicMock()
        extractor = PlaylistExtractor()
        # Act
        extractor.download_tracks(["vid001"], output_dir="/tmp/music", progress_callback=callback)
        # Assert : les options passées à YDL contiennent un progress_hook
        call_kwargs = MockYDL.call_args[0][0]
        assert "progress_hooks" in call_kwargs
        assert len(call_kwargs["progress_hooks"]) > 0

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_download_tracks_with_loudnorm_enabled_passes_postprocessor_args(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock()
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor()
        # Act
        extractor.download_tracks(["vid001"], output_dir="/tmp/music", normalize_audio=True)
        # Assert
        call_kwargs = MockYDL.call_args[0][0]
        assert "postprocessor_args" in call_kwargs
        assert "ExtractAudio" in call_kwargs["postprocessor_args"]
        assert "-af" in call_kwargs["postprocessor_args"]["ExtractAudio"]
        assert "loudnorm=I=-14.0:TP=-1.5:LRA=11" in call_kwargs["postprocessor_args"]["ExtractAudio"]

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_download_tracks_with_custom_lufs_and_true_peak(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock()
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor()
        # Act
        extractor.download_tracks(
            ["vid001"],
            output_dir="/tmp/music",
            normalize_audio=True,
            target_lufs=-16.0,
            true_peak=-2.0,
        )
        # Assert
        call_kwargs = MockYDL.call_args[0][0]
        assert "loudnorm=I=-16.0:TP=-2.0:LRA=11" in call_kwargs["postprocessor_args"]["ExtractAudio"]

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_download_tracks_with_loudnorm_disabled_omits_loudnorm_filter(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock()
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor()
        # Act
        extractor.download_tracks(["vid001"], output_dir="/tmp/music", normalize_audio=False)
        # Assert
        call_kwargs = MockYDL.call_args[0][0]
        assert "postprocessor_args" not in call_kwargs

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_download_tracks_defaults_to_loudnorm_enabled(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock()
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor()
        # Act
        extractor.download_tracks(["vid001"], output_dir="/tmp/music")
        # Assert
        call_kwargs = MockYDL.call_args[0][0]
        assert "postprocessor_args" in call_kwargs
        assert "loudnorm=I=-14.0:TP=-1.5:LRA=11" in call_kwargs["postprocessor_args"]["ExtractAudio"]

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_extractor_with_disabled_config_omits_loudnorm(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock()
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor(normalize_audio=False)
        # Act
        extractor.download_tracks(["vid001"], output_dir="/tmp/music")
        # Assert
        call_kwargs = MockYDL.call_args[0][0]
        assert "postprocessor_args" not in call_kwargs

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_download_tracks_outtmpl_uses_title_without_id(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock()
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor()
        # Act
        extractor.download_tracks(["vid001"], output_dir="/tmp/music")
        # Assert
        call_kwargs = MockYDL.call_args[0][0]
        assert call_kwargs["outtmpl"] == "/tmp/music/%(title)s.%(ext)s"
        assert "[%(id)s]" not in call_kwargs["outtmpl"]

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_download_tracks_configures_ffmpeg_extract_audio_postprocessor_m4a_default(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock()
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor()
        # Act
        extractor.download_tracks(["vid001"], output_dir="/tmp/music")
        # Assert
        call_kwargs = MockYDL.call_args[0][0]
        assert "postprocessors" in call_kwargs
        postprocessors = call_kwargs["postprocessors"]
        extract_audio_pp = next(
            p for p in postprocessors if p.get("key") == "FFmpegExtractAudio"
        )
        assert extract_audio_pp["preferredcodec"] == "m4a"
        assert extract_audio_pp["preferredquality"] == "192"

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_download_tracks_with_mp3_format_transmits_preferredcodec_mp3(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock()
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor()
        # Act
        extractor.download_tracks(["vid001"], output_dir="/tmp/music", audio_format="mp3")
        # Assert
        call_kwargs = MockYDL.call_args[0][0]
        assert "postprocessors" in call_kwargs
        postprocessors = call_kwargs["postprocessors"]
        extract_audio_pp = next(
            p for p in postprocessors if p.get("key") == "FFmpegExtractAudio"
        )
        assert extract_audio_pp["preferredcodec"] == "mp3"

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_download_tracks_with_sponsorblock_enabled_passes_sponsorblock_remove(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock()
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor()
        # Act
        extractor.download_tracks(["vid001"], output_dir="/tmp/music")
        # Assert
        call_kwargs = MockYDL.call_args[0][0]
        assert call_kwargs.get("sponsorblock_remove") == ["music_offtopic"]
        assert call_kwargs["postprocessors"] == [
            {"key": "SponsorBlock"},
            {"key": "ModifyChapters", "remove_sponsor_segments": ["music_offtopic"]},
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
                "preferredquality": "192",
            },
        ]

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_download_tracks_orders_modify_chapters_before_extract_audio(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock()
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor(enable_sponsorblock=True)
        # Act
        extractor.download_tracks(["vid001"], output_dir="/tmp/music")
        # Assert
        call_kwargs = MockYDL.call_args[0][0]
        keys = [pp["key"] for pp in call_kwargs["postprocessors"]]
        assert keys == ["SponsorBlock", "ModifyChapters", "FFmpegExtractAudio"]

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_download_tracks_with_sponsorblock_disabled_omits_sponsorblock_remove(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock()
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor()
        # Act
        extractor.download_tracks(
            ["vid001"], output_dir="/tmp/music", enable_sponsorblock=False
        )
        # Assert
        call_kwargs = MockYDL.call_args[0][0]
        assert "sponsorblock_remove" not in call_kwargs
        assert call_kwargs["postprocessors"] == [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
                "preferredquality": "192",
            },
        ]

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_download_tracks_extractor_level_sponsorblock_disabled_omits_sponsorblock_remove(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock()
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor(enable_sponsorblock=False)
        # Act
        extractor.download_tracks(["vid001"], output_dir="/tmp/music")
        # Assert
        call_kwargs = MockYDL.call_args[0][0]
        assert "sponsorblock_remove" not in call_kwargs
        assert call_kwargs["postprocessors"] == [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
                "preferredquality": "192",
            },
        ]

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_download_tracks_applies_trim_start_and_trim_end_to_track(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock()
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor()
        track_trims = {"vid001": ("00:12", "03:45")}
        # Act
        extractor.download_tracks(
            ["vid001"], output_dir="/tmp/music", track_trims=track_trims
        )
        # Assert
        call_kwargs = MockYDL.call_args[0][0]
        args = call_kwargs["postprocessor_args"]["ExtractAudio"]
        assert "-ss" in args
        assert "00:12" in args
        assert "-to" in args
        assert "03:45" in args

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_download_tracks_trim_start_only_applies_to_trimmed_track_without_impacting_others(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock()
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor()
        track_trims = {"vid001": ("00:12", None)}
        # Act
        extractor.download_tracks(
            ["vid001", "vid002"], output_dir="/tmp/music", track_trims=track_trims
        )
        # Assert
        assert MockYDL.call_count == 2
        call_opts_1 = MockYDL.call_args_list[0][0][0]
        assert "-ss" in call_opts_1["postprocessor_args"]["ExtractAudio"]
        assert "00:12" in call_opts_1["postprocessor_args"]["ExtractAudio"]
        call_opts_2 = MockYDL.call_args_list[1][0][0]
        audio_args_2 = call_opts_2.get("postprocessor_args", {}).get("ExtractAudio", [])
        assert "-ss" not in audio_args_2

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_download_tracks_supports_track_snapshot_in_track_trims(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        from yt_sync_core.models import TrackSnapshot

        mock_ydl = _make_ydl_mock()
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor()
        snapshot = TrackSnapshot(
            video_id="vid001",
            title="Trimmed",
            trim_start="00:05",
            trim_end="02:30",
        )
        # Act
        extractor.download_tracks(
            ["vid001"], output_dir="/tmp/music", track_trims={"vid001": snapshot}
        )
        # Assert
        call_kwargs = MockYDL.call_args[0][0]
        args = call_kwargs["postprocessor_args"]["ExtractAudio"]
        assert "-ss" in args
        assert "00:05" in args
        assert "-to" in args
        assert "02:30" in args

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_download_tracks_includes_player_client_extractor_args(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock()
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor()
        # Act
        extractor.download_tracks(["vid001"], output_dir="/tmp/music")
        # Assert
        call_kwargs = MockYDL.call_args[0][0]
        assert "extractor_args" in call_kwargs
        assert call_kwargs["extractor_args"]["youtube"]["player_client"] == ["android", "web"]
        assert "cookiesfrombrowser" not in call_kwargs
        assert "cookiefile" not in call_kwargs

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_download_tracks_includes_remote_components_ejs_github(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock()
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor()
        # Act
        extractor.download_tracks(["vid001"], output_dir="/tmp/music")
        # Assert
        call_kwargs = MockYDL.call_args[0][0]
        assert call_kwargs.get("remote_components") == {"ejs:github"}

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_download_tracks_with_cookies_browser_transmits_cookiesfrombrowser(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock()
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor(cookies_browser="firefox")
        # Act
        extractor.download_tracks(["vid001"], output_dir="/tmp/music")
        # Assert
        call_kwargs = MockYDL.call_args[0][0]
        assert call_kwargs.get("cookiesfrombrowser") == ("firefox",)
        assert "cookiefile" not in call_kwargs
        assert call_kwargs.get("extractor_args") == {
            "youtube": {"player_client": ["web"]}
        }

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_download_tracks_with_cookies_file_transmits_cookiefile(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock()
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor(cookies_file="/path/to/cookies.txt")
        # Act
        extractor.download_tracks(["vid001"], output_dir="/tmp/music")
        # Assert
        call_kwargs = MockYDL.call_args[0][0]
        assert call_kwargs.get("cookiefile") == "/path/to/cookies.txt"
        assert "cookiesfrombrowser" not in call_kwargs
        assert call_kwargs.get("extractor_args") == {
            "youtube": {"player_client": ["web"]}
        }

    @patch("yt_sync_core.extractor.yt_dlp.YoutubeDL")
    def test_download_tracks_with_call_level_cookies_override(
        self, MockYDL: MagicMock
    ) -> None:
        # Arrange
        mock_ydl = _make_ydl_mock()
        MockYDL.return_value = mock_ydl
        extractor = PlaylistExtractor()
        # Act
        extractor.download_tracks(
            ["vid001"], output_dir="/tmp/music", cookies_browser="chrome"
        )
        # Assert
        call_kwargs = MockYDL.call_args[0][0]
        assert call_kwargs.get("cookiesfrombrowser") == ("chrome",)
        assert call_kwargs.get("extractor_args") == {
            "youtube": {"player_client": ["web"]}
        }
