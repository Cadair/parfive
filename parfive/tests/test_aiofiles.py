import os
from importlib import reload
from unittest.mock import patch

import pytest

import parfive
from parfive import Downloader


@pytest.fixture
def remove_aiofiles():
    parfive.downloader.aiofiles = None
    yield
    reload(parfive.downloader)


@pytest.mark.parametrize("use_aiofiles", [True, False])
def test_enable_aiofiles_constructor(use_aiofiles):
    dl = Downloader(use_aiofiles=use_aiofiles)
    assert dl.use_aiofiles == use_aiofiles, f"expected={dl.use_aiofiles}, got={use_aiofiles}"


@patch.dict(os.environ, {'PARFIVE_OVERWRITE_ENABLE_AIOFILES': "some_value_to_enable_it"})
@pytest.mark.parametrize("use_aiofiles", [True, False])
def test_enable_aiofiles_env_overwrite_always_enabled(use_aiofiles):
    dl = Downloader(use_aiofiles=use_aiofiles)
    assert dl.use_aiofiles is True


@pytest.mark.parametrize("use_aiofiles", [True, False])
def test_enable_no_aiofiles(remove_aiofiles, use_aiofiles):
    Downloader.use_aiofiles.fget.cache_clear()

    dl = Downloader(use_aiofiles=use_aiofiles)
    assert dl.use_aiofiles is False
