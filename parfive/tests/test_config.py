import ssl

import aiohttp

from parfive.config import SessionConfig
from parfive.downloader import Downloader


def test_session_config_defaults():
    c = SessionConfig()
    assert c.aiohttp_session_generator is None
    assert isinstance(c.timeouts, aiohttp.ClientTimeout)
    assert c.timeouts.total == 0
    assert c.timeouts.sock_read == 90
    assert c.http_proxy is None
    assert c.https_proxy is None
    assert c.chunksize == 1024
    assert c.use_aiofiles is False
    assert len(c.done_callbacks) == 0

    assert isinstance(c.headers, dict)
    assert "User-Agent" in c.headers
    assert "parfive" in c.headers["User-Agent"]


def test_session_config_env_defaults():
    c = SessionConfig()
    assert c.env.serial_mode is False
    assert c.env.disable_range is False
    assert c.env.hide_progress is False
    assert c.env.timeout_total == 0
    assert c.env.timeout_sock_read == 90


def test_ssl_context():
    # Assert that the unpickalable SSL context object doesn't anger the
    # dataclass gods
    def gen(config):
        return aiohttp.ClientSession(context=ssl.create_default_context())

    c = SessionConfig(aiohttp_session_generator=gen)
    d = Downloader(config=c)
