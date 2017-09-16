import asyncio
import aiohttp


class Downloader:
    """
    This class manages the download of various files.
    """

    def __init__(self, max_conn=5):
        self.max_conn = max_conn
