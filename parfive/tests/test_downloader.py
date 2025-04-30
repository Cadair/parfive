import os
import platform
import threading
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock, patch

import aiohttp
import pytest
from aiohttp import ClientConnectorError, ClientTimeout

import parfive
from parfive.config import SessionConfig
from parfive.downloader import Downloader, FailedDownload, Results, Token
from parfive.utils import ChecksumMismatch, check_file_hash

skip_windows = pytest.mark.skipif(platform.system() == "Windows", reason="Windows.")


def validate_test_file(f):
    assert len(f) == 1
    assert Path(f[0]).name == "testfile.fits"
    with Path(f[0]).open(mode="rb") as fobj:
        assert check_file_hash(
            fobj, "sha-256=a1c58cd340e3bd33f94524076f1fa5cf9a7f13c59d5272a9d4bc0b5bc436d9b3"
        )


def test_setup():
    dl = Downloader()

    assert isinstance(dl, Downloader)

    assert len(dl.http_queue) == 0
    assert len(dl.ftp_queue) == 0
    assert dl._generate_tokens().qsize() == 5


def test_download(httpserver, tmpdir):
    tmpdir = str(tmpdir)
    httpserver.serve_content(
        "SIMPLE  = T", headers={"Content-Disposition": "attachment; filename=testfile.fits"}
    )
    dl = Downloader()

    dl.enqueue_file(httpserver.url, path=Path(tmpdir), max_splits=None)

    assert dl.queued_downloads == 1

    f = dl.download()
    assert len(f.urls) == 1
    assert f.urls[0] == httpserver.url
    validate_test_file(f)


def test_simple_download(httpserver, tmpdir):
    tmpdir = str(tmpdir)
    httpserver.serve_content(
        "SIMPLE  = T", headers={"Content-Disposition": "attachment; filename=testfile.fits"}
    )

    f = Downloader.simple_download([httpserver.url], path=Path(tmpdir))
    validate_test_file(f)


def test_changed_max_conn(httpserver, tmpdir):
    # Check that changing max_conn works after creating Downloader
    tmpdir = str(tmpdir)
    httpserver.serve_content(
        "SIMPLE  = T", headers={"Content-Disposition": "attachment; filename=testfile.fits"}
    )
    dl = Downloader(max_conn=4)
    dl.enqueue_file(httpserver.url, path=Path(tmpdir), max_splits=None)
    dl.max_conn = 3

    f = dl.download()
    validate_test_file(f)


@pytest.mark.asyncio
@pytest.mark.parametrize("use_aiofiles", [True, False])
async def test_async_download(httpserver, tmpdir, use_aiofiles):
    httpserver.serve_content(
        "SIMPLE  = T", headers={"Content-Disposition": "attachment; filename=testfile.fits"}
    )
    dl = Downloader(config=SessionConfig(use_aiofiles=use_aiofiles))

    dl.enqueue_file(httpserver.url, path=Path(tmpdir), max_splits=None)

    assert dl.queued_downloads == 1

    f = await dl.run_download()
    validate_test_file(f)


def test_download_ranged_http(httpserver, tmpdir):
    tmpdir = str(tmpdir)
    httpserver.serve_content(
        "SIMPLE  = T", headers={"Content-Disposition": "attachment; filename=testfile.fits"}
    )
    dl = Downloader()

    dl.enqueue_file(httpserver.url, path=Path(tmpdir))

    assert dl.queued_downloads == 1

    f = dl.download()
    validate_test_file(f)


def test_regression_download_ranged_http(httpserver, tmpdir):
    tmpdir = str(tmpdir)
    httpserver.serve_content(
        "S",
        headers={
            "Content-Disposition": "attachment; filename=testfile.fits",
            "Accept-Ranges": "bytes",
        },
    )
    dl = Downloader()

    dl.enqueue_file(httpserver.url, path=Path(tmpdir))

    assert dl.queued_downloads == 1

    f = dl.download()
    assert len(f.errors) == 0, f.errors


