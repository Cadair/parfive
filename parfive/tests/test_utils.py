import tempfile
from collections import namedtuple
from pathlib import Path

import pytest

from parfive.utils import sha256sum, default_name


def test_sha256sum():
    tempfilename = tempfile.mktemp()
    filehash = "559aead08264d5795d3909718cdd05abd49572e84fe55590eef31a88a08fdffd"
    with open(tempfilename, 'w') as f:
        f.write('A')
    assert sha256sum(tempfilename) == filehash



@pytest.fixture
def resp(header):
    resp = namedtuple("resp", ("headers",))
    headers = {'Content-Disposition': header}
    return resp(headers)


@pytest.mark.parametrize("header", (
    'attachment; filename="mdi_fd_M_96m_lev182_98611_98611.tar"\nContent-transfer-encoding: binary',
    'attachment; filename="mdi_fd_M_96m_lev182_98611_98611.tar"',
    'attachment; filename="mdi_fd_M_96m_lev182_98611_98611.tar"\n\nContent-transfer-encoding: binary',
    'ajslkdj;skjdkj',
    'attachment; wibble="hello"; filename="mdi_fd_M_96m_lev182_98611_98611.tar"',
    'attachment; filename="mdi_fd_M_96m_lev182_98611_98611.tar"filename="kjdkfjds"kajskldj',
    ''
))
def test_parse_content_disposition_header(resp, header):
    url = "http://domain.ext/mdi_fd_M_96m_lev182_98611_98611.tar"
    assert Path("./mdi_fd_M_96m_lev182_98611_98611.tar") == default_name(".", resp, url)


