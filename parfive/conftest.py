from functools import partial

import pytest

from parfive.tests.localserver import MultiPartTestServer, SimpleTestServer, error_on_paths


@pytest.fixture
def namedserver():
    server = SimpleTestServer()
    server.start_server()
    yield server
    server.stop_server()


@pytest.fixture
def testserver():
    server = SimpleTestServer(callback=partial(error_on_paths, ["testfile_2.txt"]))
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
