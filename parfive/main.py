import argparse
import sys

from parfive import Downloader


def main():
    parser = argparse.ArgumentParser(description='Parfive, the python asyncio based downloader')
    parser.add_argument('urls', metavar='URLS', type=str, nargs='+',
                        help='URLs of files to be downloaded.')
    parser.add_argument('--max-conn', type=int, default=5,
                        help='Number of maximum connections.')
    parser.add_argument('--overwrite', action='store_const', const=True, default=False,
                        help='Overwrite if the file exists.')
    parser.add_argument('--no-file-progress', action='store_const', const=False, default=True, dest='file_progress',
                        help='Overwrite if the file exists.')
    parser.add_argument('--directory', type=str, default='./',
                        help='Directory to which downloaded files are saved.')

    args = parser.parse_args()

    downloader = Downloader(max_conn=args.max_conn, file_progress=args.file_progress, overwrite=args.overwrite)
    for url in args.urls:
        downloader.enqueue_file(url, path=args.directory)
    results = downloader.download()
    for err in results.errors:
        print(f'{err.url} \t {err.exception}')
    if results.errors:
        sys.exit(1)
