import os
import signal
import asyncio
import logging
import pathlib
import warnings
import threading
import contextlib
import urllib.parse
from typing import Union, Callable, Optional
from functools import reduce

try:
    from typing import Literal  # Added in Python 3.8
except ImportError:
    from typing_extensions import Literal  # type: ignore

from functools import partial

import aiohttp
from tqdm import tqdm as tqdm_std
from tqdm.auto import tqdm as tqdm_auto

import parfive
from .config import DownloaderConfig, SessionConfig
from .results import Results
from .utils import (
    FailedDownload,
    MultiPartDownloadError,
    Token,
    _QueueList,
    cancel_task,
    default_name,
    get_filepath,
    get_ftp_size,
    get_http_size,
    remove_file,
    run_task_in_thread,
)

try:
    import aioftp
except ImportError:  # pragma: nocover
    aioftp = None


__all__ = ["Downloader"]


class Downloader:
    """
    Download files in parallel.

    Parameters
    ----------
    max_conn
        The number of parallel download slots.
    max_splits
        The maximum number of splits to use to download a file (server dependent).
    progress
        If `True` show a main progress bar showing how many of the total files
        have been downloaded. If `False`, no progress bars will be shown at all.
    overwrite
        Determine how to handle downloading if a file already exists with the
        same name. If `False` the file download will be skipped and the path
        returned to the existing file, if `True` the file will be downloaded
        and the existing file will be overwritten, if `'unique'` the filename
        will be modified to be unique.
    config
        A config object containing more complex settings for this
        ``Downloader`` instance.
    """

    def __init__(
        self,
        max_conn: int = 5,
        max_splits: int = 5,
        progress: bool = True,
        overwrite: Union[bool, Literal["unique"]] = False,
        config: Optional[SessionConfig] = None,
    ):
        self.config = DownloaderConfig(
            max_conn=max_conn,
            max_splits=max_splits,
            progress=progress,
            overwrite=overwrite,
            config=config,
        )

        self._init_queues()

        # Configure progress bars
        self.tqdm = tqdm_auto
        if self.config.notebook is not None:
            if self.config.notebook is True:
                from tqdm.notebook import tqdm as tqdm_notebook

                self.tqdm = tqdm_notebook
            elif self.config.notebook is False:
                self.tqdm = tqdm_std
            else:
                raise ValueError(
                    "The notebook keyword argument should be one of None, True or False."
                )

        self._configure_logging()

    def _init_queues(self):
        # Setup queues
        self.http_queue = _QueueList()
        self.ftp_queue = _QueueList()

    def _generate_tokens(self):
        # Create a Queue with max_conn tokens
        queue = asyncio.Queue(maxsize=self.config.max_conn)
        for i in range(self.config.max_conn):
            queue.put_nowait(Token(i + 1))
        return queue

    def _configure_logging(self):  # pragma: no cover
        if self.config.log_level is None:
            return

        sh = logging.StreamHandler()
        sh.setLevel(self.config.log_level)

        formatter = logging.Formatter("%(name)s - %(levelname)s - %(message)s")
        sh.setFormatter(formatter)

        parfive.log.addHandler(sh)
        parfive.log.setLevel(self.config.log_level)

        aiohttp_logger = logging.getLogger("aiohttp.client")
        aioftp_logger = logging.getLogger("aioftp.client")

        aioftp_logger.addHandler(sh)
        aioftp_logger.setLevel(self.config.log_level)

        aiohttp_logger.addHandler(sh)
        aiohttp_logger.setLevel(self.config.log_level)

        parfive.log.debug("Configured parfive to run with debug logging...")

    @property
    def queued_downloads(self):
        """
        The total number of files already queued for download.
        """

        return len(self.http_queue) + len(self.ftp_queue)

    def enqueue_file(
        self,
        url: str,
        path: Optional[Union[str, os.PathLike]] = None,
        filename: Optional[
            Union[str, Callable[[str, Optional[aiohttp.ClientResponse]], os.PathLike]]
        ] = None,
        overwrite: Optional[Union[bool, Literal["unique"]]] = None,
        **kwargs,
    ):
        """
        Add a file to the download queue.

        Parameters
        ----------
        url
            The URL to retrieve.
        path
            The directory to retrieve the file into, if `None` defaults to the
            current directory.
        filename
            The filename to save the file as. Can also be a callable which
            takes two arguments the url and the response object from opening
            that URL, and returns the filename. (Note, for FTP downloads the
            response will be ``None``.) If `None` the HTTP headers will be read
            for the filename, or the last segment of the URL will be used.
        overwrite
            Determine how to handle downloading if a file already exists with the
            same name. If `False` the file download will be skipped and the path
            returned to the existing file, if `True` the file will be downloaded
            and the existing file will be overwritten, if `'unique'` the filename
            will be modified to be unique. If `None` the value set when
            constructing the `~parfive.Downloader` object will be used.
        kwargs : `dict`
            Extra keyword arguments are passed to `aiohttp.ClientSession.request`
            or `aioftp.Client.context` depending on the protocol.
        """
        overwrite = overwrite or self.config.overwrite

        if path is None and filename is None:
            raise ValueError("Either path or filename must be specified.")
        elif path is None:
            path = "./"

        path = pathlib.Path(path)
        filepath: Callable[[str, Optional[aiohttp.ClientResponse]], os.PathLike]
        if not filename:
            filepath = partial(default_name, path)
        elif callable(filename):
            filepath = filename
        else:
            # Define a function because get_file expects a callback
            def filepath(url, resp):
                return path / filename

        scheme = urllib.parse.urlparse(url).scheme

        if scheme in ("http", "https"):
            get_file = partial(
                self._get_http, url=url, filepath_partial=filepath, overwrite=overwrite, **kwargs
            )
            self.http_queue.append(get_file)
        elif scheme == "ftp":
            if aioftp is None:
                raise ValueError("The aioftp package must be installed to download over FTP.")
            get_file = partial(
                self._get_ftp, url=url, filepath_partial=filepath, overwrite=overwrite, **kwargs
            )
            self.ftp_queue.append(get_file)
        else:
            raise ValueError("URL must start with either 'http' or 'ftp'.")

    @staticmethod
    def _add_shutdown_signals(loop, task):
        if os.name == "nt":
            return

        if threading.current_thread() != threading.main_thread():
            warnings.warn(
                "This download has been started in a thread which is not the main thread. You will not be able to interrupt the download.",
                UserWarning,
            )
            return

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, task.cancel)

    def _run_in_loop(self, coro):
        """
        Take a coroutine and figure out where to run it and how to cancel it.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        # If we already have a loop and it's already running then we should
        # make a new loop (as we are probably in a Jupyter Notebook)
        should_run_in_thread = loop and loop.is_running()

        # If we don't already have a loop, make a new one
        if should_run_in_thread or loop is None:
            loop = asyncio.new_event_loop()

        # Wrap up the coroutine in a task so we can cancel it later
        task = loop.create_task(coro)

        # Add handlers for shutdown signals
        self._add_shutdown_signals(loop, task)

        # Execute the task
        if should_run_in_thread:
            return run_task_in_thread(loop, task)

        return loop.run_until_complete(task)

    async def run_download(self):
        """
        Download all files in the queue.

        Returns
        -------
        `parfive.Results`
            A list of files downloaded.

        """
        tasks = set()
        with self._get_main_pb(self.queued_downloads) as main_pb:
            try:
                if len(self.http_queue):
                    tasks.add(asyncio.create_task(self._run_http_download(main_pb)))
                if len(self.ftp_queue):
                    tasks.add(asyncio.create_task(self._run_ftp_download(main_pb)))
                dl_results = await asyncio.gather(*tasks, return_exceptions=True)

            except asyncio.CancelledError:
                for task in tasks:
                    task.cancel()
                dl_results = await asyncio.gather(*tasks, return_exceptions=True)

            finally:
                results_obj = self._format_results(dl_results, main_pb)
                return results_obj

    def _format_results(self, retvals, main_pb):
        # Squash all nested lists into a single flat list
        if retvals and isinstance(retvals[0], list):
            retvals = list(reduce(list.__add__, retvals))
        errors = sum([isinstance(i, FailedDownload) for i in retvals])
        if errors:
            total_files = self.queued_downloads
            message = f"{errors}/{total_files} files failed to download. Please check `.errors` for details"
            if main_pb:
                main_pb.write(message)
            else:
                parfive.log.info(message)

        results = Results()

        # Iterate through the results and store any failed download errors in
        # the errors list of the results object.
        for res in retvals:
            if isinstance(res, FailedDownload):
                results.add_error(res.filepath_partial, res.url, res.exception)
                parfive.log.info(
                    "%s failed to download with exception\n" "%s", res.url, res.exception
                )
            elif isinstance(res, Exception):
                raise res
            else:
                results.append(res)

        return results

    def download(self):
        """
        Download all files in the queue.

        Returns
        -------
        `parfive.Results`
            A list of files downloaded.

        Notes
        -----
        This is a synchronous version of `~parfive.Downloader.run_download`, an
        `asyncio` event loop will be created to run the download (in it's own
        thread if a loop is already running).
        """
        return self._run_in_loop(self.run_download())

    def retry(self, results: Results):
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
        if self.config.progress:
            return self.tqdm(total=total, unit="file", desc="Files Downloaded", position=0)
        else:
            return contextlib.contextmanager(lambda: iter([None]))()

    async def _run_http_download(self, main_pb):
        async with self.config.aiohttp_client_session() as session:
            futures = await self._run_from_queue(
                self.http_queue.generate_queue(),
                self._generate_tokens(),
                main_pb,
                session=session,
            )

            try:
                # Wait for all the coroutines to finish
                done, _ = await asyncio.wait(futures)
            except asyncio.CancelledError:
                for task in futures:
                    task.cancel()

            return await asyncio.gather(*futures, return_exceptions=True)

    async def _run_ftp_download(self, main_pb):
        futures = await self._run_from_queue(
            self.ftp_queue.generate_queue(),
            self._generate_tokens(),
            main_pb,
        )

        try:
            # Wait for all the coroutines to finish
            done, _ = await asyncio.wait(futures)
        except asyncio.CancelledError:
            for task in futures:
                task.cancel()

        return await asyncio.gather(*futures, return_exceptions=True)

    async def _run_from_queue(self, queue, tokens, main_pb, *, session=None):
        futures = []
        try:
            while not queue.empty():
                get_file = await queue.get()
                token = await tokens.get()
                file_pb = self.tqdm if self.config.file_progress else False
                future = asyncio.create_task(get_file(session, token=token, file_pb=file_pb))

                def callback(token, future, main_pb):
                    try:
                        tokens.put_nowait(token)
                        # Update the main progressbar
                        if main_pb and not future.exception():
                            main_pb.update(1)
                    except asyncio.CancelledError:
                        return

                future.add_done_callback(partial(callback, token, main_pb=main_pb))
                futures.append(future)

        except asyncio.CancelledError:
            for task in futures:
                task.cancel()

        return futures

    async def _get_http(
        self,
        session,
        *,
        url,
        filepath_partial,
        chunksize=None,
        file_pb=None,
        token,
        overwrite,
        max_splits=None,
        **kwargs,
    ):
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
        overwrite : `bool`
            Overwrite the file if it already exists.
        max_splits: `int`, optional
            Number of maximum concurrent connections per file.
        kwargs : `dict`
            Extra keyword arguments are passed to `aiohttp.ClientSession.get`.

        Returns
        -------
        `str`
            The name of the file saved.
        """
        if chunksize is None:
            chunksize = 1024
        if max_splits is None:
            max_splits = self.config.max_splits

        # Define filepath and writer here as we use them in the except block
        filepath = writer = None
        tasks = []
        try:
            scheme = urllib.parse.urlparse(url).scheme
            if scheme == "http":
                kwargs["proxy"] = self.config.http_proxy
            elif scheme == "https":
                kwargs["proxy"] = self.config.https_proxy

            async with session.get(url, timeout=self.config.timeouts, **kwargs) as resp:
                parfive.log.debug(
                    "%s request made to %s with headers=%s",
                    resp.request_info.method,
                    resp.request_info.url,
                    resp.request_info.headers,
                )
                parfive.log.debug(
                    "%s Response received from %s with headers=%s",
                    resp.status,
                    resp.request_info.url,
                    resp.headers,
                )
                if resp.status < 200 or resp.status >= 300:
                    raise FailedDownload(filepath_partial, url, resp)
                else:
                    filepath, skip = get_filepath(filepath_partial(resp, url), overwrite)
                    if skip:
                        parfive.log.debug(
                            "File %s already exists and overwrite is False; skipping download.",
                            filepath,
                        )
                        return str(filepath)
                    if callable(file_pb):
                        file_pb = file_pb(
                            position=token.n,
                            unit="B",
                            unit_scale=True,
                            desc=filepath.name,
                            leave=False,
                            total=get_http_size(resp),
                        )
                    else:
                        file_pb = None

                    # This queue will contain the downloaded chunks and their offsets
                    # as tuples: (offset, chunk)
                    downloaded_chunk_queue = asyncio.Queue()

                    writer = asyncio.create_task(
                        self._write_worker(downloaded_chunk_queue, file_pb, filepath)
                    )

                    if (
                        not self.config.env.disable_range
                        and max_splits
                        and resp.headers.get("Accept-Ranges", None) == "bytes"
                        and "Content-length" in resp.headers
                    ):
                        content_length = int(resp.headers["Content-length"])
                        split_length = max(1, content_length // max_splits)
                        ranges = [
                            [start, start + split_length]
                            for start in range(0, content_length, split_length)
                        ]
                        # let the last part download everything
                        ranges[-1][1] = ""
                        for _range in ranges:
                            tasks.append(
                                asyncio.create_task(
                                    self._http_download_worker(
                                        session,
                                        url,
                                        chunksize,
                                        _range,
                                        downloaded_chunk_queue,
                                        **kwargs,
                                    )
                                )
                            )
                    else:
                        tasks.append(
                            asyncio.create_task(
                                self._http_download_worker(
                                    session,
                                    url,
                                    chunksize,
                                    None,
                                    downloaded_chunk_queue,
                                    **kwargs,
                                )
                            )
                        )
            # Close the initial request here before we start transferring data.

            # run all the download workers
            await asyncio.gather(*tasks)
            # join() waits till all the items in the queue have been processed
            await downloaded_chunk_queue.join()
            for callback in self.config.done_callbacks:
                callback(filepath, url, None)
            return str(filepath)

        except (Exception, asyncio.CancelledError) as e:
            for task in tasks:
                task.cancel()
            # We have to cancel the writer here before we try and remove the
            # file so it's closed (otherwise windows gets angry).
            if writer is not None:
                await cancel_task(writer)
                # Set writer to None so we don't cancel it twice.
                writer = None
            # If filepath is None then the exception occurred before the request
            # computed the filepath, so we have no file to cleanup
            if filepath is not None:
                remove_file(filepath)
            for callback in self.config.done_callbacks:
                callback(filepath, url, e)
            raise FailedDownload(filepath_partial, url, e)

        finally:
            if writer is not None:
                writer.cancel()
            if isinstance(file_pb, self.tqdm):
                file_pb.close()

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
        if self.config.use_aiofiles:
            await self._async_write_worker(queue, file_pb, filepath)
        else:
            await self._blocking_write_worker(queue, file_pb, filepath)

    async def _async_write_worker(self, queue, file_pb, filepath):
        import aiofiles

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

    async def _http_download_worker(self, session, url, chunksize, http_range, queue, **kwargs):
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
        headers = kwargs.pop("headers", {})
        if http_range:
            headers["Range"] = "bytes={}-{}".format(*http_range)
            # init offset to start of range
            offset, _ = http_range
        else:
            offset = 0

        async with session.get(url, timeout=self.config.timeouts, headers=headers, **kwargs) as resp:
            parfive.log.debug(
                "%s request made for download to %s with headers=%s",
                resp.request_info.method,
                resp.request_info.url,
                resp.request_info.headers,
            )
            parfive.log.debug(
                "%s Response received from %s with headers=%s",
                resp.status,
                resp.request_info.url,
                resp.headers,
            )

            if resp.status < 200 or resp.status >= 300:
                raise MultiPartDownloadError(resp)

            while True:
                chunk = await resp.content.read(chunksize)
                if not chunk:
                    break
                await queue.put((offset, chunk))
                offset += len(chunk)

    async def _get_ftp(
        self,
        session=None,
        *,
        url,
        filepath_partial,
        file_pb=None,
        token,
        overwrite,
        **kwargs,
    ):
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
        overwrite : `bool`
            Whether to overwrite the file if it already exists.
        kwargs : `dict`
            Extra keyword arguments are passed to `aioftp.Client.context`.

        Returns
        -------
        `str`
            The name of the file saved.
        """
        filepath = writer = None
        parse = urllib.parse.urlparse(url)
        try:
            async with aioftp.Client.context(parse.hostname, **kwargs) as client:
                parfive.log.debug("Connected to ftp server %s", parse.hostname)
                if parse.username and parse.password:
                    parfive.log.debug(
                        "Explicitly Logging in with %s:%s", parse.username, parse.password
                    )
                    await client.login(parse.username, parse.password)

                # This has to be done before we start streaming the file:
                filepath, skip = get_filepath(filepath_partial(None, url), overwrite)
                if skip:
                    parfive.log.debug(
                        "File %s already exists and overwrite is False; skipping download.",
                        filepath,
                    )
                    return str(filepath)

                if callable(file_pb):
                    total_size = await get_ftp_size(client, parse.path)
                    file_pb = file_pb(
                        position=token.n,
                        unit="B",
                        unit_scale=True,
                        desc=filepath.name,
                        leave=False,
                        total=total_size,
                    )
                else:
                    file_pb = None

                parfive.log.debug("Downloading file %s from %s", parse.path, parse.hostname)
                async with client.download_stream(parse.path) as stream:
                    downloaded_chunks_queue = asyncio.Queue()
                    download_workers = []
                    writer = asyncio.create_task(
                        self._write_worker(downloaded_chunks_queue, file_pb, filepath)
                    )

                    download_workers.append(
                        asyncio.create_task(
                            self._ftp_download_worker(stream, downloaded_chunks_queue)
                        )
                    )

                    await asyncio.gather(*download_workers)
                    await downloaded_chunks_queue.join()

                    for callback in self.config.done_callbacks:
                        callback(filepath, url, None)

                    return str(filepath)

        except (Exception, asyncio.CancelledError) as e:
            if writer is not None:
                await cancel_task(writer)
                writer = None
            # If filepath is None then the exception occurred before the request
            # computed the filepath, so we have no file to cleanup
            if filepath is not None:
                remove_file(filepath)
                filepath = None

            for callback in self.config.done_callbacks:
                callback(filepath, url, e)

            raise FailedDownload(filepath_partial, url, e)

        finally:
            # Just make sure we close the file.
            if writer is not None:
                writer.cancel()
            if isinstance(file_pb, self.tqdm):
                file_pb.close()

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
