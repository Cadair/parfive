# import os
import asyncio
import pathlib
import contextlib
import urllib.parse
from functools import partial
from collections import UserList, namedtuple
from concurrent.futures import ThreadPoolExecutor

import aiohttp
import aioftp
from tqdm import tqdm, tqdm_notebook


def in_notebook():
    try:
        import ipykernel.zmqshell
        shell = get_ipython()  # noqa
        return isinstance(shell, ipykernel.zmqshell.ZMQInteractiveShell)
    except Exception:
        return False


def default_name(path, resp, url):
    url_filename = url.split('/')[-1]
    if resp:
        name = resp.headers.get("Content-Disposition", url_filename)
    else:
        name = url_filename
    return pathlib.Path(path) / name


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

    def _get_nice_resp_repr(self, response):
        # This is a modified version of aiohttp.ClientResponse.__repr__
        if isinstance(response, aiohttp.ClientResponse):
            ascii_encodable_url = str(response.url)
            if response.reason:
                ascii_encodable_reason = response.reason.encode('ascii',
                                                                'backslashreplace').decode('ascii')
            else:
                ascii_encodable_reason = response.reason
            return '<ClientResponse({}) [{} {}]>'.format(
                ascii_encodable_url, response.status, ascii_encodable_reason)
        else:
            return repr(response)

    def __str__(self):
        out = super().__repr__()
        if self.errors:
            out += '\nErrors:\n'
            for error in self.errors:
                resp = self._get_nice_resp_repr(error.response)
                out += "(url={}, response={})\n".format(error.url, resp)
        return out

    def __repr__(self):
        out = object.__repr__(self)
        out += '\n'
        out += str(self)
        return out

    def add_error(self, url, response):
        """
        Add an error to the results.
        """
        if isinstance(response, aiohttp.ClientResponse):
            response._headers = None
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


