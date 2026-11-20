#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure DWX2 and XZ with their respective runnable decoders and byte comparisons."""
import argparse
import hashlib
import io
import json
import lzma
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

from codec import encode
from decoder import decode

HERE = Path(__file__).resolve().parent
DECODER = (HERE / "decoder.py").read_bytes()
RAW_DECODER = b"""import lzma
import shutil
def decode(source, dest):
    with lzma.open(source, "rb") as raw:
        shutil.copyfileobj(raw, dest)
"""
MAIN = b"""
import sys
import zipfile
with zipfile.ZipFile(sys.argv[0]) as package, package.open("payload") as data:
    with open(sys.argv[1], "xb") as dest:
        decode(data, dest)
"""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def runnable(path, decoder, data):
    with zipfile.ZipFile(path, "w") as z:
        for name, body, method in (("__main__.py", decoder + MAIN, zipfile.ZIP_DEFLATED),
                                   ("payload", data, zipfile.ZIP_STORED)):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = method
            z.writestr(info, body)


def measure(name, raw, folder, example=None):
    results = {}
    for profile in ("xz", "raw", "frequency", "predecessor", "lexical", "auto"):
        stats = {}
        if profile == "xz":
            data = lzma.compress(raw, preset=6)
            decoder = RAW_DECODER
        else:
            buf = io.BytesIO()
            mode = profile if profile in ("raw", "auto") else "words"
            layout = profile if profile in ("frequency", "predecessor") else "lexical"
            stats = encode(io.BytesIO(raw), buf, mode, 32, layout)
            data = buf.getvalue()
            decoder = DECODER
            restored = io.BytesIO()
            decode(io.BytesIO(data), restored)
            if restored.getvalue() != raw:
                raise ValueError(f"{name}/{profile} failed its in-process round trip")
        archive = folder / f"{name}-{profile}.pyz"
        runnable(archive, decoder, data)
        restore = folder / f"{name}-{profile}.out"
        subprocess.run([sys.executable, "-I", str(archive), str(restore)], check=True, cwd=folder)
        if restore.read_bytes() != raw:
            raise ValueError(f"{name}/{profile} fresh decoder output differs")
        if example is not None and profile == "auto":
            with example.open("xb") as saved:
                saved.write(archive.read_bytes())
        results[profile] = dict(stream_bytes=len(data), runnable_bytes=archive.stat().st_size,
            sha256=digest(data), runnable_sha256=digest(archive.read_bytes()),
            restored_sha256=digest(restore.read_bytes()), byte_comparison="equal", **stats)
    return dict(input_bytes=len(raw), input_sha256=digest(raw), profiles=results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="extracted upstream size-original source tree")
    parser.add_argument("output", type=Path)
    parser.add_argument("--write-example", type=Path, help="save the verified auto archive of the larger excerpt")
    args = parser.parse_args()
    profile_dir = args.source / "prof_input"
    short = (profile_dir / "input").read_bytes()
    whole = (profile_dir / "input2").read_bytes()
    if not whole.endswith(short) or digest(whole) != "7dc711344aaa6e9b8fab85cd4b5b5e97c3be4d98c29b2c9f479ab774a3c7cbc2" or len(short) != 50051:
        raise ValueError("unexpected upstream profiling fixture")
    with tempfile.TemporaryDirectory() as d:
        work = Path(d)
        result = {name: measure(name, raw, work, args.write_example if name == "wiki-prefix" else None) for name,raw in (
            ("wiki-prefix", whole[:-len(short)]), ("profiling-tail", short))}
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
