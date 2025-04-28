from pathlib import Path

import pytest

from parfive.main import parse_args, run_parfive

REQUIRED_ARGUMENTS = ["test_url"]


def test_no_url():
    with pytest.raises(SystemExit):
        parse_args(["--overwrite"])


def helper(args, name, expected):
    args = parse_args(REQUIRED_ARGUMENTS + args)
    assert getattr(args, name) == expected


def test_overwrite():
    helper(["--overwrite"], "overwrite", True)
    helper([], "overwrite", False)


def test_max_conn():
    helper(["--max-conn", "10"], "max_conn", 10)
    helper([], "max_conn", 5)


def test_max_splits():
    helper(["--max-splits", "10"], "max_splits", 10)
    helper([], "max_splits", 5)


def test_no_file_progress():
    helper(["--no-file-progress"], "no_file_progress", True)
    helper([], "no_file_progress", False)


def test_no_progress():
    helper(["--no-progress"], "no_progress", True)
    helper([], "no_progress", False)


def test_print_filenames():
    helper(["--print-filenames"], "print_filenames", True)
    helper([], "print_filenames", False)


def test_directory():
    helper(["--directory", "/tmp"], "directory", "/tmp")
    helper([], "directory", "./")


def test_verbose():
    helper(["--verbose"], "verbose", True)
    helper([], "verbose", False)


@pytest.fixture
def test_url(multipartserver):
    return multipartserver.url


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--no-progress"],
        ["--print-filenames"],
        ["--verbose"],
    ],
)
def test_run_cli_success(args, test_url, capsys):
    cliargs = parse_args([*args, test_url])
    with pytest.raises(SystemExit) as exit_exc:
        run_parfive(cliargs)

    assert exit_exc.value.code == 0

    cap_out = capsys.readouterr()

    if "--print-filenames" in args:
        assert "testfile.txt" in cap_out.out
    else:
        assert "testfile.txt" not in cap_out.out

    if "--no-progress" in args:
        assert "Files Downloaded:" not in cap_out.err
    else:
        assert "Files Downloaded:" in cap_out.err

    if "--verbose" in args:
        assert "DEBUG" in cap_out.err

    Path("testfile.txt").unlink()
