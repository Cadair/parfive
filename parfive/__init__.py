"""parfive - A parallel file downloader using asyncio."""

__version__ = '0.1.1'
__author__ = 'Stuart Mumford <stuart@cadair.com>'

from .downloader import Downloader
from .results import Results

__all__ = ['Downloader', 'Results']
