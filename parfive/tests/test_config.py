import aiohttp

from parfive.config import SessionConfig


def test_session_config_defaults():
    c = SessionConfig()
    assert isinstance(c.aiohttp_session_kwargs, dict)
    assert not c.aiohttp_session_kwargs
    assert isinstance(c.timeouts, aiohttp.ClientTimeout)
    assert c.timeouts.total == 0
    assert c.timeouts.sock_read == 90
    assert c.http_proxy is None
    assert c.https_proxy is None
    assert isinstance(c.headers, dict)
    assert "User-Agent" in c.headers
    assert c.chunksize == 1024
    assert c.use_aiofiles is False
