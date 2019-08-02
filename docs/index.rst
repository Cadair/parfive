Parfive
=======

.. toctree::
   :hidden:

   self
   changelog

Parfive is a small library for downloading files, its objective is to provide a
simple API for queuing files for download and then providing excellent feedback
to the user about the in progress downloads. It also aims to provide a clear
interface for inspecting any failed downloads.

The parfive package was motivated by the needs of
`SunPy's <https://sunpy.org>`__ ``net`` submodule, but should be generally applicable to anyone who wants a user friendly way of downloading multiple files in parallel. Parfive supports downloading files over either HTTP or FTP using `aiohttp <http://aiohttp.readthedocs.io/>`__ and `aioftp <https://aioftp.readthedocs.io/>`__
``aioftp`` is an optional dependency, which does not need to be installed to
download files over HTTP.


Installation
------------

parfive can be installed via pip::

  pip install parfive


or with FTP support::

  pip install parfive[ftp]


or with conda from conda-forge::

  conda install -c conda-forge parfive


or from `GitHub <https://github.com/Cadair/parfive>`__.


Usage
-----

parfive works by creating a downloader object, queuing downloads with it and
then running the download. parfive has a synchronous API, but uses `asyncio` to
parallelise downloading the files.

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



.. automodapi:: parfive
   :no-heading:
   :no-main-docstr:
