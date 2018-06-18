"""parfive - A parallel file downloader using asyncio."""

__version__ = '0.1.0'
__author__ = 'Stuart Mumford <stuart@cadair.com>'

from .downloader import Downloader, Results

__all__ = ['Downloader', 'Results']
