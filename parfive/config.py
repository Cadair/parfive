import os
import sys
import warnings
from typing import Dict, Union, Optional

try:
    from typing import Literal  # Added in Python 3.8
except ImportError:
    from typing_extensions import Literal

from dataclasses import InitVar, field, asdict, dataclass

import aiohttp

import parfive
from parfive.utils import ParfiveUserWarning

__all__ = ["DownloaderConfig", "SessionConfig"]


def _default_headers():
    return {
        "User-Agent": f"parfive/{parfive.__version__} aiohttp/{aiohttp.__version__} python/{sys.version[:5]}"
    }


@dataclass
class SessionConfig:
    """
    Configuration options for `parfive.Downloader`.
    """

    http_proxy: Optional[str] = None
    """
    The URL of a proxy to use for HTTP requests. Will default to the value of
    the ``HTTP_PROXY`` env var.
    """
    https_proxy: Optional[str] = None
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
    notebook: Union[bool, None] = None
    """
    If `None` `tqdm` will automatically detect if it can draw rich IPython
    Notebook progress bars. If `False` or `True` notebook mode will be forced
    off or on.
    """
    use_aiofiles: bool = None
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
    aiohttp_session_kwargs: Dict = field(default_factory=dict)
    """
    Any extra keyword arguments to be passed to `aiohttp.ClientSession`.

    Note that the `headers` keyword argument is handled separately, so should
    not be included in this dict.
    """

    @staticmethod
    def _aiofiles_importable():
        try:
            import aiofiles
        except ImportError:
            return False
        return True

    def _compute_aiofiles(self, use_aiofiles):
        use_aiofiles = use_aiofiles or "PARFIVE_OVERWRITE_ENABLE_AIOFILES" in os.environ
        if use_aiofiles and not self._aiofiles_importable():
            warnings.warn(
                "Can not use aiofiles even though use_aiofiles is set to True as aiofiles can not be imported.",
                ParfiveUserWarning,
            )
            use_aiofiles = False
        return use_aiofiles

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

        if self.use_aiofiles is not None:
            self.use_aiofiles = self._compute_aiofiles(self.use_aiofiles)


@dataclass
class EnvConfig:
    """
    Configuration read from environment variables.
    """

    # Session scoped env vars
    serial_mode: bool = field(default=False, init=False)
    disable_range: bool = field(default=False, init=False)
    debug: bool = field(default=False, init=False)
    hide_progress: bool = field(default=False, init=False)

    def __post_init__(self):
        self.serial_mode = "PARFIVE_SINGLE_DOWNLOAD" in os.environ
        self.disable_range = "PARFIVE_DISABLE_RANGE" in os.environ
        self.debug = "PARFIVE_DEBUG" in os.environ
        self.hide_progress = "PARFIVE_HIDE_PROGRESS" in os.environ


@dataclass
class DownloaderConfig(SessionConfig):
    """
    Hold all downloader session state.
    """

    max_conn: int = 5
    max_splits: int = 5
    progress: bool = True
    overwrite: Union[bool, Literal["unique"]] = False
    # headers and use_aiofiles are deprecated here.
    # The arguments passed to SessionConfig take precedence.
    # To make this priority work, the defaults on SessionConfig
    # are that these two arguments default to None.
    # When these are removed after the deprecation period, the defaults here
    # should be moved to SessionConifg
    headers: Optional[Dict[str, str]] = field(default_factory=_default_headers)
    use_aiofiles: bool = False
    config: InitVar[Optional[SessionConfig]] = None
    env: EnvConfig = field(default_factory=EnvConfig)

    def __post_init__(self, config):
        if config is None:
            config = SessionConfig()
        if not isinstance(config, SessionConfig):
            raise TypeError("config argument should be a parfive.config.SessionConfig instance")

        self.max_conn = 1 if self.env.serial_mode else self.max_conn
        self.max_splits = 1 if self.env.serial_mode or self.env.disable_range else self.max_splits
        self.progress = False if self.env.hide_progress else self.progress

        # Squash the properties passed by the user in config onto this object.
        for name, value in asdict(config).items():
            # Remove this check after deprecation period
            if name in ("headers", "use_aiofiles"):
                continue
            setattr(self, name, value)

        # Remove this after deprecation period
        if config.headers is not None:
            self.headers = config.headers
        if config.use_aiofiles is not None:
            self.use_aiofiles = self._compute_aiofiles(config.use_aiofiles)

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
