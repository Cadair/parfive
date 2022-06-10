import os
import platform
import warnings
from typing import Any, Dict, Union, Optional

try:
    from typing import Literal  # Added in Python 3.8
except ImportError:
    from typing_extensions import Literal  # type: ignore

import aiohttp
from pydantic import BaseSettings, Field

import parfive
from parfive.utils import ParfiveUserWarning

__all__ = ["DownloaderConfig", "SessionConfig"]


def _default_headers():
    return {
        "User-Agent": f"parfive/{parfive.__version__}"
        f" aiohttp/{aiohttp.__version__}"
        f" python/{platform.python_version()}"
    }


class EnvConfig(BaseSettings):
    """
    Configuration read from environment variables.
    """

    # Session scoped env vars
    serial_mode: bool = Field(False, env="PARFIVE_SINGLE_DOWNLOAD")
    disable_range: bool = Field(False, env="PARFIVE_DISABLE_RANGE")
    hide_progress: bool = Field(False, env="PARFIVE_HIDE_PROGRESS")
    debug_logging: bool = Field(False, env="PARFIVE_DEBUG")
    timeout_total: float = Field(0, env="PARFIVE_TOTAL_TIMEOUT")
    timeout_sock_read: float = Field(90, env="PARFIVE_SOCK_READ_TIMEOUT")
    override_use_aiofiles: bool = Field(False, env="PARFIVE_OVERWRITE_ENABLE_AIOFILES")


class SessionConfig(BaseSettings):
    """
    Configuration options for `parfive.Downloader`.
    """

    http_proxy: Optional[str] = Field(None, env="HTTP_PROXY")
    """
    The URL of a proxy to use for HTTP requests. Will default to the value of
    the ``HTTP_PROXY`` env var.
    """
    https_proxy: Optional[str] = Field(None, env="HTTPS_PROXY")
    """
    The URL of a proxy to use for HTTPS requests. Will default to the value of
    the ``HTTPS_PROXY`` env var.
    """
    headers: Optional[Dict[str, str]] = None
    """
    Headers to be passed to all requests made by this session. These headers
    are passed to the `aiohttp.ClientSession` along with
    ``aiohttp_session_kwargs``.

    The default value for headers is setting the user agent to a string with
    the version of parfive, aiohttp and Python.

    To use aiohttp's default headers set this argument to an empty dictionary.
    """
    chunksize: float = 1024
    """
    The default chunksize to be used for transfers over HTTP.
    """
    file_progress: bool = True
    """
    If `True` (the default) a progress bar will be shown for every file if any
    progress bars are shown.
    """
    notebook: Optional[bool] = None
    """
    If `None` `tqdm` will automatically detect if it can draw rich IPython
    Notebook progress bars. If `False` or `True` notebook mode will be forced
    off or on.
    """
    log_level: Optional[str] = None
    """
    If not `None` configure the logger to log to stderr with this log level.
    """
    use_aiofiles: bool = Field(False)
    """
    Enables using `aiofiles` to write files to disk in their own thread pool.

    The default value is `False`.

    This argument will be overridden by the
    ``PARFIVE_OVERWRITE_ENABLE_AIOFILES`` environment variable. If `aiofiles`
    can not be imported then this will be set to `False`.
    """
    timeouts: Optional[aiohttp.ClientTimeout] = None
    """
    The `aiohttp.ClientTimeout` object to control the timeouts used for all
    HTTP requests.

    By default the ``total`` timeout is set to `0` (never timeout) and the
    ``sock_read`` timeout is set to `90` seconds. These defaults can also be
    overridden by the ``PARFIVE_TOTAL_TIMEOUT`` and
    ``PARFIVE_SOCK_READ_TIMEOUT`` environment variables.
    """
    aiohttp_session_kwargs: Dict = Field(default_factory=dict)
    """
    Any extra keyword arguments to be passed to `aiohttp.ClientSession`.

    Note that the `headers` keyword argument is handled separately, so should
    not be included in this dict.
    """
    env: EnvConfig = Field(default_factory=EnvConfig)

    @staticmethod
    def _aiofiles_importable():
        try:
            import aiofiles
        except ImportError:
            return False
        return True

    def _compute_aiofiles(self, use_aiofiles):
        if self.env.override_use_aiofiles:
            use_aiofiles = True
        if use_aiofiles and not self._aiofiles_importable():
            warnings.warn(
                "Can not use aiofiles even though use_aiofiles is set to True as aiofiles can not be imported.",
                ParfiveUserWarning,
            )
            use_aiofiles = False
        return use_aiofiles

    def __init__(self, **data):
        super().__init__(**data)
        if self.timeouts is None:
            timeouts = {
                "total": self.env.timeout_total,
                "sock_read": self.env.timeout_sock_read,
            }
            self.timeouts = aiohttp.ClientTimeout(**timeouts)

        if self.use_aiofiles is not None:
            self.use_aiofiles = self._compute_aiofiles(self.use_aiofiles)

        if self.env.debug_logging:
            self.log_level = "DEBUG"


class DownloaderConfig(BaseSettings):
    """
    Hold all downloader session state.
    """

    max_conn: int = 5
    max_splits: int = 5
    progress: bool = True
    overwrite: Union[bool, Literal["unique"]] = False
    headers: Optional[Dict[str, str]] = Field(default_factory=_default_headers)
    config: Optional[SessionConfig] = Field(default_factory=SessionConfig)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.config is None:
            self.config = SessionConfig()

        self.max_conn = 1 if self.env.serial_mode else self.max_conn
        self.max_splits = 1 if self.env.serial_mode or self.env.disable_range else self.max_splits
        self.progress = False if self.env.hide_progress else self.progress

        if self.progress is False:
            self.config.file_progress = False

        # Remove this after deprecation period
        if self.config.headers is not None:
            self.headers = self.config.headers
        if self.headers is None:
            self.headers = _default_headers()

    def __getattr__(self, __name: str) -> Any:
        return getattr(self.config, __name)

    @property
    def aiohttp_session(self) -> aiohttp.ClientSession:
        """
        The aiohttp session with the kwargs stored by this class.

        Notes
        -----
        `aiohttp.ClientSession` expects to be instantiated in a asyncio context
        where it can get a running loop.
        """
        return aiohttp.ClientSession(headers=self.headers, **self.aiohttp_session_kwargs)