def test_download_partial(httpserver, tmpdir):
    tmpdir = str(tmpdir)
    httpserver.serve_content("SIMPLE  = T")
    dl = Downloader()

    dl.enqueue_file(httpserver.url, filename=lambda resp, url: Path(tmpdir) / "filename")
    f = dl.download()
    assert len(f) == 1

    # strip the http://
    assert "filename" in f[0]


def test_empty_download(tmpdir):
    dl = Downloader()

    f = dl.download()
    assert len(f) == 0


def test_download_filename(httpserver, tmpdir):
    httpserver.serve_content("SIMPLE  = T")

    fname = "testing123"
    filename = str(tmpdir.join(fname))
    with open(filename, "w") as fh:
        fh.write("SIMPLE = T")

    dl = Downloader()

    dl.enqueue_file(httpserver.url, filename=filename, chunksize=200)
    f = dl.download()

    assert isinstance(f, Results)
    assert len(f) == 1

    assert f[0] == filename


def test_download_no_overwrite(httpserver, tmpdir):
    httpserver.serve_content("SIMPLE  = T")

    fname = "testing123"
    filename = str(tmpdir.join(fname))
    with open(filename, "w") as fh:
        fh.write("Hello world")

    dl = Downloader()

    dl.enqueue_file(httpserver.url, filename=filename, chunksize=200)
    f = dl.download()

    assert isinstance(f, Results)
    assert len(f) == 1

    assert f[0] == filename

    with open(filename) as fh:
        # If the contents is the same as when we wrote it, it hasn't been
        # overwritten
        assert fh.read() == "Hello world"


def test_download_overwrite(httpserver, tmpdir):
    httpserver.serve_content("SIMPLE  = T")

    fname = "testing123"
    filename = str(tmpdir.join(fname))
    with open(filename, "w") as fh:
        fh.write("Hello world")

    dl = Downloader(overwrite=True)

    dl.enqueue_file(httpserver.url, filename=filename, chunksize=200)
    f = dl.download()

    assert isinstance(f, Results)
    assert len(f) == 1

    assert f[0] == filename

    with open(filename) as fh:
        assert fh.read() == "SIMPLE  = T"


def test_download_unique(httpserver, tmpdir):
    httpserver.serve_content("SIMPLE  = T")

    fname = "testing123"
    filename = str(tmpdir.join(fname))

    filenames = [filename, filename + ".fits", filename + ".fits.gz"]

    dl = Downloader(overwrite="unique")

    # Write files to both the target filenames.
    for fn in filenames:
        with open(fn, "w") as fh:
            fh.write("Hello world")

            dl.enqueue_file(httpserver.url, filename=fn, chunksize=200)

    f = dl.download()

    assert isinstance(f, Results)
    assert len(f) == len(filenames)

    for fn in f:
        assert fn not in filenames
        assert f"{fname}.1" in fn


def test_retrieve_some_content(testserver, tmpdir):
    """
    Test that the downloader handles errors properly.
    """
    tmpdir = str(tmpdir)
    dl = Downloader()

    nn = 5
    for i in range(nn):
        dl.enqueue_file(testserver.url + f"/testfile_{i}.txt", path=tmpdir)

    f = dl.download()

    assert len(f) == nn - 1
    assert len(f.errors) == 1


def test_no_progress(httpserver, tmpdir, capsys):
    tmpdir = str(tmpdir)
    httpserver.serve_content("SIMPLE  = T")
    dl = Downloader(progress=False)

    dl.enqueue_file(httpserver.url, path=tmpdir)

    dl.download()

    # Check that there was not stdout
    captured = capsys.readouterr().out
    assert not captured


def throwerror(*args, **kwargs):
    raise ValueError("Out of Cheese.")


