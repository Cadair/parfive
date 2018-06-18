import os
import asyncio
import contextlib
from functools import partial
from collections import UserList, namedtuple

import aiohttp
from tqdm import tqdm


def default_name(path, resp, url):
    name = resp.headers.get("Content-Disposition", url.split('/')[-1])
    return os.path.join(path, name)


class FailedDownload(Exception):
    def __init__(self, url, response):
        self.url = url
        self.response = response
        super().__init__()

    def __repr__(self):
        out = super().__repr__()
        out += '\n {} {}'.format(self.url, self.response)
        return out

    def __str__(self):
        return "Download Failed: {} with error {}".format(self.url, str(self.response))


class Results(UserList):
    """
    The results of a download.
    """
    def __init__(self, *args):
        super().__init__(*args)
        self._errors = list()
        self._error = namedtuple("error", ("url", "response"))

    def __repr__(self):
        out = super().__repr__()
        if self.errors:
            out += '\nErrors:\n'
            out += repr(self.errors)
        return out

    def add_error(self, url, response):
        """
        Add an error to the results.
        """
        self._errors.append(self._error(url, response))

    @property
    def errors(self):
        return self._errors


class Token:
    def __init__(self, n):
        self.n = n

    def __repr__(self):
        return super().__repr__() + "n = {}".format(self.n)

    def __str__(self):
        return "Token {}".format(self.n)


class Downloader:
    """
    Download files in parallel.

    Parameters
    ----------

    max_conn : `int`, optional
        The number of parallel download slots.

    progress : `bool`, optional
        If true a main progress bar showing how many of the total files have
        been downloaded. If false, no progress bars will be shown at all.

    file_progress : `bool`, optional
        If true and ``progress`` is true, show ``max_conn`` progress bars
        detailing the progress of each individual file being downloaded.

    loop : `asyncio.AbstractEventLoop`, optional
        The event loop to use to download the files.
    """

    def __init__(self, max_conn=5, progress=True, file_progress=True, loop=None):
        if not loop:
            loop = asyncio.get_event_loop()
        self.loop = loop

        self.progress = progress
        self.file_progress = file_progress if self.progress else False

        self.queue = asyncio.Queue()
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
            The directory to retrieve the file into.

        kwargs : `dict`
            Extra keyword arguments are passed to `aiohttp.ClientSession.get`.
        """
        filepath = partial(default_name, path)
        get_file = partial(self._get_file, url=url, filepath_partial=filepath, **kwargs)
        self.queue.put_nowait(get_file)

    def download(self):
        """
        Download all files in the queue.

        Returns
        -------
        filenames : `parfive.Results`
            A list of files downloaded.
        """
        future = self.loop.run_until_complete(self._run_download())
        dlresults = future.result()

        results = Results()

        # Iterate through the results and store any failed download errors in
        # the errors list of the results object.
        for res in dlresults:
            if isinstance(res, FailedDownload):
                results.add_error(res.url, res.response)
            elif isinstance(res, Exception):
                raise res
            else:
                results.append(res)

        return results

    @staticmethod
    async def _get_file(session, *, url, filepath_partial, chunksize=100,
                        main_pb=None, file_pb=True, token, **kwargs):
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

        file_pb : `bool`
            Should progress bars be displayed for each file downloaded.

        token : `parfive.downloader.Token`
            A token for this download slot.

        kwargs : `dict`
            Extra keyword arguments are passed to `~aiohttp.ClientSession.get`.

        Returns
        -------

        filepath : `str`
            The name of the file saved.

        """
        try:
            async with session.get(url, **kwargs) as resp:
                if resp.status != 200:
                    raise FailedDownload(url, resp)
                else:
                    filepath = filepath_partial(resp, url)
                    fname = os.path.split(filepath)[-1]
                    if file_pb:
                        file_pb = tqdm(position=token.n, unit='B', unit_scale=True,
                                       desc=fname, leave=False)
                    else:
                        file_pb = None
                    with open(filepath, 'wb') as fd:
                        while True:
                            chunk = await resp.content.read(chunksize)
                            if not chunk:
                                # Update the main progressbar
                                if main_pb:
                                    main_pb.update(1)
                                    # Close the file progressbar
                                if file_pb is not None:
                                    file_pb.close()

                                return filepath

                            # Write this chunk to the output file.
                            fd.write(chunk)

                            # Update the progressbar for file
                            if file_pb is not None:
                                file_pb.update(chunksize)

        # Catch all the possible aiohttp errors, which are variants on failed
        # downloads and then send them to the user in the place of the response
        # object.
        except aiohttp.ClientError as e:
            raise FailedDownload(url, e)

    def _get_main_pb(self):
        """
        Return the tqdm instance if we want it, else return a contextmanager
        that just returns None.
        """
        if self.progress:
            return tqdm(total=self.queue.qsize(), unit='file',
                        desc="Files Downloaded")
        else:
            return contextlib.contextmanager(lambda: iter([None]))()

    async def _run_download(self):
        """
        Download all files in the queue.

        Returns
        -------

        results : `parfive.Results`
            A list of filenames which successfully downloaded. This list also
            has an attribute ``errors`` which lists any failed urls and their
            error.
        """
        with self._get_main_pb() as main_pb:
            async with aiohttp.ClientSession(loop=self.loop) as session:
                futures = []
                while not self.queue.empty():
                    get_file = await self.queue.get()
                    token = await self.tokens.get()
                    future = asyncio.ensure_future(get_file(session, main_pb=main_pb, token=token,
                                                            file_pb=self.file_progress))

                    def callback(token, future):
                        self.tokens.put_nowait(token)

                    future.add_done_callback(partial(callback, token))
                    futures.append(future)

                # Wait for all the coroutines to finish
                done, _ = await asyncio.wait(futures)

        # Return one future to represent all the results.
        return asyncio.gather(*done, return_exceptions=True)
