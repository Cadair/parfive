import os
import asyncio
from functools import partial

import aiohttp


def default_name(path, resp, url):
    name = resp.headers.get("Content-Disposition", url.split('/')[-1])
    return os.path.join(path, name)


class Downloader:
    """
    This class manages the download of various files.
    """

    def __init__(self, max_conn=5, loop=None):
        if not loop:
            loop = asyncio.get_event_loop()
        self.loop = loop

        self.queue = asyncio.Queue(maxsize=max_conn)
        self.files = list()
        self.targets = list()

    def enqueue_file(self, url, path):
        """
        Add a file to the download queue.

        Parameters
        ----------

        url : `str`
            The URL to retrieve.

        path : `str`
            The path to retrieve the file into.
        """
        filepath = partial(default_name, path)
        get_file = partial(self._get_file, url=url, filepath_partial=filepath)
        self.targets.append(get_file)

    async def _get_file(self, session, *, url, filepath_partial, chunksize=100, **kwargs):
        """
        Read the file from the given url into the filename given by ``filepath_partial``.

        Parameters
        ----------

        session : `aiohttp.ClientSession`
            The `aiohttp.ClientSession` to use to retrieve the files.

        url : `str`
            The url to retrieve.

        filepath_partial : `callable`
            A function to call which returns the filepath to save the url to.
            Takes two arguments ``resp, url``.

        chunksize : `int`
            The number of bytes to read into the file at a time.

        kwargs : `dict`
            Extra keyword arguments are passed to `~aiohttp.ClientSession.get`.

        Returns
        -------

        filepath : `str`
            The name of the file saved.

        """
        async with session.get(url, **kwargs) as resp:
            filepath = filepath_partial(resp, url)
            with open(filepath, 'wb') as fd:
                while True:
                    chunk = await resp.content.read(chunksize)
                    if not chunk:
                        return filepath
                    fd.write(chunk)

    async def run_download(self, session):
        """
        Download all files in the queue.
        """

        futures = []
        while self.targets:
            await self.queue.put(self.targets.pop())
            get_file = await self.queue.get()
            futures.append(self.loop.create_task(get_file(session)))

        done, _ = await asyncio.wait(futures)
        return asyncio.gather(*done)

    def download(self):
        """
        Download all files in the queue.

        Returns
        -------
        filenames : `list`
            A list of files downloaded.
        """
        with aiohttp.ClientSession(loop=self.loop) as session:
            i = self.loop.run_until_complete(self.run_download(session))
        return i.result()