@patch("parfive.downloader.default_name", throwerror)
def test_raises_other_exception(httpserver, tmpdir):
    tmpdir = str(tmpdir)
    httpserver.serve_content("SIMPLE  = T")
    dl = Downloader()

    dl.enqueue_file(httpserver.url, path=tmpdir)
    res = dl.download()
    assert isinstance(res.errors[0].exception, ValueError)


def test_token():
    t = Token(5)

    assert "5" in repr(t)
    assert "5" in str(t)


def test_failed_download():
    err = FailedDownload("wibble", "bbc.co.uk", "running away")

    assert "bbc.co.uk" in repr(err)
    assert "bbc.co.uk" in repr(err)

    assert "running away" in str(err)
    assert "running away" in str(err)


def test_results():
    res = Results()

    res.append(path="hello", url="aurl")

    assert res[0] == "hello"
    assert res.urls[0] == "aurl"

    res.add_error("wibble", "notaurl", "out of cheese")

    assert "notaurl" in repr(res)
    assert "hello" in repr(res)
    assert "out of cheese" in repr(res)


def test_notaurl(tmpdir):
    tmpdir = str(tmpdir)

    dl = Downloader(progress=False)

    dl.enqueue_file("http://notaurl.wibble/file", path=tmpdir)

    f = dl.download()

    assert len(f.errors) == 1
    assert isinstance(f.errors[0].exception, aiohttp.ClientConnectionError)


def test_wrongscheme(tmpdir):
    tmpdir = str(tmpdir)

    dl = Downloader(progress=False)

    with pytest.raises(ValueError, match="URL must start with either"):
        dl.enqueue_file("webcal://notaurl.wibble/file", path=tmpdir)


def test_retry(tmpdir, testserver):
    tmpdir = str(tmpdir)
    dl = Downloader()

    nn = 5
    for i in range(nn):
        dl.enqueue_file(testserver.url + f"/testfile_{i}.txt", path=tmpdir)

    f = dl.download()

    assert len(f) == nn - 1
    assert len(f.errors) == 1

    f2 = dl.retry(f)

    assert len(f2) == nn
    assert len(f2.errors) == 0
    assert [f"testfile_{k}.txt" for k in ["0", "1", "3", "4", "2"]] == [f.split("/")[-1] for f in f2.urls]
    assert "testfile_0.txt" == Path(f2[0]).name
    assert "testfile_4.txt" == Path(f2[-2]).name
    assert "testfile_2.txt" == Path(f2[-1]).name


def test_empty_retry():
    f = Results()
    dl = Downloader()

    dl.retry(f)


def test_done_callback_error(tmp_path, testserver):
    def done_callback(filepath, url, error):
        if error is not None:
            (tmp_path / "callback.error").touch()

    dl = Downloader(config=SessionConfig(done_callbacks=[done_callback]))

    dl.enqueue_file(testserver.url + "/testfile_2.txt", path=tmp_path)

    f = dl.download()

    assert len(f.errors) == 1

    assert (tmp_path / "callback.error").exists()


@skip_windows
@pytest.mark.allow_hosts(True)
def test_ftp(tmpdir):
    tmpdir = str(tmpdir)
    dl = Downloader()

    dl.enqueue_file("ftp://ftp.swpc.noaa.gov/pub/warehouse/2011/2011_SRS.tar.gz", path=tmpdir)
    dl.enqueue_file("ftp://ftp.swpc.noaa.gov/pub/warehouse/2011/2013_SRS.tar.gz", path=tmpdir)
    dl.enqueue_file("ftp://ftp.swpc.noaa.gov/pub/_SRS.tar.gz", path=tmpdir)
    dl.enqueue_file("ftp://notaserver/notafile.fileL", path=tmpdir)

    f = dl.download()
    assert len(f) == 1
    assert len(f.errors) == 3


