"""parfive - A parallel file downloader using asyncio."""
from .downloader import Downloader
from .results import Results

__all__ = ['Downloader', 'Results']


try:
    from .version import __version__
except ImportError:
    print("version.py not found, please reinstall parfive.")
    __version__ = "unknown"
