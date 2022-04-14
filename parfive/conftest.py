import platform
from importlib import reload

import pytest
from pytest_localserver.http import WSGIServer

import parfive

skip_windows = pytest.mark.skipif(platform.system() == 'Windows', reason="Windows.")


@pytest.fixture
def testserver(request):
    """
    A server that throws a 404 for the second request.
    """
    counter = 0

    def simple_app(environ, start_response):
        """
        Simplest possible WSGI application.
        """
        nonlocal counter

        counter += 1
        if counter != 2:
            status = '200 OK'
            response_headers = [('Content-type', 'text/plain'),
                                ('Content-Disposition', (f'testfile_{counter}'))]
            start_response(status, response_headers)
            return [b'Hello world!\n']
        else:
            status = '404'
            response_headers = [('Content-type', 'text/plain')]
            start_response(status, response_headers)
            return ""

    server = WSGIServer(application=simple_app)
    server.start()
    request.addfinalizer(server.stop)
    return server


@pytest.fixture
def remove_aiofiles():
    parfive.downloader.aiofiles = None
    yield
    reload(parfive.downloader)
