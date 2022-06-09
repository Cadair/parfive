from functools import partial

import pytest

from parfive.tests.localserver import MultiPartTestServer, SimpleTestServer, error_on_nth_request


@pytest.fixture
def testserver():
    server = SimpleTestServer(callback=partial(error_on_nth_request, 2))
    server.start_server()
    yield server
    server.stop_server()


@pytest.fixture
def multipartserver():
    """
    A server that can handle multi-part file downloads
    """
    server = MultiPartTestServer()
    server.start_server()
    yield server
    server.stop_server()
