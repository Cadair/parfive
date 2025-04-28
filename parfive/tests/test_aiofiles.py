import os
from unittest.mock import patch

import pytest

import parfive
from parfive import Downloader
from parfive.config import SessionConfig
from parfive.utils import ParfiveUserWarning


@pytest.mark.parametrize("use_aiofiles", [True, False])
def test_enable_aiofiles_constructor(use_aiofiles):
    dl = Downloader(config=parfive.SessionConfig(use_aiofiles=use_aiofiles))
    assert dl.config.use_aiofiles == use_aiofiles, f"expected={use_aiofiles}, got={dl.config.use_aiofiles}"


@patch.dict(os.environ, {"PARFIVE_OVERWRITE_ENABLE_AIOFILES": "some_value_to_enable_it"})
@pytest.mark.parametrize("use_aiofiles", [True, False])
def test_enable_aiofiles_env_overwrite_always_enabled(use_aiofiles):
    dl = Downloader(config=parfive.SessionConfig(use_aiofiles=use_aiofiles))
    assert dl.config.use_aiofiles is True


@patch("parfive.config.SessionConfig._aiofiles_importable", lambda self: False)
def test_enable_no_aiofiles():
    with pytest.warns(ParfiveUserWarning):
        dl = Downloader(config=parfive.SessionConfig(use_aiofiles=True))
    assert dl.config.use_aiofiles is False

    dl = Downloader(config=parfive.SessionConfig(use_aiofiles=False))
    assert dl.config.use_aiofiles is False


def test_aiofiles_session_config():
    c = SessionConfig(use_aiofiles=True)
    assert c.use_aiofiles is True


@patch("parfive.config.SessionConfig._aiofiles_importable", lambda self: False)
def test_aiofiles_session_config_no_aiofiles_warn():
    with pytest.warns(ParfiveUserWarning):
        c = SessionConfig(use_aiofiles=True)
        assert c.use_aiofiles is False
