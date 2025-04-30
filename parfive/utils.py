import asyncio
import hashlib
import io
import os
import pathlib
import typing
import warnings
from collections.abc import AsyncIterator, Generator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from itertools import count
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Literal, TypeVar, Union

import aiohttp

import parfive

if TYPE_CHECKING:
    import aioftp


__all__ = [
    "FailedDownload",
    "Token",
    "cancel_task",
    "default_name",
    "remove_file",
]


# Copied out of CPython under PSF Licence 2
def _parseparam(s: str) -> Generator[str, None, None]:
    while s[:1] == ";":
        s = s[1:]
        end = s.find(";")
        while end > 0 and (s.count('"', 0, end) - s.count('\\"', 0, end)) % 2:
            end = s.find(";", end + 1)
        if end < 0:
            end = len(s)
        f = s[:end]
        yield f.strip()
        s = s[end:]


def parse_header(line: str) -> tuple[str, dict[str, str]]:
    """Parse a Content-type like header.
    Return the main content-type and a dictionary of options.
    """
    parts = _parseparam(";" + line)
    key = parts.__next__()
    pdict = {}
    for p in parts:
        i = p.find("=")
        if i >= 0:
            name = p[:i].strip().lower()
            value = p[i + 1 :].strip()
            if len(value) >= 2 and value[0] == value[-1] == '"':
                value = value[1:-1]
                value = value.replace("\\\\", "\\").replace('\\"', '"')
            pdict[name] = value
    return key, pdict


def default_name(path: os.PathLike, resp: aiohttp.ClientResponse, url: str) -> os.PathLike:
    url_filename = url.split("/")[-1]
    if resp:
        cdheader = resp.headers.get("Content-Disposition", None)
        if cdheader:
            value, params = parse_header(cdheader)
            name = params.get("filename", url_filename)
        else:
            name = url_filename
    else:
        name = url_filename
    return pathlib.Path(path) / name


def run_task_in_thread(loop: asyncio.BaseEventLoop, coro: asyncio.Task) -> Any:
    """
    This function returns the asyncio Future after running the loop in a
    thread.

    This makes the return value of this function the same as the return
    of ``loop.run_until_complete``.
    """
    with ThreadPoolExecutor(max_workers=1) as aio_pool:
        try:
            future = aio_pool.submit(loop.run_until_complete, coro)
        except KeyboardInterrupt:
            future.cancel()
    return future.result()


async def get_ftp_size(client: "aioftp.Client", filepath: os.PathLike) -> int:
    """
    Given an `aioftp.ClientSession` object get the expected size of the file,
    return ``None`` if the size can not be determined.
    """
    try:
        size = await client.stat(filepath)
        size = size.get("size", None)
    except Exception:  # noqa BLE001
        parfive.log.info("Failed to get size of FTP file", exc_info=True)
        size = None

    return int(size) if size else size


def get_http_size(resp: aiohttp.ClientResponse) -> Union[int, str, None]:
    size = resp.headers.get("content-length", None)
    return int(size) if size else size


def replacement_filename(path: os.PathLike) -> Path:  # type: ignore[return]
    """
    Given a path generate a unique filename.
    """
    path = pathlib.Path(path)

    if not path.exists():
        return path

    suffix = "".join(path.suffixes)
    for c in count(start=1):
        if suffix:
            name, _ = path.name.split(suffix)
        else:
            name = path.name
        new_name = f"{name}.{c}{suffix}"
        new_path = path.parent / new_name
        if not new_path.exists():
            return new_path


def get_filepath(filepath: os.PathLike, overwrite: Union[bool, Literal["unique"]]) -> tuple[Path, bool]:
    """
    Get the filepath to download to and ensure dir exists.

    Returns
    -------
    `pathlib.Path`, `bool`
    """
    filepath = pathlib.Path(filepath)
    if filepath.exists():
        if not overwrite:
            return filepath, True
        if overwrite == "unique":
            filepath = replacement_filename(filepath)
    if not filepath.parent.exists():
        filepath.parent.mkdir(parents=True)

    return filepath, False


class MultiPartDownloadError(Exception):
    def __init__(self, response: aiohttp.ClientResponse) -> None:
        self.response = response


class FailedDownload(Exception):
    def __init__(self, filepath_partial: Union[Path, Callable], url: str, exception: BaseException) -> None:
        self.filepath_partial = filepath_partial
        self.url = url
        self.exception = exception
        super().__init__()

    def __repr__(self) -> str:
        out = super().__repr__()
        out += f"\n {self.url} {self.exception}"
        return out

    def __str__(self) -> str:
        return f"Download Failed: {self.url} with error {self.exception!s}"


