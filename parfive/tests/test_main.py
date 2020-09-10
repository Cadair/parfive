import pytest

from parfive.main import parse_args

REQUIRED_ARGUMENTS = ['test_url']


def test_no_url():
    with pytest.raises(SystemExit):
        parse_args(['--overwrite'])


def helper(args, name, expected):
    args = parse_args(REQUIRED_ARGUMENTS + args)
    assert getattr(args, name) == expected


def test_overwrite():
    helper(['--overwrite'], 'overwrite', True)
    helper([], 'overwrite', False)


def test_max_conn():
    helper(['--max-conn', '10'], 'max_conn', 10)
    helper([], 'max_conn', 5)


def test_no_file_progress():
    helper(['--no-file-progress'], 'no_file_progress', True)
    helper([], 'no_file_progress', False)


def test_print_filenames():
    helper(['--print-filenames'], 'print_filenames', True)
    helper([], 'print_filenames', False)


def test_directory():
    helper(['--directory', '/tmp'], 'directory', '/tmp')
    helper([], 'directory', './')
