#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build the enwik9-only cmix-neif + DWX4 PPMd compressor from bundled sources."""
import argparse
import os
import shutil
from pathlib import Path
import subprocess
import tarfile
import tempfile

from launcher import write_bundle

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def build(work, destination):
    with tarfile.open(ROOT / "upstream" / "sources.tar.xz", "r:xz") as combined:
        with combined.extractfile("cmix-neif-2.0.tar") as inner, tarfile.open(fileobj=inner, mode="r|") as source:
            for entry in source:
                if entry.isfile() and entry.name.startswith(("cmix-neif-2.0/src/", "cmix-neif-2.0/dictionary/")):
                    source.extract(entry, work, filter="data")
    upstream = work / "cmix-neif-2.0"
    src = upstream / "src"
    transform, ppmd = work / "transform", work / "ppmd"
    cxx = os.environ.get("CXX", "g++")
    subprocess.run([
        cxx, "-include", HERE / "sections.hpp", "-march=x86-64-v3", "-ffp-contract=off",
        "-fno-math-errno", "-fno-builtin", "-std=c++17", "-O2", "-Wno-attributes",
        "-fno-strict-aliasing", "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
        "-Wl,--build-id=none", "-s", "-I", src, HERE / "transform.cpp",
        src / "preprocess/dict_derive.cpp", src / "preprocess/dictionary.cpp",
        src / "preprocess/preprocessor.cpp", src / "detmath.cpp", "-o", transform,
    ], check=True)
    subprocess.run([
        cxx, "-O2", "-std=c++20", "-fno-ident", "-Wl,--build-id=none", "-s",
        "-I", ROOT / "dwx4", HERE / "ppmd.cpp", "-l:libarchive.so.13", "-o", ppmd,
    ], check=True)
    files = [
        ("__main__.py", HERE / "launcher.py"), ("transform", transform), ("ppmd", ppmd),
        (".hints", upstream / "dictionary/english.hints"),
        (".new_article_order", src / "readalike_prepr/data/new_article_order"),
    ]
    output = work / "compressor.pyz"
    write_bundle(output, ((name, path.read_bytes()) for name, path in files))
    # Publish a complete compressor even if TMPDIR and the destination differ.
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as file:
        staged = Path(file.name)
    try:
        shutil.copyfile(output, staged)
        staged.chmod(0o755)
        os.link(staged, destination)
    finally:
        staged.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("new_compressor", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        build(Path(tmp), args.new_compressor.absolute())
