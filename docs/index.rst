.. currentmodule:: parfive

.. _parfive:

=======
Parfive
=======

Parfive is a small library for downloading files, its objective is to provide a simple API for queuing files for download and then providing excellent feedback to the user about the in progress downloads.
It also aims to provide a clear interface for inspecting any failed downloads.

The parfive package was motivated by the needs of `SunPy's <https://sunpy.org>`__ ``net`` submodule, but should be generally applicable to anyone who wants a user friendly way of downloading multiple files in parallel.
Parfive uses asyncio to support downloading multiple files in parallel, and to support downloading a single file in multiple parallel chunks.
Parfive supports downloading files over either HTTP or FTP using `aiohttp <http://aiohttp.readthedocs.io/>`__ and `aioftp <https://aioftp.readthedocs.io/>`__ (``aioftp`` is an optional dependency, which does not need to be installed to download files over HTTP).

Parfive provides both a function and coroutine interface, so that it can be used from both synchronous and asynchronous code.
It also has opt-in support for using `aiofiles <https://github.com/Tinche/aiofiles>`__ to write downloaded data to disk using a separate thread pool, which may be useful if you are using parfive from within an asyncio application.


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

Parfive works by creating a downloader object, queuing downloads with it and then running the download.

A simple example is::

  from parfive import Downloader
  dl = Downloader()
  dl.enqueue_file("http://data.sunpy.org/sample-data/predicted-sunspot-radio-flux.txt", path="./")
  files = dl.download()

It's also possible to download a list of URLs to a single destination using the `Downloader.simple_download <parfive.Downloader.simple_download>` method::

  from parfive import Downloader
  files = Downloader.simple_download(['http://212.183.159.230/5MB.zip' 'http://212.183.159.230/10MB.zip'], path="./")

Parfive also bundles a CLI. The following example will download the two files concurrently::

  $ parfive 'http://212.183.159.230/5MB.zip' 'http://212.183.159.230/10MB.zip'
  $ parfive --help
  usage: parfive [-h] [--max-conn MAX_CONN] [--overwrite] [--no-file-progress] [--directory DIRECTORY] [--print-filenames] URLS [URLS ...]

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


Options and Customisation
-------------------------

Parfive aims to support as many use cases as possible, and therefore has a number of options.

There are two main points where you can customise the behaviour of the downloads, in the initialiser to `parfive.Downloader` or when adding a URL to the download queue with `~parfive.Downloader.enqueue_file`.
The arguments to the ``Downloader()`` constructor affect all files transferred, and the arguments to ``enqueue_file()`` apply to only that file.

By default parfive will transfer 5 files in parallel and, if supported by the remote server, chunk those files and download 5 chunks simultaneously.
This behaviour is controlled by the ``max_conn=`` and ``max_splits=`` keyword arguments.

Further configuration of the ``Downloader`` instance is done by passing in a `parfive.SessionConfig` object as the ``config=`` keyword argument to ``Downloader()``.
See the documentation of that class for more details.

Keyword arguments to `~parfive.Downloader.enqueue_file` are passed through to either `aiohttp.ClientSession.get` for HTTP downloads or `aioftp.Client` for FTP downloads.
This gives you many per-file options such as headers, authentication, ssl options etc.


Parfive API
-----------

.. automodapi:: parfive
   :no-heading:
   :no-main-docstr:

Environment Variables
---------------------

Parfive reads the following environment variables, note that as of version 2.0 all environment variables are read at the point where the ``Downloader()`` class is instantiated.

* ``PARFIVE_SINGLE_DOWNLOAD`` - If set to ``"True"`` this variable sets ``max_conn`` and ``max_splits`` to one; meaning that no parallelisation of the downloads will occur.
* ``PARFIVE_DISABLE_RANGE`` - If set to ``"True"`` this variable will set ``max_splits`` to one; meaning that each file downloaded will only have one concurrent connection, although multiple files may be downloaded simultaneously.
* ``PARFIVE_OVERWRITE_ENABLE_AIOFILES`` - If set to ``"True"`` and aiofiles is installed in the system, aiofiles will be used to write files to disk.
* ``PARFIVE_DEBUG`` - If set to ``"True"`` will configure the built-in Python logger to log to stderr and set parfive, aiohttp and aioftp to debug levels.
* ``PARFIVE_HIDE_PROGESS`` - If set to ``"True"`` no progress bars will be shown.
* ``PARFIVE_TOTAL_TIMEOUT`` - Overrides the default aiohttp ``total`` timeout value (unless set in Python).
* ``PARFIVE_SOCK_READ_TIMEOUT`` - Overrides the default aiohttp ``sock_read`` timeout value (unless set in Python).

Contributors
------------

.. contributors:: Cadair/parfive
    :avatars:
    :exclude: pre-commit-ci[bot]
    :order: ASC

Changelog
---------

See `GitHub Releases <https://github.com/Cadair/parfive/releases>`__ for the release history and changelog.
