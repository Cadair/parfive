from collections import UserList, namedtuple

import aiohttp

__all__ = ['Results']


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
