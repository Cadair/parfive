from functools import partial

from parfive import Downloader
from parfive.tests.localserver import error_on_nth_get_request
from parfive.utils import MultiPartDownloadError


def test_multipart(multipartserver, tmp_path):
    dl = Downloader(progress=False)
    max_splits = 5
    dl.enqueue_file(multipartserver.url, path=tmp_path, max_splits=max_splits)
    files = dl.download()

    # Verify we transferred all the content
    with open(files[0], "rb") as fobj:
        assert fobj.read() == b"a" * 100

    # Assert that we made the expected number of requests
    assert len(multipartserver.requests) == max_splits + 1
    assert "HTTP_RANGE" not in multipartserver.requests[0]
    for split_req in multipartserver.requests[1:]:
        assert "HTTP_RANGE" in split_req


def test_multipart_with_error(multipartserver, tmp_path):
    multipartserver.callback = partial(error_on_nth_get_request, 3)
    dl = Downloader(progress=False)
    max_splits = 5
    dl.enqueue_file(multipartserver.url, path=tmp_path, max_splits=max_splits)
    files = dl.download()

    assert len(files) == 0
    assert len(files.errors) == 1
    assert isinstance(files.errors[0].exception, MultiPartDownloadError)

    expected_file = tmp_path / "testfile.txt"
    assert not expected_file.exists()
