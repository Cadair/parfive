import sys
import argparse

from parfive import Downloader


def main():
    args = parse_args(sys.argv[1:])
    downloader = Downloader(max_conn=args.max_conn,
                            file_progress=not args.no_file_progress, overwrite=args.overwrite)
    for url in args.urls:
        downloader.enqueue_file(url, path=args.directory)
    results = downloader.download()
    for i in results:
        print(i)

    err_str = ''
    for err in results.errors:
        err_str += f'{err.url} \t {err.exception}\n'
    if err_str:
        sys.exit(err_str)


def parse_args(args):
    parser = argparse.ArgumentParser(description='Parfive, the python asyncio based downloader')
    parser.add_argument('urls', metavar='URLS', type=str, nargs='+',
                        help='URLs of files to be downloaded.')
    parser.add_argument('--max-conn', type=int, default=5,
                        help='Number of maximum connections.')
    parser.add_argument('--overwrite', action='store_const', const=True, default=False,
                        help='Overwrite if the file exists.')
    parser.add_argument('--no-file-progress', action='store_const', const=True, default=False, dest='no_file_progress',
                        help='Show progress bar for each file.')
    parser.add_argument('--directory', type=str, default='./',
                        help='Directory to which downloaded files are saved.')
    parser.add_argument('--print-filenames', action='store_const', const=True, default=False, dest='print_filenames',
                        help='Print successfully downloaded files\'s names to stdout.')

    args = parser.parse_args(args)
    return args
