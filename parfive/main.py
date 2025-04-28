import argparse
import sys

from parfive import Downloader, SessionConfig, __version__


def main():
    args = parse_args(sys.argv[1:])
    run_parfive(args)


def run_parfive(args):
    log_level = "DEBUG" if args.verbose else None
    config = SessionConfig(file_progress=not args.no_file_progress, log_level=log_level)

    downloader = Downloader(
        max_conn=args.max_conn,
        max_splits=args.max_splits,
        progress=not args.no_progress,
        overwrite=args.overwrite,
        config=config,
    )
    for url in args.urls:
        downloader.enqueue_file(url, path=args.directory)
    results = downloader.download()

    if args.print_filenames:
        for i in results:
            print(i)

    err_str = ""
    for err in results.errors:
        err_str += f"{err.url} \t {err.exception}\n"
    if err_str:
        print(err_str, file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


def parse_args(args):
    parser = argparse.ArgumentParser(description="Parfive: A parallel file downloader written in Python.")
    parser.add_argument("urls", metavar="URLS", type=str, nargs="+", help="URLs of files to be downloaded.")
    parser.add_argument("--max-conn", type=int, default=5, help="Maximum number of parallel file downloads.")
    parser.add_argument(
        "--max-splits",
        type=int,
        default=5,
        help="Maximum number of parallel connections per file (only used if supported by the server).",
    )
    parser.add_argument(
        "--directory", type=str, default="./", help="Directory to which downloaded files are saved."
    )
    parser.add_argument(
        "--overwrite",
        action="store_const",
        const=True,
        default=False,
        help="Overwrite if the file exists.",
    )
    parser.add_argument(
        "--no-progress",
        action="store_const",
        const=True,
        default=False,
        dest="no_progress",
        help="Show progress indicators during download.",
    )
    parser.add_argument(
        "--no-file-progress",
        action="store_const",
        const=True,
        default=False,
        dest="no_file_progress",
        help="Show progress bar for each file.",
    )
    parser.add_argument(
        "--print-filenames",
        action="store_const",
        const=True,
        default=False,
        dest="print_filenames",
        help="Print successfully downloaded files's names to stdout.",
    )
    parser.add_argument(
        "--verbose",
        action="store_const",
        const=True,
        default=False,
        help="Log debugging output while transferring the files.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    return parser.parse_args(args)
