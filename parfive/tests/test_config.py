import ssl

import aiohttp
import pytest

from parfive.config import DownloaderConfig, SessionConfig
from parfive.downloader import Downloader
from parfive.utils import ParfiveFutureWarning


def test_session_config_defaults():
    c = SessionConfig()
    assert callable(c.aiohttp_session_generator)
    assert isinstance(c.timeouts, aiohttp.ClientTimeout)
    assert c.timeouts.total == 0
    assert c.timeouts.sock_read == 90
    assert c.http_proxy is None
    assert c.https_proxy is None
    assert c.chunksize == 1024
    assert c.use_aiofiles is False

    # Deprecated behaviour
    assert c.headers is None
    # assert isinstance(c.headers, dict)
    # assert "User-Agent" in c.headers


def test_session_config_env_defaults():
    c = SessionConfig()
    assert c.env.serial_mode is False
    assert c.env.disable_range is False
    assert c.env.hide_progress is False
    assert c.env.timeout_total == 0
    assert c.env.timeout_sock_read == 90


def test_headers_deprecated():
    c = DownloaderConfig()
    assert isinstance(c.headers, dict)
    assert len(c.headers) == 1
    assert "User-Agent" in c.headers
    assert "parfive" in c.headers["User-Agent"]

    c = DownloaderConfig(headers=None)
    assert isinstance(c.headers, dict)
    assert len(c.headers) == 1
    assert "User-Agent" in c.headers
    assert "parfive" in c.headers["User-Agent"]

    test_headers = {"spam": "eggs"}

    c = DownloaderConfig(headers=test_headers)
    assert c.headers == test_headers

    c = DownloaderConfig(headers={"ordinary": "rabbit"}, config=SessionConfig(headers=test_headers))
    assert c.headers == test_headers

    c = DownloaderConfig(config=SessionConfig(headers=test_headers))
    assert c.headers == test_headers

    # This test should really be on the SessionConfig object
    # but because of the deprecation logic it has to be done here.
    c = DownloaderConfig(headers={})
    assert not c.headers


def test_deprecated_downloader_arguments():
    with pytest.warns(ParfiveFutureWarning, match="headers keyword"):
        d = Downloader(headers="ni")
    assert d.config.headers == "ni"


def test_ssl_context():
    # Assert that the unpickalable SSL context object doesn't anger the
    # dataclass gods
    gen = lambda config: aiohttp.ClientSession(context=ssl.create_default_context())
    c = SessionConfig(aiohttp_session_generator=gen)
    d = Downloader(config=c)
