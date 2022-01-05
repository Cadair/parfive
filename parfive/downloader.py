import os
import sys
import asyncio
import logging
import pathlib
import warnings
import contextlib
import urllib.parse
from functools import partial, lru_cache
from concurrent.futures import ThreadPoolExecutor

import aiohttp
from tqdm import tqdm, tqdm_notebook

import parfive
from .results import Results
from .utils import (
    FailedDownload,
    Token,
    _QueueList,
    default_name,
    get_filepath,
    get_ftp_size,
    get_http_size,
    in_notebook,
    run_in_thread,
)

try:
    import aioftp
except ImportError:  # pragma: nocover
    aioftp = None


try:
    import aiofiles  # pragma: nocover
except ImportError:
    aiofiles = None


SERIAL_MODE = "PARFIVE_SINGLE_DOWNLOAD" in os.environ
DISABLE_RANGE = "PARFIVE_DISABLE_RANGE" in os.environ or SERIAL_MODE

__all__ = ['Downloader']


class Downloader:
    """
    Download files in parallel.

    Parameters
    ----------
    max_conn : `int`, optional
        The number of parallel download slots.
    progress : `bool`, optional
        If `True` show a main progress bar showing how many of the total files
        have been downloaded. If `False`, no progress bars will be shown at all.
    file_progress : `bool`, optional
        If `True` and ``progress`` is true, show ``max_conn`` progress bars
        detailing the progress of each individual file being downloaded.
    loop : `asyncio.AbstractEventLoop`, optional
        No longer used, and will be removed in a future release.
    notebook : `bool`, optional
        If `True` tqdm will be used in notebook mode. If `None` an attempt will
        be made to detect the notebook and guess which progress bar to use.
    overwrite : `bool` or `str`, optional
        Determine how to handle downloading if a file already exists with the
        same name. If `False` the file download will be skipped and the path
        returned to the existing file, if `True` the file will be downloaded
        and the existing file will be overwritten, if `'unique'` the filename
        will be modified to be unique.
    headers : `dict`
       Request headers to be passed to the server.
       Adds `User-Agent` information about `parfive`, `aiohttp` and `python` if not passed explicitely.
    """

    def __init__(self, max_conn=5, progress=True, file_progress=True,
                 loop=None, notebook=None, overwrite=False, headers=None,
                 use_aiofiles=False):

        if loop:
            warnings.warn('The loop argument is no longer used, and will be '
                          'removed in a future release.')
        self.max_conn = max_conn if not SERIAL_MODE else 1
        self._init_queues()

        # Configure progress bars
        if notebook is None:
            notebook = in_notebook()
        self.progress = progress
        self.file_progress = file_progress if self.progress else False
        self.tqdm = tqdm if not notebook else tqdm_notebook

        self.overwrite = overwrite

        self.headers = headers
        if headers is None or 'User-Agent' not in headers:
            self.headers = {
                'User-Agent': f"parfive/{parfive.__version__} aiohttp/{aiohttp.__version__} python/{sys.version[:5]}"}

        self._use_aiofiles = use_aiofiles

    def _init_queues(self):
        # Setup queues
        self.http_queue = _QueueList()
        self.ftp_queue = _QueueList()

    def _generate_tokens(self):
        # Create a Queue with max_conn tokens
        queue = asyncio.Queue(maxsize=self.max_conn)
        for i in range(self.max_conn):
            queue.put_nowait(Token(i + 1))
        return queue

    @property
    @lru_cache()
    def use_aiofiles(self):
        """
        aiofiles will be used if installed and must be explicitly enabled

        PARFIVE_OVERWRITE_ENABLE_AIOFILES takes precedence if present,
        aiofiles will not be used

        finally the Downloader's constructor argument is considered.
        """
        if aiofiles is None:
            return False

        if "PARFIVE_OVERWRITE_ENABLE_AIOFILES" in os.environ:
            return True

        return self._use_aiofiles

    @property
    @lru_cache()
    def default_chunk_size(self):
        """
        aiofiles requires a different default chunk size
        """
        return 1024 if self.use_aiofiles else 100

    @property
    def queued_downloads(self):
        """
        The total number of files already queued for download.
        """

        return len(self.http_queue) + len(self.ftp_queue)

    def enqueue_file(self, url, path=None, filename=None, overwrite=None, **kwargs):
        """
        Add a file to the download queue.

        Parameters
        ----------
        url : `str`
            The URL to retrieve.
        path : `str`, optional
            The directory to retrieve the file into, if `None` defaults to the
            current directory.
        filename : `str` or `callable`, optional
            The filename to save the file as. Can also be a callable which
            takes two arguments the url and the response object from opening
            that URL, and returns the filename. (Note, for FTP downloads the
            response will be ``None``.) If `None` the HTTP headers will be read
            for the filename, or the last segment of the URL will be used.
        overwrite : `bool` or `str`, optional
            Determine how to handle downloading if a file already exists with the
            same name. If `False` the file download will be skipped and the path
            returned to the existing file, if `True` the file will be downloaded
            and the existing file will be overwritten, if `'unique'` the filename
            will be modified to be unique. If `None` the value set when
            constructing the `~parfive.Downloader` object will be used.
        kwargs : `dict`
            Extra keyword arguments are passed to `aiohttp.ClientSession.get`
            or `aioftp.Client.context` depending on the protocol.

        Notes
        -----
        Proxy URL is read from the environment variables `HTTP_PROXY` or
        `HTTPS_PROXY`, depending on the protocol of the `url` passed. Proxy
        Authentication `proxy_auth` should be passed as a `aiohttp.BasicAuth`
        object. Proxy Headers `proxy_headers` should be passed as `dict`
        object.
        """
        overwrite = overwrite or self.overwrite

        if path is None and filename is None:
            raise ValueError("Either path or filename must be specified.")
        elif path is None:
            path = './'

        path = pathlib.Path(path)
        if not filename:
            filepath = partial(default_name, path)
        elif callable(filename):
            filepath = filename
        else:
            # Define a function because get_file expects a callback
            def filepath(*args):
                return path / filename

        scheme = urllib.parse.urlparse(url).scheme

        if scheme in ('http', 'https'):
            get_file = partial(self._get_http, url=url, filepath_partial=filepath,
                               overwrite=overwrite, **kwargs)
            self.http_queue.append(get_file)
        elif scheme == 'ftp':
            if aioftp is None:
                raise ValueError("The aioftp package must be installed to download over FTP.")
            get_file = partial(self._get_ftp, url=url, filepath_partial=filepath,
                               overwrite=overwrite, **kwargs)
            self.ftp_queue.append(get_file)
        else:
            raise ValueError("URL must start with either 'http' or 'ftp'.")

    @staticmethod
    def _run_in_loop(coro):
        """
        Detect an existing, running loop and run in a separate loop if needed.

        If no loop is running, use asyncio.run to run the coroutine instead.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            aio_pool = ThreadPoolExecutor(1)
            new_loop = asyncio.new_event_loop()
            return run_in_thread(aio_pool, new_loop, coro)

        return asyncio.run(coro)

    @staticmethod
    def _configure_debug():  # pragma: no cover

        sh = logging.StreamHandler()
        sh.setLevel(logging.DEBUG)

        formatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
        sh.setFormatter(formatter)

        parfive.log.addHandler(sh)
        parfive.log.setLevel(logging.DEBUG)

        aiohttp_logger = logging.getLogger('aiohttp.client')
        aioftp_logger = logging.getLogger('aioftp.client')

        aioftp_logger.addHandler(sh)
        aioftp_logger.setLevel(logging.DEBUG)

        aiohttp_logger.addHandler(sh)
        aiohttp_logger.setLevel(logging.DEBUG)

        parfive.log.debug("Configured parfive to run with debug logging...")

    async def run_download(self, timeouts=None):
        """
        Download all files in the queue.

        Parameters
        ----------
        timeouts : `dict`, optional
            Overrides for the default timeouts for http downloads. Supported
            keys are any accepted by the `aiohttp.ClientTimeout` class.
            Defaults to no timeout for total session timeout (overriding the
            aiohttp 5 minute default) and 90 seconds for socket read timeout.

        Returns
        -------
        `parfive.Results`
            A list of files downloaded.

        Notes
        -----
        The defaults for the `'total'` and `'sock_read'` timeouts can be
        overridden by two environment variables ``PARFIVE_TOTAL_TIMEOUT`` and
        ``PARFIVE_SOCK_READ_TIMEOUT``.
        """
        # Setup debug logging before starting a download
        if "PARFIVE_DEBUG" in os.environ:
            self._configure_debug()

        timeouts = timeouts or {"total": float(os.environ.get("PARFIVE_TOTAL_TIMEOUT", 0)),
                                "sock_read": float(os.environ.get("PARFIVE_SOCK_READ_TIMEOUT", 90))}

        total_files = self.queued_downloads

        done = set()
        with self._get_main_pb(total_files) as main_pb:
            if len(self.http_queue):
                done.update(await self._run_http_download(main_pb, timeouts))
            if len(self.ftp_queue):
                done.update(await self._run_ftp_download(main_pb, timeouts))

        dl_results = await asyncio.gather(*done, return_exceptions=True)

        results = Results()

        # Iterate through the results and store any failed download errors in
        # the errors list of the results object.
        for res in dl_results:
            if isinstance(res, FailedDownload):
                results.add_error(res.filepath_partial, res.url, res.exception)
                parfive.log.info(f'{res.url} failed to download with exception\n'
                                 f'{res.exception}')
            elif isinstance(res, Exception):
                raise res
            else:
                results.append(res)

        return results

    def download(self, timeouts=None):
        """
        Download all files in the queue.

        Parameters
        ----------
        timeouts : `dict`, optional
            Overrides for the default timeouts for http downloads. Supported
            keys are any accepted by the `aiohttp.ClientTimeout` class.
            Defaults to no timeout for total session timeout (overriding the
            aiohttp 5 minute default) and 90 seconds for socket read timeout.

        Returns
        -------
        `parfive.Results`
            A list of files downloaded.

        Notes
        -----
        This is a synchronous version of `~parfive.Downloader.run_download`, an
        `asyncio` event loop will be created to run the download (in it's own
        thread if a loop is already running).

        The defaults for the `'total'` and `'sock_read'` timeouts can be
        overridden by two environment variables ``PARFIVE_TOTAL_TIMEOUT`` and
        ``PARFIVE_SOCK_READ_TIMEOUT``.
        """
        return self._run_in_loop(self.run_download(timeouts))

    def retry(self, results):
        """
        Retry any failed downloads in a results object.

        .. note::
            This will start a new event loop.

        Parameters
        ----------
        results : `parfive.Results`
            A previous results object, the ``.errors`` property will be read
            and the downloads retried.

        Returns
        -------
        `parfive.Results`
            A modified version of the input ``results`` with all the errors from
            this download attempt and any new files appended to the list of
            file paths.
        """
        # Reset the queues
        self._init_queues()

        for err in results.errors:
            self.enqueue_file(err.url, filename=err.filepath_partial)

        new_res = self.download()

        results += new_res
        results._errors = new_res._errors

        return results

    @classmethod
    def simple_download(cls, urls, *, path="./", overwrite=None):
        """
        Download a series of URLs to a single destination.

        Parameters
        ----------
        urls : iterable
            A sequence of URLs to download.

        path : `pathlib.Path`, optional
            The destination directory for the downloaded files.
            Defaults to the current directory.

        overwrite: `bool`, optional
            Overwrite the files at the destination directory. If `False` the
            URL will not be downloaded if a file with the corresponding
            filename already exists.

        Returns
        -------
        `parfive.Results`
            A list of files downloaded.
        """
        dl = cls()
        for url in urls:
            dl.enqueue_file(url, path=path, overwrite=overwrite)
        return dl.download()

    def _get_main_pb(self, total):
        """
        Return the tqdm instance if we want it, else return a contextmanager
        that just returns None.
        """
        if self.progress:
            return self.tqdm(total=total, unit='file',
                             desc="Files Downloaded",
                             position=0)
        else:
            return contextlib.contextmanager(lambda: iter([None]))()

    async def _run_http_download(self, main_pb, timeouts):
        async with aiohttp.ClientSession(headers=self.headers) as session:
            self._generate_tokens()
            futures = await self._run_from_queue(
                self.http_queue.generate_queue(),
                self._generate_tokens(),
                main_pb, session=session, timeouts=timeouts)

            # Wait for all the coroutines to finish
            done, _ = await asyncio.wait(futures)

            return done

    async def _run_ftp_download(self, main_pb, timeouts):
        futures = await self._run_from_queue(
            self.ftp_queue.generate_queue(),
            self._generate_tokens(),
            main_pb, timeouts=timeouts)
        # Wait for all the coroutines to finish
        done, _ = await asyncio.wait(futures)

        return done

    async def _run_from_queue(self, queue, tokens, main_pb, *, session=None, timeouts):
        futures = []
        while not queue.empty():
            get_file = await queue.get()
            token = await tokens.get()
            file_pb = self.tqdm if self.file_progress else False
            future = asyncio.create_task(get_file(session, token=token,
                                                  file_pb=file_pb,
                                                  timeouts=timeouts))

            def callback(token, future, main_pb):
                tokens.put_nowait(token)
                # Update the main progressbar
                if main_pb and not future.exception():
                    main_pb.update(1)

            future.add_done_callback(partial(callback, token, main_pb=main_pb))
            futures.append(future)

        return futures

    async def _get_http(self, session, *, url, filepath_partial, chunksize=None,
                        file_pb=None, token, overwrite, timeouts, max_splits=5, **kwargs):
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
        file_pb : `tqdm.tqdm` or `False`
            Should progress bars be displayed for each file downloaded.
        token : `parfive.downloader.Token`
            A token for this download slot.
        max_splits: `int`
            Number of maximum concurrent connections per file.
        kwargs : `dict`
            Extra keyword arguments are passed to `aiohttp.ClientSession.get`.

        Returns
        -------
        `str`
            The name of the file saved.
        """
        if chunksize is None:
            chunksize =  self.default_chunk_size

        timeout = aiohttp.ClientTimeout(**timeouts)
        try:
            scheme = urllib.parse.urlparse(url).scheme
            if 'HTTP_PROXY' in os.environ and scheme == 'http':
                kwargs['proxy'] = os.environ['HTTP_PROXY']
            elif 'HTTPS_PROXY' in os.environ and scheme == 'https':
                kwargs['proxy'] = os.environ['HTTPS_PROXY']

            async with session.get(url, timeout=timeout, **kwargs) as resp:
                parfive.log.debug("%s request made to %s with headers=%s",
                                  resp.request_info.method,
                                  resp.request_info.url,
                                  resp.request_info.headers)
                parfive.log.debug("Response received from %s with headers=%s",
                                  resp.request_info.url,
                                  resp.headers)
                if resp.status != 200:
                    raise FailedDownload(filepath_partial, url, resp)
                else:
                    filepath, skip = get_filepath(filepath_partial(resp, url), overwrite)
                    if skip:
                        parfive.log.debug("File %s already exists and overwrite is False; skipping download.", filepath)
                        return str(filepath)
                    if callable(file_pb):
                        file_pb = file_pb(position=token.n, unit='B', unit_scale=True,
                                          desc=filepath.name, leave=False,
                                          total=get_http_size(resp))
                    else:
                        file_pb = None

                    # This queue will contain the downloaded chunks and their offsets
                    # as tuples: (offset, chunk)
                    downloaded_chunk_queue = asyncio.Queue()

                    download_workers = []
                    writer = asyncio.create_task(
                        self._write_worker(downloaded_chunk_queue, file_pb, filepath))

                    if not DISABLE_RANGE and max_splits and resp.headers.get('Accept-Ranges', None) == "bytes":
                        content_length = int(resp.headers['Content-length'])
                        split_length = max(1, content_length // max_splits)
                        ranges = [
                            [start, start + split_length]
                            for start in range(0, content_length, split_length)
                        ]
                        # let the last part download everything
                        ranges[-1][1] = ''
                        for _range in ranges:
                            download_workers.append(
                                asyncio.create_task(self._http_download_worker(
                                    session, url, chunksize, _range, timeout, downloaded_chunk_queue, **kwargs
                                ))
                            )
                    else:
                        download_workers.append(
                            asyncio.create_task(self._http_download_worker(
                                session, url, chunksize, None, timeout, downloaded_chunk_queue, **kwargs
                            ))
                        )
            # Close the initial request here before we start transferring data.

            # run all the download workers
            await asyncio.gather(*download_workers)
            # join() waits till all the items in the queue have been processed
            await downloaded_chunk_queue.join()
            writer.cancel()
            return str(filepath)

        except Exception as e:
            raise FailedDownload(filepath_partial, url, e)

    async def _write_worker(self, queue, file_pb, filepath):
        """
        Worker for writing the downloaded chunk to the file.

        The downloaded chunk is put into a asyncio Queue by a download worker.
        This worker gets the chunk from the queue and write it to the file
        using the specified offset of the chunk.

        Parameters
        ----------
        queue: `asyncio.Queue`
             Queue for chunks

        file_pb : `tqdm.tqdm` or `False`
            Should progress bars be displayed for each file downloaded.
        filepath: `pathlib.Path`
            Path to the which the file should be downloaded.
        """
        if self.use_aiofiles:
            await self._async_write_worker(queue, file_pb, filepath)
        else:
            await self._blocking_write_worker(queue, file_pb, filepath)

    async def _async_write_worker(self, queue, file_pb, filepath):
        async with aiofiles.open(filepath, mode="wb") as f:
            while True:
                offset, chunk = await queue.get()

                await f.seek(offset)
                await f.write(chunk)
                await f.flush()

                # Update the progressbar for file
                if file_pb is not None:
                    file_pb.update(len(chunk))

                queue.task_done()

    async def _blocking_write_worker(self, queue, file_pb, filepath):
        with open(filepath, "wb") as f:
            while True:
                offset, chunk = await queue.get()

                f.seek(offset)
                f.write(chunk)
                f.flush()

                # Update the progressbar for file
                if file_pb is not None:
                    file_pb.update(len(chunk))

                queue.task_done()

    async def _http_download_worker(self, session, url, chunksize, http_range, timeout, queue, **kwargs):
        """
        Worker for downloading chunks from http urls.

        This function downloads the chunk from the specified http range and puts the chunk in the
        asyncio Queue. If no range is specified, then the whole file is downloaded via chunks
        and put in the queue.

        Parameters
        ----------
        session : `aiohttp.ClientSession`
            The `aiohttp.ClientSession` to use to retrieve the files.
        url : `str`
            The url to retrieve.
        chunksize : `int`
            The number of bytes to read into the file at a time.
        http_range: (`int`, `int`) or `None`
            Start and end bytes of the file. In None, then no `Range` header is specified
            in request and the whole file will be downloaded.
        queue: `asyncio.Queue`
             Queue to put the download chunks.
        kwargs : `dict`
            Extra keyword arguments are passed to `aiohttp.ClientSession.get`.
        """
        headers = kwargs.pop('headers', {})
        if http_range:
            headers['Range'] = 'bytes={}-{}'.format(*http_range)
            # init offset to start of range
            offset, _ = http_range
        else:
            offset = 0

        async with session.get(url, timeout=timeout, headers=headers, **kwargs) as resp:
            parfive.log.debug("%s request made for download to %s with headers=%s",
                              resp.request_info.method,
                              resp.request_info.url,
                              resp.request_info.headers)
            parfive.log.debug("Response received from %s with headers=%s",
                              resp.request_info.url,
                              resp.headers)
            while True:
                chunk = await resp.content.read(chunksize)
                if not chunk:
                    break
                await queue.put((offset, chunk))
                offset += len(chunk)

    async def _get_ftp(self, session=None, *, url, filepath_partial,
                       file_pb=None, token, overwrite, timeouts, **kwargs):
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
        file_pb : `tqdm.tqdm` or `False`
            Should progress bars be displayed for each file downloaded.
        token : `parfive.downloader.Token`
            A token for this download slot.
        kwargs : `dict`
            Extra keyword arguments are passed to `~aioftp.Client.context`.

        Returns
        -------
        `str`
            The name of the file saved.
        """
        parse = urllib.parse.urlparse(url)
        try:
            async with aioftp.Client.context(parse.hostname, **kwargs) as client:
                parfive.log.debug("Connected to ftp server %s", parse.hostname)
                if parse.username and parse.password:
                    parfive.log.debug("Explicitly Logging in with %s:%s", parse.username, parse.password)
                    await client.login(parse.username, parse.password)

                # This has to be done before we start streaming the file:
                filepath, skip = get_filepath(filepath_partial(None, url), overwrite)
                if skip:
                    parfive.log.debug("File %s already exists and overwrite is False; skipping download.", filepath)
                    return str(filepath)

                if callable(file_pb):
                    total_size = await get_ftp_size(client, parse.path)
                    file_pb = file_pb(position=token.n, unit='B', unit_scale=True,
                                      desc=filepath.name, leave=False, total=total_size)
                else:
                    file_pb = None

                parfive.log.debug("Downloading file %s from %s", parse.path, parse.hostname)
                async with client.download_stream(parse.path) as stream:
                    downloaded_chunks_queue = asyncio.Queue()
                    download_workers = []
                    writer = asyncio.create_task(
                        self._write_worker(downloaded_chunks_queue, file_pb, filepath))

                    download_workers.append(
                        asyncio.create_task(self._ftp_download_worker(
                            stream, downloaded_chunks_queue))
                    )

                    await asyncio.gather(*download_workers)
                    await downloaded_chunks_queue.join()
                    writer.cancel()

                    return str(filepath)

        except Exception as e:
            raise FailedDownload(filepath_partial, url, e)

    async def _ftp_download_worker(self, stream, queue):
        """
        Similar to `Downloader._http_download_worker`.
        See that function's documentation for more info.

        Parameters
        ----------
        stream: `aioftp.StreamIO`
            Stream of the file to be downloaded.
        queue: `asyncio.Queue`
             Queue to put the download chunks.
        """
        offset = 0
        async for chunk in stream.iter_by_block():
            # Write this chunk to the output file.
            await queue.put((offset, chunk))
            offset += len(chunk)
