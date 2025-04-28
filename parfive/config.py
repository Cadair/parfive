import importlib.util
import os
import platform
import warnings
from collections.abc import Iterable
from typing import Callable, Optional, Union

try:
    from typing import Literal  # Added in Python 3.8
except ImportError:
    from typing_extensions import Literal  # type: ignore

from dataclasses import dataclass, field

import aiohttp

import parfive
from parfive.utils import ParfiveUserWarning

__all__ = ["DownloaderConfig", "SessionConfig"]


def _default_headers():
    return {
        "User-Agent": f"parfive/{parfive.__version__}"
        f" aiohttp/{aiohttp.__version__}"
        f" python/{platform.python_version()}"
    }


def _default_aiohttp_session(config: "SessionConfig") -> aiohttp.ClientSession:
    """
    The aiohttp session with the kwargs stored by this config.

    Notes
    -----
    `aiohttp.ClientSession` expects to be instantiated in a asyncio context
    where it can get a running loop.
    """
    return aiohttp.ClientSession(headers=config.headers, requote_redirect_url=False)


@dataclass
class EnvConfig:
    """
    Configuration read from environment variables.
    """

    # Session scoped env vars
    serial_mode: bool = field(default=False, init=False)
    disable_range: bool = field(default=False, init=False)
    hide_progress: bool = field(default=False, init=False)
    debug_logging: bool = field(default=False, init=False)
    timeout_total: float = field(default=0, init=False)
    timeout_sock_read: float = field(default=90, init=False)
    override_use_aiofiles: bool = field(default=False, init=False)

    def __post_init__(self):
        self.serial_mode = "PARFIVE_SINGLE_DOWNLOAD" in os.environ
        self.disable_range = "PARFIVE_DISABLE_RANGE" in os.environ
        self.hide_progress = "PARFIVE_HIDE_PROGRESS" in os.environ
        self.debug_logging = "PARFIVE_DEBUG" in os.environ
        self.timeout_total = float(os.environ.get("PARFIVE_TOTAL_TIMEOUT", 0))
        self.timeout_sock_read = float(os.environ.get("PARFIVE_SOCK_READ_TIMEOUT", 90))
        self.override_use_aiofiles = "PARFIVE_OVERWRITE_ENABLE_AIOFILES" in os.environ


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
    headers: Optional[dict[str, str]] = field(default_factory=_default_headers)
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
    If `True` (the default) a progress bar will be shown (if any progress bars
    are shown) for every file, in addition for one showing progress of
    downloading all file.
    """
    notebook: Union[bool, None] = None
    """
    Override automatic detection of Jupyter notebook for drawing progress bars.
    If `None` `tqdm` will automatically detect if it can draw rich notebook
    progress bars. If `False` or `True` notebook mode will be forced
    off or on.
    """
    log_level: Optional[str] = None
    """
    If not `None` configure the logger to log to stderr with this log level.
    """
    use_aiofiles: Optional[bool] = False
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
    aiohttp_session_generator: Optional[Callable[["SessionConfig"], aiohttp.ClientSession]] = None
    """
    A function to override the generation of the `aiohttp.ClientSession` object.

    Due to the fact that this session needs to be instantiated inside the
    asyncio context this option is a function. This function takes one argument
    which is the instance of this ``SessionConfig`` class. It is expected that
    you pass the ``.headers`` attribute of the config instance through to the
    ``headers=`` keyword argument of the session you instantiate.
    """
    env: EnvConfig = field(default_factory=EnvConfig)

    done_callbacks: Iterable[Callable[[str, str, Optional[Exception]], None]] = ()
    """
    A list of functions to be called when a download is completed.

    The signature of the function to be called is `f(filepath: str, url: str, error: Optional[Exception])`.
    If successful, error will be None, else the occured exception or asyncio.CancelledError.
    """

    @staticmethod
    def _aiofiles_importable():
        return importlib.util.find_spec("aiofiles") is not None

    def _compute_aiofiles(self, use_aiofiles):
        use_aiofiles = use_aiofiles or self.env.override_use_aiofiles
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
                "total": self.env.timeout_total,
                "sock_read": self.env.timeout_sock_read,
            }
            self.timeouts = aiohttp.ClientTimeout(**timeouts)
        if self.http_proxy is None:
            self.http_proxy = os.environ.get("HTTP_PROXY", None)
        if self.https_proxy is None:
            self.https_proxy = os.environ.get("HTTPS_PROXY", None)

        if self.use_aiofiles is not None:
            self.use_aiofiles = self._compute_aiofiles(self.use_aiofiles)

        if self.env.debug_logging:
            self.log_level = "DEBUG"


@dataclass
class DownloaderConfig:
    """
    Hold all downloader session state.
    """

    max_conn: int = 5
    max_splits: int = 5
    progress: bool = True
    overwrite: Union[bool, Literal["unique"]] = False
    config: Optional[SessionConfig] = field(default_factory=SessionConfig)
    env: EnvConfig = field(default_factory=EnvConfig)

    def __post_init__(self):
        if self.config is None:
            self.config = SessionConfig()

        self.max_conn = 1 if self.env.serial_mode else self.max_conn
        self.max_splits = 1 if self.env.serial_mode or self.env.disable_range else self.max_splits
        self.progress = False if self.env.hide_progress else self.progress

        if self.progress is False:
            self.file_progress = False

    def __getattr__(self, __name: str):
        return getattr(self.config, __name)

    def aiohttp_client_session(self):
        if self.config.aiohttp_session_generator is None:
            return _default_aiohttp_session(self.config)
        return self.config.aiohttp_session_generator(self.config)
