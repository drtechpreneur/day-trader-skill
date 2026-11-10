#!/usr/bin/env python3
"""Unsupported earnings-facts tool in the NSE-only configuration.

The former implementation used SEC EDGAR / US GAAP company facts. It is
disabled rather than returning US results for Indian-listed symbols.
"""

import argparse
import sys


MESSAGE = (
    "facts: unsupported for NSE-only research. This tool has no verified "
    "Indian financial-reporting source for its quarterly metrics; it will "
    "not query SEC/EDGAR or return US company data. Review the issuer's NSE "
    "or BSE filings directly."
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("tickers", nargs="*", help="NSE symbols (currently unsupported)")
    args = parser.parse_args(argv)
    if not args.tickers:
        parser.print_help()
        return 2
    print(MESSAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
