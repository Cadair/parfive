import tempfile

from parfive.utils import sha256sum


def test_sha256sum():
    tempfilename = tempfile.mktemp()
    filehash = "559aead08264d5795d3909718cdd05abd49572e84fe55590eef31a88a08fdffd"
    with open(tempfilename, 'w') as f:
        f.write('A')
    assert sha256sum(tempfilename) == filehash
