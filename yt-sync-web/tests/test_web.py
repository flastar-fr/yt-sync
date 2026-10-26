from yt_sync_web import __version__
from yt_sync_core import __version__ as core_version


def test_web_version():
    assert __version__ == "0.1.0"
    assert core_version == "0.1.0"