# I don't know of an alternative server which makes any sense to test this with
@pytest.mark.skip("Remote server offline")
@skip_windows
@pytest.mark.allow_hosts(True)
def test_ftp_pasv_command(tmpdir):
    tmpdir = str(tmpdir)
    dl = Downloader()
    dl.enqueue_file(
        "ftp://ftp.ngdc.noaa.gov/STP/swpc_products/daily_reports/solar_region_summaries/2002/04/20020414SRS.txt",
        path=tmpdir,
        passive_commands=["pasv"],
    )
    assert dl.queued_downloads == 1
    f = dl.download()
    assert len(f) == 1
    assert len(f.errors) == 0


@skip_windows
@pytest.mark.allow_hosts(True)
def test_ftp_http(tmpdir, httpserver):
    tmpdir = str(tmpdir)
    httpserver.serve_content("SIMPLE  = T")
    dl = Downloader()

    dl.enqueue_file("ftp://ftp.swpc.noaa.gov/pub/warehouse/2011/2011_SRS.tar.gz", path=tmpdir)
    dl.enqueue_file("ftp://ftp.swpc.noaa.gov/pub/warehouse/2011/2013_SRS.tar.gz", path=tmpdir)
    dl.enqueue_file("ftp://ftp.swpc.noaa.gov/pub/_SRS.tar.gz", path=tmpdir)
    dl.enqueue_file("ftp://notaserver/notafile.fileL", path=tmpdir)
    dl.enqueue_file(httpserver.url, path=tmpdir)
    dl.enqueue_file("http://noaurl.notadomain/noafile", path=tmpdir)

    assert dl.queued_downloads == 6

    f = dl.download()
    assert len(f) == 2
    assert len(f.errors) == 4


def test_default_user_agent(httpserver, tmpdir):
    tmpdir = str(tmpdir)
    httpserver.serve_content(
        "SIMPLE  = T", headers={"Content-Disposition": "attachment; filename=testfile.fits"}
    )

    dl = Downloader()
    dl.enqueue_file(httpserver.url, path=Path(tmpdir), max_splits=None)

    assert dl.queued_downloads == 1

    dl.download()

    assert "User-Agent" in httpserver.requests[0].headers
    assert (
        httpserver.requests[0].headers["User-Agent"]
        == f"parfive/{parfive.__version__} aiohttp/{aiohttp.__version__} python/{platform.python_version()}"
    )


def test_custom_user_agent(httpserver, tmpdir):
    tmpdir = str(tmpdir)
    httpserver.serve_content(
        "SIMPLE  = T", headers={"Content-Disposition": "attachment; filename=testfile.fits"}
    )

    dl = Downloader(config=SessionConfig(headers={"User-Agent": "test value 299792458"}))
    dl.enqueue_file(httpserver.url, path=Path(tmpdir), max_splits=None)

    assert dl.queued_downloads == 1

    dl.download()

    assert "User-Agent" in httpserver.requests[0].headers
    assert httpserver.requests[0].headers["User-Agent"] == "test value 299792458"


@patch.dict(os.environ, {"HTTP_PROXY": "http_proxy_url", "HTTPS_PROXY": "https_proxy_url"})
@pytest.mark.parametrize(
    ("url", "proxy"),
    [
        ("http://test.example.com", "http_proxy_url"),
        ("https://test.example.com", "https_proxy_url"),
    ],
)
def test_proxy_passed_as_kwargs_to_get(tmpdir, url, proxy):
    with mock.patch("aiohttp.client.ClientSession._request", new_callable=mock.MagicMock) as patched:
        dl = Downloader()
        dl.enqueue_file(url, path=Path(tmpdir), max_splits=None)

        assert dl.queued_downloads == 1

        dl.download()

    assert patched.called, "`ClientSession._request` not called"
    assert list(patched.call_args) == [
        ("HEAD", url),
        {
            "allow_redirects": False,
            "timeout": ClientTimeout(total=0, connect=None, sock_read=90, sock_connect=None),
            "proxy": proxy,
            "headers": {},
        },
    ]


