import aiohttp
import pytest

from parfive.config import DownloaderConfig, SessionConfig
from parfive.downloader import Downloader
from parfive.utils import ParfiveFutureWarning


def test_session_config_defaults():
    c = SessionConfig()
    assert isinstance(c.aiohttp_session_kwargs, dict)
    assert not c.aiohttp_session_kwargs
    assert isinstance(c.timeouts, aiohttp.ClientTimeout)
    assert c.timeouts.total == 0
    assert c.timeouts.sock_read == 90
    assert c.http_proxy is None
    assert c.https_proxy is None
    assert c.chunksize == 1024

    # Deprecated behaviour
    assert c.headers is None
    assert c.use_aiofiles is None
    # assert c.use_aiofiles is False
    # assert isinstance(c.headers, dict)
    # assert "User-Agent" in c.headers


def test_use_aiofiles_deprecated():
    c = DownloaderConfig()
    assert c.use_aiofiles is False
    c = DownloaderConfig(use_aiofiles=True)
    assert c.use_aiofiles is True
    c = DownloaderConfig(config=SessionConfig(use_aiofiles=True))
    assert c.use_aiofiles is True
    c = DownloaderConfig(config=SessionConfig(use_aiofiles=False))
    assert c.use_aiofiles is False
    c = DownloaderConfig(use_aiofiles=True, config=SessionConfig(use_aiofiles=False))
    assert c.use_aiofiles is False
    c = DownloaderConfig(use_aiofiles=False, config=SessionConfig(use_aiofiles=True))
    assert c.use_aiofiles is True


def test_headers_deprecated():
    c = DownloaderConfig()
    assert isinstance(c.headers, dict)
    assert len(c.headers) == 1
    assert "User-Agent" in c.headers

    test_headers = {"spam": "eggs"}

    c = DownloaderConfig(headers=test_headers)
    assert c.headers == test_headers

    c = DownloaderConfig(headers={"ordinary": "rabbit"}, config=SessionConfig(headers=test_headers))
    assert c.headers == test_headers

    c = DownloaderConfig(config=SessionConfig(headers=test_headers))
    assert c.headers == test_headers

    # This test should really be on the SessionConfig object
    # but because of the deprecation logic it has to be done here.
    c = DownloaderConfig(headers=None)
    assert c.headers is None


def test_deprecated_downloader_arguments():
    with pytest.warns(ParfiveFutureWarning, match="use_aiofiles keyword"):
        d = Downloader(use_aiofiles=False)
    assert d.config.use_aiofiles is False

    with pytest.warns(ParfiveFutureWarning, match="headers keyword"):
        d = Downloader(headers="ni")
    assert d.config.headers == "ni"
