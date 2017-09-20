import os
import asyncio
from functools import partial

import aiohttp
from tqdm import tqdm


def default_name(path, resp, url):
    name = resp.headers.get("Content-Disposition", url.split('/')[-1])
    return os.path.join(path, name)


class Token:
    def __init__(self, n):
        self.n = n

    def __repr__(self):
        return super().__repr__() + f"n = {self.n}"

    def __str__(self):
        return f"Token {self.n}"


class Downloader:
    """
    This class manages the parallel download of files.
    """

    def __init__(self, max_conn=5, loop=None):
        if not loop:
            loop = asyncio.get_event_loop()
        self.loop = loop

        self.queue = asyncio.Queue()
        self.files = list()
        self.targets = list()
        self.tokens = asyncio.Queue(maxsize=max_conn)
        for i in range(max_conn):
            self.tokens.put_nowait(Token(i+1))

    def enqueue_file(self, url, path, **kwargs):
        """
        Add a file to the download queue.

        Parameters
        ----------

        url : `str`
            The URL to retrieve.

        path : `str`
            The path to retrieve the file into.

        kwargs : `dict`
            Extra keyword arguments are passed to `asyncdownloader.Downloader.get_file`.
        """
        filepath = partial(default_name, path)
        get_file = partial(self.get_file, url=url, filepath_partial=filepath, **kwargs)
        self.queue.put_nowait(get_file)

    async def get_file(self, session, *, url, filepath_partial, chunksize=100,
                       main_pb=None, token, **kwargs):
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

        main_pb : `tqdm.tqdm`
            Optional progressbar instance to advance when file is complete.

        kwargs : `dict`
            Extra keyword arguments are passed to `~aiohttp.ClientSession.get`.

        Returns
        -------

        filepath : `str`
            The name of the file saved.

        """
        async with session.get(url, **kwargs) as resp:
            filepath = filepath_partial(resp, url)
            fname = os.path.split(filepath)[-1]
            file_pb = tqdm(position=token.n, unit='B', unit_scale=True, desc=fname, leave=False)
            with open(filepath, 'wb') as fd:
                while True:
                    chunk = await resp.content.read(chunksize)
                    if not chunk:
                        if main_pb:
                            main_pb.update(1)
                        if file_pb is not None:
                            file_pb.close()
                        return filepath
                    if file_pb is not None:
                        file_pb.update(chunksize)
                    fd.write(chunk)

    async def run_download(self):
        """
        Download all files in the queue.
        """
        with tqdm(total=self.queue.qsize(), unit='file', desc="Files Downloaded") as main_pb:
            with aiohttp.ClientSession(loop=self.loop) as session:
                futures = []
                while not self.queue.empty():
                    get_file = await self.queue.get()
                    token = await self.tokens.get()
                    future = asyncio.ensure_future(get_file(session, main_pb=main_pb, token=token))

                    def callback(token, future):
                        self.tokens.put_nowait(token)

                    future.add_done_callback(partial(callback, token))
                    futures.append(future)

                # Wait for all the coroutines to finish
                done, _ = await asyncio.wait(futures)
                # Return one future to represent all the results.
                return asyncio.gather(*done)

    def download(self):
        """
        Download all files in the queue.

        Returns
        -------
        filenames : `list`
            A list of files downloaded.
        """
        future = self.loop.run_until_complete(self.run_download())
        return future.result()
