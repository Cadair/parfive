Parfive v1.1.0 (2020-05-01)
===========================

Features
--------

- Add concurent requests to `parfive`. This feature splits the download of
  a single file into multiple parts if the server the file is being downloaded
  from supports ranged requests. This should improve the performance of all
  downloads under these circumstances, and also make parfive useful even if
  downloading a single file. No changes are needed to use this feature, files
  will be downloaded using 12 concurrent requests by default. To change the
  number of concurrent requests you can pass ``max_splits`` to
  `parfive.Downloader.enqueue_file`. (`#15 <https://github.com/Cadair/parfive/pull/15>`__)
- Added CLI interface to Parfive. (`#16 <https://github.com/Cadair/parfive/pull/16>`__)
- Parfive now only supports Python 3.6+. (`#22 <https://github.com/Cadair/parfive/pull/22>`__)
- Support for specifying headers to be used for all requests to `parfive.Downloader` has been added. (`#32 <https://github.com/Cadair/parfive/pull/32>`__)
- Support for `HTTP_PROXY` and `HTTPS_PROXY` environment variables have been
  added. (`#32 <https://github.com/Cadair/parfive/pull/32>`__)


Bugfixes
--------

- Fix a bug where running parfive in the notebook would error if ipywidgets was
  not installed. (`#25 <https://github.com/Cadair/parfive/pull/25>`__)
- Remove use of the deprecated ``loop=`` keyword argument to `aiohttp.ClientSession`. (`#30 <https://github.com/Cadair/parfive/pull/30>`__)
- Update the notebook detection function due to changes in tqdm (`#36 <https://github.com/Cadair/parfive/pull/36>`__)
- Reduce the number of parallel connections to 25 (5 parallel files, 5 parallel
  downloads per file). (`#37 <https://github.com/Cadair/parfive/pull/37>`__)


Parfive 1.0.0 (2019-05-01)
==========================

Features
--------

- First stable release of Parfive. (`#13 <https://github.com/Cadair/parfive/pull/13>`__)
