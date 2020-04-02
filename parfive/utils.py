import cgi
import pathlib
from itertools import count

__all__ = ['run_in_thread', 'Token', 'FailedDownload', 'default_name', 'in_notebook']


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
    thread. This makes the return value of this function the same as the return
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
        new_name = "{name}.{c}{suffix}".format(name=name, c=c, suffix=suffix)
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


class FailedDownload(Exception):
    def __init__(self, filepath_partial, url, exception):
        self.filepath_partial = filepath_partial
        self.url = url
        self.exception = exception
        super().__init__()

    def __repr__(self):
        out = super().__repr__()
        out += '\n {} {}'.format(self.url, self.exception)
        return out

    def __str__(self):
        return "Download Failed: {} with error {}".format(self.url, str(self.exception))


class Token:
    def __init__(self, n):
        self.n = n

    def __repr__(self):
        return super().__repr__() + "n = {}".format(self.n)

    def __str__(self):
        return "Token {}".format(self.n)
