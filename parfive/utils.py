import pathlib

__all__ = ['run_in_thread', 'Token', 'FailedDownload', 'default_name', 'in_notebook']


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
