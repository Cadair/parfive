import cgi
import asyncio
import hashlib
import pathlib
from itertools import count

import parfive

__all__ = ['run_in_thread', 'Token', 'FailedDownload', 'default_name',
           'in_notebook']


def in_notebook():
    try:
        import ipykernel.zmqshell
        shell = get_ipython()  # noqa
        if isinstance(shell, ipykernel.zmqshell.ZMQInteractiveShell):
            try:
                # Newer tqdm
                import tqdm.notebook
                return tqdm.notebook.IPY > 0
            except ImportError:
                # Older tqdm
                try:
                    # Check that we can import the right widget
                    from tqdm import _tqdm_notebook
                    _tqdm_notebook.IntProgress
                except Exception:
                    return False
            except Exception:
                return False
            return True
        return False
    except Exception:
        return False


def default_name(path, resp, url):
    url_filename = url.split('/')[-1]
    if resp:
        cdheader = resp.headers.get("Content-Disposition", None)
        if cdheader:
            value, params = cgi.parse_header(cdheader)
            name = params.get('filename', url_filename)
        else:
            name = url_filename
    else:
        name = url_filename
    return pathlib.Path(path) / name


def run_in_thread(aio_pool, loop, coro):
    """
    This function returns the asyncio Future after running the loop in a
    thread.

    This makes the return value of this function the same as the return
    of ``loop.run_until_complete``.
    """
    return aio_pool.submit(loop.run_until_complete, coro).result()


async def get_ftp_size(client, filepath):
    """
    Given an `aioftp.ClientSession` object get the expected size of the file,
    return ``None`` if the size can not be determined.
    """
    try:
        size = await client.stat(filepath)
        size = size.get("size", None)
    except Exception:
        parfive.log.exception("Failed to get size of FTP file")
        size = None

    return int(size) if size else size


def get_http_size(resp):
    size = resp.headers.get("content-length", None)
    return int(size) if size else size


def replacement_filename(path):
    """
    Given a path generate a unique filename.
    """
    path = pathlib.Path(path)

    if not path.exists:
        return path

    suffix = ''.join(path.suffixes)
    for c in count(1):
        if suffix:
            name, _ = path.name.split(suffix)
        else:
            name = path.name
        new_name = f"{name}.{c}{suffix}"
        new_path = path.parent / new_name
        if not new_path.exists():
            return new_path


def get_filepath(filepath, overwrite):
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
        if overwrite == 'unique':
            filepath = replacement_filename(filepath)
    if not filepath.parent.exists():
        filepath.parent.mkdir(parents=True)

    return filepath, False


def sha256sum(filename):
    """
    https://stackoverflow.com/a/44873382
    """
    h = hashlib.sha256()
    b = bytearray(128 * 1024)
    mv = memoryview(b)
    with open(filename, 'rb', buffering=0) as f:
        for n in iter(lambda: f.readinto(mv), 0):
            h.update(mv[:n])
    return h.hexdigest()


class FailedDownload(Exception):
    def __init__(self, filepath_partial, url, exception):
        self.filepath_partial = filepath_partial
        self.url = url
        self.exception = exception
        super().__init__()

    def __repr__(self):
        out = super().__repr__()
        out += f'\n {self.url} {self.exception}'
        return out

    def __str__(self):
        return "Download Failed: {} with error {}".format(self.url, str(self.exception))


class Token:
    def __init__(self, n):
        self.n = n

    def __repr__(self):
        return super().__repr__() + f"n = {self.n}"

    def __str__(self):
        return f"Token {self.n}"


class _QueueList(list):
    """
    A list, with an extra method that empties the list and puts it into a
    `asyncio.Queue`.

    Creating the queue can only be done inside a running asyncio loop.
    """

    def generate_queue(self, maxsize=0):
        queue = asyncio.Queue(maxsize=maxsize)
        for item in self:
            queue.put_nowait(item)
        self.clear()
        return queue
