#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Package an existing DWX3 stream and its decoder as a standalone Python ZIP application."""
import argparse
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

from wiki3_decoder import MAGIC3

HERE = Path(__file__).resolve().parent
MAIN = b"""
import sys
import zipfile
with zipfile.ZipFile(sys.argv[0]) as package, package.open("payload") as data:
    with open(sys.argv[1], "xb") as dest:
        decode(data, dest)
"""


def decoder_source():
    common = (HERE / "decoder.py").read_bytes().split(b"def decode(source, dest):", 1)[0]
    module = (HERE / "wiki3_decoder.py").read_bytes()
    dependency = b"from decoder import BLOCK, HEADER, expand, read_exact, varint"
    if module.count(dependency) != 1:
        raise ValueError("standalone decoder imports differ")
    return common + module.replace(dependency, b"") + MAIN


def write_archive(source, output):
    if source.read(4) != MAGIC3:
        raise ValueError("expected a DWX3 stream")
    source.seek(0)
    with tempfile.NamedTemporaryFile(dir=output.parent) as temp:
        with zipfile.ZipFile(temp, "w") as archive:
            main = zipfile.ZipInfo("__main__.py", (1980, 1, 1, 0, 0, 0))
            main.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(main, decoder_source())
            payload = zipfile.ZipInfo("payload", (1980, 1, 1, 0, 0, 0))
            with archive.open(payload, "w") as member:
                shutil.copyfileobj(source, member, 1 << 20)
        temp.flush()
        os.link(temp.name, output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stream", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with args.stream.open("rb") as source:
        write_archive(source, args.output)
