#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare complete archives, restored XML and Linux process RSS for DWX2 and DWX3."""
import argparse
import hashlib
import json
import io
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time

from benchmark import DECODER, runnable
from wiki3 import encode_v3
from standalone import write_archive

HERE = Path(__file__).resolve().parent


def hash_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


# A fresh small launcher keeps the benchmark orchestrator's earlier allocations
# out of the child's inherited high water mark on Linux.
RSS_LAUNCHER = """
import os, sys
actions = [(os.POSIX_SPAWN_OPEN, fd, os.devnull, os.O_WRONLY, 0) for fd in (1, 2)]
pid = os.posix_spawn(sys.argv[1], sys.argv[1:], os.environ, file_actions=actions)
_, status, usage = os.wait4(pid, 0)
print(f"{usage.ru_maxrss}")
sys.exit(os.waitstatus_to_exitcode(status))
"""


def measure(command):
    start = time.monotonic()
    result = subprocess.run([sys.executable, "-I", "-S", "-c", RSS_LAUNCHER, *command],
                            check=True, stdout=subprocess.PIPE, text=True)
    return dict(peak_rss_kib=int(result.stdout), wall_seconds=round(time.monotonic()-start, 3))


def bench(source, output, example):
    prefix = (source / "prof_input/input2").read_bytes()
    tail = (source / "prof_input/input").read_bytes()
    if (not prefix.endswith(tail) or hashlib.sha256(prefix).hexdigest() !=
            "7dc711344aaa6e9b8fab85cd4b5b5e97c3be4d98c29b2c9f479ab774a3c7cbc2"):
        raise ValueError("unknown input fixture")
    report = dict(platform=platform.platform(), python=platform.python_version(), samples={})
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        for label, raw in (("wiki-prefix", prefix[:-len(tail)]), ("profiling-tail", tail)):
            src = folder / label
            src.write_bytes(raw)
            sample = dict(input_bytes=len(raw), input_sha256=hash_file(src), variants={})
            for mode in ("DWX2", "DWX3"):
                stem = label + "-" + mode
                packed, app, decoded = (folder / (stem + ext) for ext in (".dwx", ".pyz", ".xml"))
                enc = measure([sys.executable, HERE / "codec.py", "encode", src, packed, "--format", mode])
                payload = packed.read_bytes()
                if mode == "DWX3":
                    write_archive(io.BytesIO(payload), app)
                else:
                    runnable(app, DECODER, payload)
                dec = measure([sys.executable, "-I", app, decoded])
                if decoded.read_bytes() != raw:
                    raise ValueError(f"{stem} round trip differs")
                sample["variants"][mode] = dict(stream_bytes=len(payload), stream_sha256=hash_file(packed),
                    runnable_bytes=app.stat().st_size, runnable_sha256=hash_file(app),
                    restored_sha256=hash_file(decoded), encode=enc, standalone_decode=dec)
                if label == "wiki-prefix" and mode == "DWX3" and example:
                    with example.open("xb") as dest:
                        dest.write(app.read_bytes())
            sample["ablation_stream_bytes"] = {}
            for mode, name in enumerate(("raw", "words", "words_case", "words_case_fields", "words_fields")):
                with src.open("rb") as source_file, (folder / "ablation").open("wb") as dest:
                    encode_v3(source_file, dest, (mode,))
                # Verify every experimental packet, including modes auto did not choose.
                check = folder / f"{label}-{mode}.check"
                measure([sys.executable, HERE / "codec.py", "decode", folder / "ablation", check])
                if check.read_bytes() != raw:
                    raise ValueError(f"failed ablation {name}")
                sample["ablation_stream_bytes"][name] = (folder / "ablation").stat().st_size
            report["samples"][label] = sample
    with output.open("x") as dest:
        dest.write(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--example", type=Path)
    args = parser.parse_args()
    bench(args.source.resolve(), args.output, args.example)
