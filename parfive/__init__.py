"""parfive - A parallel file downloader using asyncio."""

from pkg_resources import get_distribution, DistributionNotFound

from .downloader import Downloader
from .results import Results

__all__ = ['Downloader', 'Results']

__author__ = 'Stuart Mumford <stuart@cadair.com>'

try:
    __version__ = get_distribution(__name__).version
except DistributionNotFound:
    # package is not installed
    __version__ = "unknown"
