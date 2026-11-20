#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare whole-file XZ, blocked XZ and DWX2. Read every recovered byte against the source."""
import argparse
import hashlib
import json
import lzma
from pathlib import Path
import shutil
import sys
import time

from codec import encode
from decoder import decode

ENWIK9 = "159b85351e5f76e60cbe32e04c677847a9ecba3adc79addab6f4c6c7aa3744bc"


def fingerprint(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


class CompareOutput:
    def __init__(self, source):
        self.source = source
        self.total = 0
        self.hash = hashlib.sha256()

    def write(self, buf):
        if self.source.read(len(buf)) != buf:
            raise ValueError(f"decoded bytes differ in the block starting at {self.total}")
        self.hash.update(buf)
        self.total += len(buf)
        return len(buf)


def compare(source, dest):
    info = {"bytes": source.stat().st_size, "sha256": fingerprint(source)}
    dest.mkdir(parents=True, exist_ok=False)
    report = {"corpus": "enwik9" if info["sha256"] == ENWIK9 else source.name, "input": info,
              "python": sys.version.split()[0], "profiles": {}}
    for mode, filename in (("xz", "continuous.xz"), ("raw", "blocked.dwx"), ("auto", "words.dwx")):
        packed = dest / filename
        stats = {}
        start = time.monotonic()
        with source.open("rb") as src:
            if mode == "xz":
                with lzma.open(packed, "wb", preset=6) as out:
                    shutil.copyfileobj(src, out, 1 << 20)
            else:
                with packed.open("xb") as out:
                    stats = encode(src, out, mode)
        encoded = time.monotonic()
        with source.open("rb") as expected:
            output = CompareOutput(expected)
            if mode == "xz":
                with lzma.open(packed, "rb") as data:
                    shutil.copyfileobj(data, output, 1 << 20)
            else:
                with packed.open("rb") as data:
                    decode(data, output)
            if expected.read(1) or output.hash.hexdigest() != info["sha256"] or output.total != info["bytes"]:
                raise ValueError(f"{mode} failed whole-file verification")
        finished = time.monotonic()
        report["profiles"][mode] = dict(archive_bytes=packed.stat().st_size, archive_sha256=fingerprint(packed),
            restored_sha256=output.hash.hexdigest(), byte_comparison="equal", encode_seconds=round(encoded-start,3),
            decode_compare_seconds=round(finished-encoded,3), **stats)
        print(f"{mode} restored {output.total} bytes from {packed.stat().st_size} archived bytes", flush=True)
    (dest / "verified.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path)
    p.add_argument("output", type=Path, help="new output directory for all three archives")
    a = p.parse_args()
    compare(a.input, a.output)
