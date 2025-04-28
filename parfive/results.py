from collections import UserList, namedtuple

import aiohttp

from .utils import FailedDownload

__all__ = ["Results"]


class Error(namedtuple("error", ("filepath_partial", "url", "exception"))):
    def __str__(self):
        filepath_partial = ""
        if isinstance(self.filepath_partial, str):
            filepath_partial = f"{self.filepath_partial},\n"
        return filepath_partial + f"{self.url},\n{self.exception}"

    def __repr__(self):
        return f"{object.__repr__(self)}\n{self}"


class Results(UserList):
    """
    The results of a download from `parfive.Downloader.download`.

    This object contains the filenames of successful downloads as well,
    a list of all urls requested in the `~parfive.Results.urls` property
    and a list of any errors encountered in the `~parfive.Results.errors`
    property.
    """

    def __init__(self, *args, errors=None, urls=None):
        super().__init__(*args)
        self._errors = errors or []
        self._urls = urls or []

    def _get_nice_resp_repr(self, response):
        # This is a modified version of aiohttp.ClientResponse.__repr__
        if isinstance(response, aiohttp.ClientResponse):
            ascii_encodable_url = str(response.url)
            if response.reason:
                ascii_encodable_reason = response.reason.encode("ascii", "backslashreplace").decode("ascii")
            else:
                ascii_encodable_reason = response.reason
            return f"<ClientResponse({ascii_encodable_url}) [{response.status} {ascii_encodable_reason}]>"
        return repr(response)

    def __str__(self):
        out = super().__repr__()
        if self.errors:
            out += "\nErrors:\n"
            for error in self.errors:
                if isinstance(error, FailedDownload):
                    resp = self._get_nice_resp_repr(error.exception)
                    out += f"(url={error.url}, response={resp})\n"
                else:
                    out += f"({error!r})"
        return out

    def __repr__(self):
        out = object.__repr__(self)
        out += "\n"
        out += str(self)
        return out

    def append(self, *, path, url):
        super().append(path)
        self._urls.append(url)

    def add_error(self, filename, url, exception):
        """
        Add an error to the results.
        """
        if isinstance(exception, aiohttp.ClientResponse):
            exception._headers = None
        self._errors.append(Error(filename, url, exception))

    @property
    def errors(self):
        """
        A list of errors encountered during the download.

        The errors are represented as a tuple containing
        ``(filepath, url, exception)`` where ``filepath`` is a function for
        generating a filepath, ``url`` is the url to be downloaded and
        ``exception`` is the error raised during download.
        """
        return self._errors

    @property
    def urls(self):
        """
        A list of requested urls.

        """
        return self._urls