def test_http_callback_success(httpserver, tmpdir):
    # Test callback on successful download
    httpserver.serve_content(
        "SIMPLE  = T", headers={"Content-Disposition": "attachment; filename=testfile.fits"}
    )

    cb = MagicMock()
    dl = Downloader(config=SessionConfig(done_callbacks=[cb]))
    dl.enqueue_file(httpserver.url, path=tmpdir, max_splits=None)

    assert dl.queued_downloads == 1

    dl.download()

    assert cb.call_count == 1
    cb_path, cb_url, cb_status = cb.call_args[0]
    assert cb_path == tmpdir / "testfile.fits"
    assert httpserver.url == cb_url
    assert cb_status is None


def test_http_callback_fail(tmpdir):
    # Test callback on failed download
    cb = MagicMock()
    dl = Downloader(config=SessionConfig(done_callbacks=[cb]))
    url = "http://127.0.0.1/myfile.txt"
    dl.enqueue_file(url, path=tmpdir, max_splits=None)

    assert dl.queued_downloads == 1

    dl.download()

    assert cb.call_count == 1
    cb_path, cb_url, cb_status = cb.call_args[0]
    assert cb_path is None
    assert url == cb_url
    # Returns 404 on windows on GHA, which triggers FailedDownload
    assert isinstance(cb_status, (ClientConnectorError, FailedDownload))


@pytest.mark.allow_hosts(True)
def test_ftp_callback_success(tmpdir):
    cb = MagicMock()
    dl = Downloader(config=SessionConfig(done_callbacks=[cb]))
    url = "ftp://ftp.swpc.noaa.gov/pub/warehouse/2011/2011_SRS.tar.gz"
    dl.enqueue_file(url, path=str(tmpdir))

    assert dl.queued_downloads == 1

    dl.download()

    assert cb.call_count == 1
    cb_path, cb_url, cb_status = cb.call_args[0]
    assert cb_path == tmpdir / "2011_SRS.tar.gz"
    assert url == cb_url
    assert cb_status is None


@mock.patch("aioftp.Client.context", side_effect=ConnectionRefusedError())
def test_ftp_callback_error(tmpdir):
    # Download should fail as not marked with allowed hosts
    cb = MagicMock()
    dl = Downloader(config=SessionConfig(done_callbacks=[cb]))
    url = "ftp://127.0.0.1/nosuchfile.txt"
    dl.enqueue_file(url, path=str(tmpdir))

    assert dl.queued_downloads == 1

    dl.download()

    assert cb.call_count == 1
    cb_path, cb_url, cb_status = cb.call_args[0]
    assert cb_path is None
    assert cb_url == url
    assert isinstance(cb_status, ConnectionRefusedError)


class CustomThread(threading.Thread):
    def __init__(self, *args, **kwargs):
        self.result = None
        super().__init__(*args, **kwargs)

    def run(self):
        try:
            self.result = self._target(*self._args, **self._kwargs)
        finally:
            del self._target, self._args, self._kwargs


@skip_windows
def test_download_out_of_main_thread(httpserver, tmpdir, recwarn):
    tmpdir = str(tmpdir)
    httpserver.serve_content(
        "SIMPLE  = T", headers={"Content-Disposition": "attachment; filename=testfile.fits"}
    )
    dl = Downloader()

    dl.enqueue_file(httpserver.url, path=Path(tmpdir), max_splits=None)

    thread = CustomThread(target=dl.download)
    thread.start()
    thread.join()

    validate_test_file(thread.result)

    # We use recwarn here as for some reason pytest.warns did not reliably pickup this warning.
    assert len(recwarn) > 0
    assert any(
        "This download has been started in a thread which is not the main thread. You will not be able to interrupt the download."
        == w.message.args[0]
        for w in recwarn
    )


