ParFive
=======

.. image:: https://img.shields.io/pypi/v/parfive.svg
    :target: https://pypi.python.org/pypi/parfive
    :alt: Latest PyPI version

A parallel file downloader using asyncio. parfive can handle downloading
multiple files in parallel as well as downloading each file in a number of
chunks.

Usage
-----

parfive works by creating a downloader object, appending files to it and then
running the download. parfive has a synchronous API, but uses asyncio to
paralellise downloading the files.

A simple example is::

  from parfive import Downloader

  dl = Downloader()

  dl.enqueue_file("http://data.sunpy.org/sample-data/predicted-sunspot-radio-flux.txt", path="./")

  files = dl.download()

Parfive also bundles a CLI. The following example will download the two files concurrently.::

  $ parfive 'http://212.183.159.230/5MB.zip' 'http://212.183.159.230/10MB.zip'
  $ parfive --help                                                                           
  usage: parfive [-h] [--max-conn MAX_CONN] [--overwrite] [--no-file-progress]
                [--directory DIRECTORY] [--print-filenames]
                URLS [URLS ...]

  Parfive, the python asyncio based downloader

  positional arguments:
    URLS                  URLs of files to be downloaded.

  optional arguments:
    -h, --help            show this help message and exit
    --max-conn MAX_CONN   Number of maximum connections.
    --overwrite           Overwrite if the file exists.
    --no-file-progress    Show progress bar for each file.
    --directory DIRECTORY
                          Directory to which downloaded files are saved.
    --print-filenames     Print successfully downloaded files's names to stdout.


Results
^^^^^^^

``parfive.Downloader.download`` returns a ``parfive.Results`` object, which is a
list of the filenames that have been downloaded. It also tracks any files which
failed to download.


Handling Errors
^^^^^^^^^^^^^^^

If files fail to download, the urls and the response from the server are stored
in the ``Results`` object returned by ``parfive.Downloader``. These can be used to
inform users about the errors. (Note, the progress bar will finish in an
incomplete state if a download fails, i.e. it will show ``4/5 Files Downloaded``).

The ``Results`` object is a list with an extra attribute ``errors``, this property
returns a list of named tuples, where these named tuples contains the ``.url``
and the ``.response``, which is a ``aiohttp.ClientResponse`` or a
``aiohttp.ClientError`` object.

Installation
------------

parfive is available on PyPI, you can install it with pip::

  pip install parfive

or if you want to use FTP downloads::

  pip install parfive[ftp]

Requirements
^^^^^^^^^^^^

- Python 3.7 or above
- aiohttp
- tqdm
- aioftp (for downloads over FTP)

Licence
-------

MIT Licensed

Authors
-------

`parfive` was written by `Stuart Mumford <http://stuartmumford.uk>`_.
