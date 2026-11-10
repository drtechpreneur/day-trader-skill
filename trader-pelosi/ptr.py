#!/usr/bin/env python3
"""Unsupported US Congress-trade tracker in the NSE-only configuration.

Congressional STOCK Act PTRs are US disclosures and are not Indian insider or
promoter filings. No verified Indian replacement is implemented here.
"""

import argparse
import sys


MESSAGE = (
    "ptr: unsupported for NSE-only research. US Congress PTRs are not Indian "
    "insider/promoter disclosures, and no verified Indian replacement source "
    "is configured. No US disclosure data was fetched or returned."
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    argv = sys.argv[1:] if argv is None else argv
    if "-h" in argv or "--help" in argv:
        parser.print_help()
        return 0
    print(MESSAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