def test_checksum_want_headers(httpserver, tmpdir):
    tmpdir = str(tmpdir)
    httpserver.serve_content(
        "SIMPLE  = T",
        headers={
            "Content-Disposition": "attachment; filename=testfile.fits",
            "Repr-Digest": "sha-256=a1c58cd340e3bd33f94524076f1fa5cf9a7f13c59d5272a9d4bc0b5bc436d9b3",
        },
    )
    dl = Downloader()

    dl.enqueue_file(httpserver.url, path=Path(tmpdir), max_splits=None, checksum=True)
    dl.enqueue_file(httpserver.url, path=Path(tmpdir), max_splits=None, checksum=False)

    assert dl.queued_downloads == 2

    f = dl.download()
    assert len(f.urls) == 2
    assert f.urls[0] == httpserver.url
    validate_test_file(f[0:1])

    first_headers = httpserver.requests[0].headers
    assert "Want-Repr-Digest" in first_headers
    assert "Want-Content-Digest" in first_headers

    # Two requests a file
    second_headers = httpserver.requests[2].headers
    assert "Want-Repr-Digest" not in second_headers
    assert "Want-Content-Digest" not in second_headers


def test_checksum_invalid(httpserver, tmpdir):
    tmpdir = str(tmpdir)
    httpserver.serve_content(
        "SIMPLE  = T",
        headers={
            "Content-Disposition": "attachment; filename=testfile.fits",
            "Content-Digest": "sha-256=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        },
    )
    dl = Downloader()

    dl.enqueue_file(httpserver.url, path=Path(tmpdir), max_splits=None, checksum=True)

    assert dl.queued_downloads == 1

    f = dl.download()

    assert len(f.errors) == 1
    exception = f.errors[0].exception
    assert isinstance(exception, FailedDownload)
    assert "checksum doesn't match" in str(exception)


def test_early_fail_download_checksum_mismatch(httpserver, tmpdir):
    tmpdir = str(tmpdir)
    httpserver.serve_content(
        "SIMPLE  = T",
        headers={
            "Content-Disposition": "attachment; filename=testfile.fits",
            "Repr-Digest": "sha-256=INVALID",
        },
    )
    dl = Downloader()

    dl.enqueue_file(
        httpserver.url,
        path=Path(tmpdir),
        max_splits=None,
        checksum="sha-256=a1c58cd340e3bd33f94524076f1fa5cf9a7f13c59d5272a9d4bc0b5bc436d9b3",
    )

    assert dl.queued_downloads == 1

    f = dl.download()

    assert len(f.errors) == 1
    exc = f.errors[0].exception
    assert isinstance(exc, FailedDownload)
    assert isinstance(exc.exception, ChecksumMismatch)
    assert "Server provided checksum and user provided checksum do not match, download skipped" in str(
        exc.exception
    )


def test_server_user_algorithm_mismatch(httpserver, tmp_path, caplog):
    caplog.set_level("INFO")
    httpserver.serve_content(
        "SIMPLE  = T",
        headers={
            "Content-Disposition": "attachment; filename=testfile.fits",
            "Repr-Digest": "sha-512=INVALID",
        },
    )
    dl = Downloader()

    dl.enqueue_file(
        httpserver.url,
        path=tmp_path,
        max_splits=None,
        checksum="sha-256=a1c58cd340e3bd33f94524076f1fa5cf9a7f13c59d5272a9d4bc0b5bc436d9b3",
    )

    assert dl.queued_downloads == 1

    f = dl.download()

    assert len(f.errors) == 0

    assert any(
        "Not comparing user provided checksum to server provided checksum as algorithms do not match (got sha512 from the server)."
        in m
        for m in caplog.messages
    )

    first_headers = httpserver.requests[0].headers
    assert "Want-Repr-Digest" in first_headers
    assert "Want-Content-Digest" in first_headers
    assert "sha-256=10" in first_headers["Want-Repr-Digest"]
    assert "sha-256=10" in first_headers["Want-Content-Digest"]


def test_explicit_checksum(namedserver, tmpdir):
    tmpdir = str(tmpdir)
    dl = Downloader()

    dl.enqueue_file(
        namedserver.url + "/testfile.txt",
        path=Path(tmpdir),
        max_splits=None,
        checksum="sha-256=0ba904eae8773b70c75333db4de2f3ac45a8ad4ddba1b242f0b3cfc199391dd8",
    )

    dl.enqueue_file(
        namedserver.url + "/testfile.txt",
        path=Path(tmpdir),
        max_splits=None,
        checksum="sha-256=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
    )

    assert dl.queued_downloads == 2

    f = dl.download()

    assert len(f) == 1
    assert f.urls[0] == namedserver.url + "/testfile.txt"

    assert len(f.errors) == 1
    exception = f.errors[0].exception
    assert isinstance(exception, FailedDownload)
    assert "checksum doesn't match" in str(exception)


def test_file_exists_checksum(httpserver, tmpdir, caplog):
    caplog.set_level("DEBUG")
    tmpdir = str(tmpdir)
    httpserver.serve_content(
        "SIMPLE  = T",
        headers={
            "Content-Disposition": "attachment; filename=testfile.fits",
            "Repr-Digest": "sha-256=a1c58cd340e3bd33f94524076f1fa5cf9a7f13c59d5272a9d4bc0b5bc436d9b3",
        },
    )
    dl = Downloader()

    dl.enqueue_file(httpserver.url, path=Path(tmpdir), max_splits=None, checksum=True)

    assert dl.queued_downloads == 1

    f = dl.download()

    assert len(f) == 1

    dl = Downloader()

    dl.enqueue_file(httpserver.url, path=Path(tmpdir), max_splits=None, checksum=True)

    assert dl.queued_downloads == 1

    f = dl.download()

    assert len(f) == 1

    # Assert that only three requests have been made, thereby checking
    # that the file wasn't re-downloaded the second time
    assert len(httpserver.requests) == 3

    assert (
        "testfile.fits already exists, checksum matches and overwrite is False; skipping download."
        in caplog.messages[-1]
    )


def test_no_server_checksum(httpserver, tmpdir, caplog):
    caplog.set_level("DEBUG")
    tmpdir = str(tmpdir)
    httpserver.serve_content(
        "SIMPLE  = T",
        headers={
            "Content-Disposition": "attachment; filename=testfile.fits",
        },
    )
    dl = Downloader()

    dl.enqueue_file(httpserver.url, path=Path(tmpdir), max_splits=None, checksum=True)

    assert dl.queued_downloads == 1

    f = dl.download()

    assert len(f) == 1

    assert any("Expected server to provide checksum for url" in msg for msg in caplog.messages)


def test_invalid_checksum_enqueue():
    dl = Downloader()

    with pytest.raises(ValueError, match="checksum 'wibble' should be of the format <algorithm>=<checksum>"):
        dl.enqueue_file("", checksum="wibble")

    with pytest.raises(ValueError, match="checksum type 'nope' is not supported"):
        dl.enqueue_file("", checksum="nope=wibble")

    with pytest.raises(ValueError, match="checksum type 'nope' is not supported"):
        check_file_hash("", "nope=wibble")


@pytest.mark.parametrize("checksum", ["nope=wibble", "wibble"])
def test_invalid_server_checksum(httpserver, tmpdir, caplog, checksum):
    caplog.set_level("ERROR")
    tmpdir = str(tmpdir)
    httpserver.serve_content(
        "SIMPLE  = T",
        headers={
            "Content-Disposition": "attachment; filename=testfile.fits",
            "Content-Digest": checksum,
        },
    )
    dl = Downloader()

    dl.enqueue_file(httpserver.url, path=Path(tmpdir), max_splits=None, checksum=True)

    assert dl.queued_downloads == 1

    f = dl.download()

    assert len(f.errors) == 0
    assert "Got invalid checksum:" in caplog.messages[0]