class ChecksumMismatch(Exception):
    """Used when a checksum doesn't match."""


class Token:
    def __init__(self, n: int) -> None:
        self.n = n

    def __repr__(self) -> str:
        return super().__repr__() + f"n = {self.n}"

    def __str__(self) -> str:
        return f"Token {self.n}"


_T = TypeVar("_T")


class _QueueList(list[_T]):
    """
    A list, with an extra method that empties the list and puts it into a
    `asyncio.Queue`.

    Creating the queue can only be done inside a running asyncio loop.
    """

    def generate_queue(self, maxsize: int = 0) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        for item in self:
            queue.put_nowait(item)
        self.clear()
        return queue


class ParfiveUserWarning(UserWarning):
    """
    Raised for not-quite errors.
    """


class ParfiveFutureWarning(FutureWarning):
    """
    Raised for future changes to the parfive API.
    """


def remove_file(filepath: os.PathLike) -> None:
    """
    Remove the file from the disk, if it exists
    """
    filepath = Path(filepath)
    try:
        filepath.unlink(missing_ok=True)
    except Exception as remove_exception:  # noqa BLE001
        warnings.warn(
            f"Failed to delete possibly incomplete file {filepath} {remove_exception}",
            ParfiveUserWarning,
        )


async def cancel_task(task: asyncio.Task) -> bool:
    """
    Call cancel on a task and then wait for it to exit.

    Return True if the task was cancelled, False otherwise.
    """
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        return True
    return task.cancelled()


try:
    # Python 3.11 added file_digest
    from hashlib import file_digest
except ImportError:
    import hashlib

    # Copied from the stdlib
    @typing.no_type_check
    def file_digest(fileobj, digest, /, *, _bufsize=2**18):
        """
        Hash the contents of a file-like object. Returns a digest object.

        *fileobj* must be a file-like object opened for reading in binary mode.
        It accepts file objects from open(), io.BytesIO(), and SocketIO objects.
        The function may bypass Python's I/O and use the file descriptor *fileno*
        directly.

        *digest* must either be a hash algorithm name as a *str*, a hash
        constructor, or a callable that returns a hash object.
        """
        # On Linux we could use AF_ALG sockets and sendfile() to archive zero-copy
        # hashing with hardware acceleration.
        if isinstance(digest, str):
            digestobj = hashlib.new(digest)
        else:
            digestobj = digest()

        if hasattr(fileobj, "getbuffer"):
            # io.BytesIO object, use zero-copy buffer
            digestobj.update(fileobj.getbuffer())
            return digestobj

        # Only binary files implement readinto().
        if not (hasattr(fileobj, "readinto") and hasattr(fileobj, "readable") and fileobj.readable()):
            raise ValueError(f"'{fileobj!r}' is not a file-like object in binary reading mode.")

        # binary file, socket.SocketIO object
        # Note: socket I/O uses different syscalls than file I/O.
        buf = bytearray(_bufsize)  # Reusable buffer to reduce allocations.
        view = memoryview(buf)
        while True:
            size = fileobj.readinto(buf)
            if size is None:
                raise BlockingIOError("I/O operation would block.")
            if size == 0:
                break  # EOF
            digestobj.update(view[:size])

        return digestobj


def validate_checksum_format(checksum: str) -> tuple[str, str]:
    if "=" not in checksum:
        raise ValueError(f"checksum '{checksum}' should be of the format <algorithm>=<checksum>")
    chk_alg, checksum = checksum.split("=")
    # Normalise the algorithm name to not have "-" as that might have wider support
    chk_alg = chk_alg.replace("-", "")
    if chk_alg not in hashlib.algorithms_available:
        raise ValueError(f"checksum type '{chk_alg}' is not supported.")
    return chk_alg, checksum


def check_file_hash(fileobj: io.BufferedReader, checksum: str, accept_invalid_checksum: bool = False) -> bool:
    """
    Verify the contents of fileobj match the checksum provided by ``checksum``.
    """
    try:
        chk_alg, checksum = validate_checksum_format(checksum)
    except ValueError as e:
        if not accept_invalid_checksum:
            raise
        parfive.log.error("Got invalid checksum: %s", e)
        # Allow invalid checksums to match
        return True

    computed_file_hash = file_digest(fileobj, chk_alg).hexdigest()
    return computed_file_hash == checksum


@asynccontextmanager
async def session_head_or_get(session: aiohttp.ClientSession, url: str, **kwargs: dict) -> AsyncIterator:
    """
    Try and make a HEAD request to the resource and fallback to a get
    request if that fails.
    """
    async with session.head(url, **kwargs) as resp:
        if resp.status == 200:
            yield resp
            return

    async with session.get(url, **kwargs) as resp:
        yield resp
