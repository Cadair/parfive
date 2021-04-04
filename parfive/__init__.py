
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
from .version import version as __version__

__all__ = ['Downloader', 'Results', 'log', "__version__"]
