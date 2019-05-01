from collections import UserList, namedtuple

import aiohttp

from .utils import FailedDownload

__all__ = ['Results']


class Results(UserList):
    """
    The results of a download from `parfive.Downloader.download`.

    This object contains the filenames of successful downloads as well as a
    list of any errors encountered in the `~parfive.Results.errors` property.
    """
    def __init__(self, *args, errors=None):
        super().__init__(*args)
        self._errors = errors or list()
        self._error = namedtuple("error", ("filepath_partial", "url", "exception"))

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
                if isinstance(error, FailedDownload):
                    resp = self._get_nice_resp_repr(error.exception)
                    out += "(url={}, response={})\n".format(error.url, resp)
                else:
                    out += "({})".format(repr(error))
        return out

    def __repr__(self):
        out = object.__repr__(self)
        out += '\n'
        out += str(self)
        return out

    def add_error(self, filename, url, exception):
        """
        Add an error to the results.
        """
        if isinstance(exception, aiohttp.ClientResponse):
            exception._headers = None
        self._errors.append(self._error(filename, url, exception))

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
