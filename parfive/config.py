import os
import sys
import warnings
from typing import Dict, Union, Literal, Optional
from dataclasses import InitVar, field, asdict, dataclass

import aiohttp

import parfive
from parfive.utils import ParfiveUserWarning

__all__ = ["SessionConfig"]


def _default_headers():
    return {
        "User-Agent": f"parfive/{parfive.__version__} aiohttp/{aiohttp.__version__} python/{sys.version[:5]}"
    }


@dataclass
class SessionConfig:
    """
    Extra session config for advanced users.

    The defaults for the `'total'` and `'sock_read'` timeouts can be
    overridden by two environment variables ``PARFIVE_TOTAL_TIMEOUT`` and
    ``PARFIVE_SOCK_READ_TIMEOUT``.
    """

    http_proxy: Optional[str] = None
    """
    The URL of a proxy to use for http requests. Will default to the value of
    the ``HTTP_PROXY`` env var.
    """
    https_proxy: Optional[str] = None
    """
    The URL of a proxy to use for https requests. Will default to the value of
    the ``HTTPSPROXY`` env var.
    """
    headers: Dict = field(default_factory=_default_headers)
    chunksize: float = 1024
    file_progress: bool = True
    notebook: Union[bool, None] = None
    use_aiofiles: bool = False
    timeouts: Optional[aiohttp.ClientTimeout] = None
    aiohttp_session_kwargs: Dict = field(default_factory=dict)

    @staticmethod
    def _aiofiles_importable():
        try:
            pass
        except ImportError:
            return False
        return True

    def __post_init__(self):
        if self.timeouts is None:
            timeouts = {
                "total": float(os.environ.get("PARFIVE_TOTAL_TIMEOUT", 0)),
                "sock_read": float(os.environ.get("PARFIVE_SOCK_READ_TIMEOUT", 90)),
            }
            self.timeouts = aiohttp.ClientTimeout(**timeouts)
        if self.http_proxy is None:
            self.http_proxy = os.environ.get("HTTP_PROXY", None)
        if self.https_proxy is None:
            self.https_proxy = os.environ.get("HTTPS_PROXY", None)

        self.use_aiofiles = (
            self.use_aiofiles or "PARFIVE_OVERWRITE_ENABLE_AIOFILES" in os.environ
        )
        if self.use_aiofiles and not self._aiofiles_importable():
            warnings.warn(
                "Can not use aiofiles even though use_aiofiles is set to True as aiofiles can not be imported.",
                ParfiveUserWarning,
            )
            self.use_aiofiles = False


@dataclass
class _DownloaderConfig(SessionConfig):
    """
    Hold all downloader session state.
    """

    max_conn: int = 5
    max_splits: int = 5
    progress: bool = True
    overwrite: Union[bool, Literal["unique"]] = False
    config: InitVar[SessionConfig] = None
    # Session scoped env vars
    serial_mode: bool = field(default=False, init=False)
    disable_range: bool = field(default=False, init=False)
    debug: bool = field(default=False, init=False)

    def __post_init__(self, config):
        if config is None:
            config = SessionConfig()
        if not isinstance(config, SessionConfig):
            raise TypeError(
                "config argument should be a parfive.config.SessionConfig instance"
            )

        self.serial_mode = "PARFIVE_SINGLE_DOWNLOAD" in os.environ
        self.disable_range = "PARFIVE_DISABLE_RANGE" in os.environ
        self.debug = "PARFIVE_DEBUG" in os.environ

        self.max_conn = 1 if self.serial_mode else self.max_conn
        self.max_splits = (
            1 if self.serial_mode or self.disable_range else self.max_splits
        )

        for name, value in asdict(config).items():
            setattr(self, name, value)

    @property
    def aiohttp_session(self) -> aiohttp.ClientSession:
        """
        The aiohttp session with the kwargs stored by this class.

        Notes
        -----
        `aiohttp.ClientSession` expects to be instantiated in a asyncio context
        where it can get a running loop.
        """
        return aiohttp.ClientSession(
            headers=self.headers, **self.aiohttp_session_kwargs
        )
