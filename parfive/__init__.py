
"""
*******
parfive
*******

A parallel file downloader using asyncio.

* Documentation: https://parfive.readthedocs.io/en/stable/
* Source code: https://github.com/Cadair/parfive
"""
from .downloader import Downloader
from .results import Results
from .utils import log

__all__ = ['Downloader', 'Results', 'log', "__version__"]

try:
    from ._version import version as __version__
except ImportError:
    print("Version not found, please reinstall parfive.")
    __version__ = "unknown"
