import os
import asyncio
import hashlib
import pathlib
import warnings
from typing import TYPE_CHECKING, Any, Dict, List, Tuple, Union, TypeVar, Generator
from pathlib import Path
from itertools import count
from concurrent.futures import ThreadPoolExecutor

import aiohttp

import parfive

if TYPE_CHECKING:
    import aioftp


__all__ = [
    "cancel_task",
    "run_in_thread",
    "Token",
    "FailedDownload",
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


def parse_header(line: str) -> Tuple[str, Dict[str, str]]:
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
    except Exception:
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


def get_filepath(filepath: os.PathLike, overwrite: bool) -> Tuple[Union[Path, str], bool]:
    """
    Get the filepath to download to and ensure dir exists.

    Returns
    -------
    `pathlib.Path`, `bool`
    """
    filepath = pathlib.Path(filepath)
    if filepath.exists():
        if not overwrite:
            return str(filepath), True
        if overwrite == "unique":
            filepath = replacement_filename(filepath)
    if not filepath.parent.exists():
        filepath.parent.mkdir(parents=True)

    return filepath, False


def sha256sum(filename: str) -> str:
    """
    https://stackoverflow.com/a/44873382
    """
    h = hashlib.sha256()
    b = bytearray(128 * 1024)
    mv = memoryview(b)
    with open(filename, "rb", buffering=0) as f:
        for n in iter(lambda: f.readinto(mv), 0):
            h.update(mv[:n])
    return h.hexdigest()


class MultiPartDownloadError(Exception):
    def __init__(self, response: aiohttp.ClientResponse) -> None:
        self.response = response


class FailedDownload(Exception):
    def __init__(self, filepath_partial: Path, url: str, exception: BaseException) -> None:
        self.filepath_partial = filepath_partial
        self.url = url
        self.exception = exception
        super().__init__()

    def __repr__(self) -> str:
        out = super().__repr__()
        out += f"\n {self.url} {self.exception}"
        return out

    def __str__(self) -> str:
        return f"Download Failed: {self.url} with error {str(self.exception)}"


class Token:
    def __init__(self, n: int) -> None:
        self.n = n

    def __repr__(self) -> str:
        return super().__repr__() + f"n = {self.n}"

    def __str__(self) -> str:
        return f"Token {self.n}"


_T = TypeVar("_T")


class _QueueList(List[_T]):
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
    except Exception as remove_exception:
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
