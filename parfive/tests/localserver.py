import abc
from collections import defaultdict

from pytest_localserver.http import WSGIServer


class BaseTestServer(abc.ABC):
    """
    A pytest-localserver server which allows you to customise it's responses.

    Parameters
    ----------
    callback
        A callable with signature ``(request_number, environ,
        start_response)``. If the callback returns anything other than `None`
        it is assumed that the callback has handled the WSGI request. If the
        callback returns `None` then `default_request_handler` is returned
        which will handle the WSGI request.
    """

    def __init__(self, callback=None):
        self.requests = []
        self.server = WSGIServer(application=self.request_handler)
        self.callback = callback
        self.requests_by_method = defaultdict(lambda: 0)

    def callback_handler(self, environ, start_response):
        if self.callback is not None:
            return self.callback(self, environ, start_response)

    def request_handler(self, environ, start_response):
        self.requests.append(environ)
        callback_return = self.callback_handler(environ, start_response)
        self.requests_by_method[environ["REQUEST_METHOD"]] += 1
        if callback_return:
            return callback_return

        return self.default_request_handler(environ, start_response)

    @abc.abstractmethod
    def default_request_handler(self, environ, start_response):
        return

    def start_server(self):
        self.server.start()

    def stop_server(self):
        self.server.stop()

    @property
    def url(self):
        return self.server.url


class SimpleTestServer(BaseTestServer):
    def default_request_handler(self, environ, start_response):
        status = "200 OK"
        response_headers = [
            ("Content-type", "text/plain"),
            ("Content-Disposition", f"attachment; filename={environ['PATH_INFO'].strip('/')}"),
        ]
        start_response(status, response_headers)
        return [b"Hello world!\n"]


class MultiPartTestServer(BaseTestServer):
    def default_request_handler(self, environ, start_response):
        content = b"a" * 100
        bytes_end = content_length = len(content)
        bytes_start = 0

        http_range = environ.get("HTTP_RANGE", None)
        if http_range:
            http_range = http_range.split("bytes=")[1]
            bytes_start = int(http_range.split("-")[0])
            bytes_end = http_range.split("-")[1]
            if not bytes_end:
                bytes_end = content_length
            bytes_end = int(bytes_end)

            content_length = bytes_end - bytes_start

        status = "200 OK"
        response_headers = [
            ("Content-type", "text/plain"),
            ("Content-Length", content_length),
            ("Accept-Ranges", "bytes"),
            ("Content-Disposition", "attachment; filename=testfile.txt"),
        ]
        start_response(status, response_headers)
        part = content[bytes_start:bytes_end]
        return [part]


def error_on_paths(paths, server, environ, start_response):
    if (path := environ["PATH_INFO"].strip("/")) in paths:
        # Once we error on a GET request serve it next time
        if environ["REQUEST_METHOD"] == "GET":
            paths.remove(path)
        status = "404"
        response_headers = [("Content-type", "text/plain")]
        start_response(status, response_headers)
        return [b""]


def error_on_nth_get_request(n, server, environ, start_response):
    if server.requests_by_method["GET"] == n:
        status = "404"
        response_headers = [("Content-type", "text/plain")]
        start_response(status, response_headers)
        return [b""]