def run_in_thread(aio_pool, loop, coro):
    """
    This function returns the asyncio Future after running the loop in a
    thread. This makes the return value of this function the same as the return
    of ``loop.run_until_complete``.
    """
    return aio_pool.submit(loop.run_until_complete, coro).result()


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
        The event loop to use to download the files. If not specified a new
        loop will be created and executed in a new thread so it does not
        interfere with any currently running event loop.

    notebook : `bool`
        If `True` tqdm will be used in notebook mode. If `None` an attempt will
        be made to detect the notebook and guess which progress bar to use.
    """

    def __init__(self, max_conn=5, progress=True, file_progress=True, loop=None, notebook=None):
        # Setup asyncio loops
        if not loop:
            aio_pool = ThreadPoolExecutor(1)
            self.loop = asyncio.new_event_loop()
            self.run_until_complete = partial(run_in_thread, aio_pool, self.loop)
        else:
            self.loop = loop
            self.run_until_complete = self.loop.run_until_complete

        # Setup queues
        self.http_queue = asyncio.Queue(loop=self.loop)
        self.http_tokens = asyncio.Queue(maxsize=max_conn, loop=self.loop)
        self.ftp_queue = asyncio.Queue(loop=self.loop)
        self.ftp_tokens = asyncio.Queue(maxsize=max_conn, loop=self.loop)
        for i in range(max_conn):
            self.http_tokens.put_nowait(Token(i+1))
            self.ftp_tokens.put_nowait(Token(i+1))

        # Configure progress bars
        if notebook is None:
            notebook = in_notebook()
        self.progress = progress
        self.file_progress = file_progress if self.progress else False
        self.tqdm = tqdm if not notebook else tqdm_notebook

    def enqueue_file(self, url, path=None, filename=None, **kwargs):
        """
        Add a file to the download queue.

        Parameters
        ----------

        url : `str`
            The URL to retrieve.

        path : `str`
            The directory to retrieve the file into.

        filename : `str` or `callable`
            The filename to save the file as. Can also be a callable which
            takes no arguments and returns the path.

        chunksize : `int`
            The size (in bytes) of the chunks to be downloaded for HTTP downloads.

        kwargs : `dict`
            Extra keyword arguments are passed to `aiohttp.ClientSession.get`.
        """
        if path is None and filename is None:
            raise ValueError("either path or filename must be specified.")
        if not filename:
            filepath = partial(default_name, path)
        elif callable(filename):
            filepath = filename
        else:
            # Define a function because get_file expects a callback
            def filepath(*args): return filename

        if url.startswith("http"):
            get_file = partial(self._get_http, url=url, filepath_partial=filepath, **kwargs)
            self.http_queue.put_nowait(get_file)
        elif url.startswith("ftp"):
            get_file = partial(self._get_ftp, url=url, filepath_partial=filepath, **kwargs)
            self.ftp_queue.put_nowait(get_file)
        else:
            raise ValueError("url must start with either http or ftp")

    def download(self):
        """
        Download all files in the queue.

        Returns
        -------
        filenames : `parfive.Results`
            A list of files downloaded.
        """
        future = self.run_until_complete(self._run_download())
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

    def _get_main_pb(self, total):
        """
        Return the tqdm instance if we want it, else return a contextmanager
        that just returns None.
        """
        if self.progress:
            return self.tqdm(total=total, unit='file',
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
        total_files = self.http_queue.qsize() + self.ftp_queue.qsize()
        done = set()
        with self._get_main_pb(total_files) as main_pb:
            if not self.http_queue.empty():
                done.update(await self._run_http_download(main_pb))
            if not self.ftp_queue.empty():
                done.update(await self._run_ftp_download(main_pb))

        # Return one future to represent all the results.
        return asyncio.gather(*done, return_exceptions=True)

    async def _run_from_queue(self, queue, tokens, main_pb, session=None):
        futures = []
        while not queue.empty():
            get_file = await queue.get()
            token = await tokens.get()
            file_pb = self.tqdm if self.file_progress else False
            future = asyncio.ensure_future(get_file(session, main_pb=main_pb, token=token,
                                                    file_pb=file_pb))

            def callback(token, future):
                tokens.put_nowait(token)

            future.add_done_callback(partial(callback, token))
            futures.append(future)

        return futures

    async def _run_ftp_download(self, main_pb):
        futures = await self._run_from_queue(self.ftp_queue, self.ftp_tokens, main_pb)
        # Wait for all the coroutines to finish
        done, _ = await asyncio.wait(futures)

        return done

    async def _run_http_download(self, main_pb):
        async with aiohttp.ClientSession(loop=self.loop) as session:
            futures = await self._run_from_queue(self.http_queue, self.http_tokens,
                                                 main_pb, session)

            # Wait for all the coroutines to finish
            done, _ = await asyncio.wait(futures)

            return done

    @staticmethod
    async def _get_http(session, *, url, filepath_partial, chunksize=100,
                        main_pb=None, file_pb=None, token, **kwargs):
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

        file_pb : `tqdm.tqdm` or `False`
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
                    filepath = pathlib.Path(filepath_partial(resp, url))
                    if not filepath.parent.exists():
                        filepath.parent.mkdir(parents=True)
                    fname = filepath.name
                    if callable(file_pb):
                        file_pb = file_pb(position=token.n, unit='B', unit_scale=True,
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

                                return str(filepath)

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

    @staticmethod
    async def _get_ftp(session=None, *, url, filepath_partial,
                       main_pb=None, file_pb=None, token, **kwargs):
        """
        Read the file from the given url into the filename given by ``filepath_partial``.

        Parameters
        ----------

        session : `None`
            A placeholder for API compatibility with ``_get_http``

        url : `str`
            The url to retrieve.

        filepath_partial : `callable`
            A function to call which returns the filepath to save the url to.
            Takes two arguments ``resp, url``.

        main_pb : `tqdm.tqdm`
            Optional progressbar instance to advance when file is complete.

        file_pb : `tqdm.tqdm` or `False`
            Should progress bars be displayed for each file downloaded.

        token : `parfive.downloader.Token`
            A token for this download slot.

        kwargs : `dict`
            Extra keyword arguments are passed to `~aioftp.ClientSession`.

        Returns
        -------

        filepath : `str`
            The name of the file saved.

        """
        parse = urllib.parse.urlparse(url)
        try:
            async with aioftp.ClientSession(parse.hostname, **kwargs) as client:
                if parse.username and parse.password:
                    client.login(parse.username, parse.password)
                async with client.download_stream(parse.path) as stream:
                    filepath = pathlib.Path(filepath_partial(None, url))
                    if not filepath.parent.exists():
                        filepath.parent.mkdir(parents=True)
                    fname = filepath.name
                    if callable(file_pb):
                        file_pb = file_pb(position=token.n, unit='B', unit_scale=True,
                                          desc=fname, leave=False)
                    else:
                        file_pb = None

                    with open(filepath, 'wb') as fd:
                        async for chunk in stream.iter_by_block():
                            # Write this chunk to the output file.
                            fd.write(chunk)

                            # Update the progressbar for file
                            if file_pb is not None:
                                file_pb.update(len(chunk))

                        # Update the main progressbar
                        if main_pb:
                            main_pb.update(1)
                        # Close the file progressbar
                        if file_pb is not None:
                            file_pb.close()

                        return str(filepath)

        # Catch all the possible aioftp errors, and socket errors (when a
        # server is not found) which are variants on failed downloads and then
        # send them to the user in the place of the response object.
        except (aioftp.StatusCodeError, OSError) as e:
            raise FailedDownload(url, e)
