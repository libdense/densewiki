#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Write the complete enwik9 pages containing a film infobox, in source order."""
import argparse
from pathlib import Path
import re

FILM = re.compile(rb"\{\{\s*infobox[ _]+film\s*(?:\||\r?\n|\})", re.I)


def select(source, output):
    count = 0
    page = None
    with source.open("rb") as src, output.open("xb") as dest:
        for line in src:
            if line == b"  <page>\n":
                page = bytearray()
            if page is not None:
                page.extend(line)
                if line == b"  </page>\n":
                    if FILM.search(page):
                        dest.write(page)
                        count += 1
                    page = None
        print(f"{count} film pages, {dest.tell()} bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("new_sample", type=Path)
    args = parser.parse_args()
    select(args.input, args.new_sample)
