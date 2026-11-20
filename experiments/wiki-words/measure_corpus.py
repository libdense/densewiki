#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure the normal single-process CLI on an entire corpus, in both directions."""
import argparse
import filecmp
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from full_corpus import ENWIK9, fingerprint


def run_cli(args, log, cpu):
    start = time.monotonic()
    with log.open("wb") as stream:
        proc = subprocess.Popen([sys.executable, Path(__file__).with_name("codec.py"), *args],
                                stdout=stream, stderr=subprocess.STDOUT,
                                preexec_fn=lambda: os.sched_setaffinity(0, {cpu}))
        _, status, usage = os.wait4(proc.pid, 0)
        proc.returncode = os.waitstatus_to_exitcode(status)
    if proc.returncode:
        raise RuntimeError(f"codec exited with status {proc.returncode}. See {log}")
    return dict(peak_rss_kib=usage.ru_maxrss, wall_seconds=round(time.monotonic()-start, 3))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("format", choices=("DWX2", "DWX3"))
    p.add_argument("input", type=Path)
    p.add_argument("output", type=Path, help="fresh work directory")
    p.add_argument("--cpu", type=int, default=min(os.sched_getaffinity(0)))
    p.add_argument("--mode", choices=("auto", "wiki"), default="auto")
    args = p.parse_args()
    if args.mode == "wiki" and args.format != "DWX3":
        p.error("--mode wiki requires DWX3")
    source = args.input.resolve(strict=True)
    dest = args.output
    dest.mkdir()
    identity = fingerprint(source)
    archive = dest / "stream.dwx"
    restored = dest / "restored"
    encode = run_cli(["encode", source, archive, "--format", args.format, "--mode", args.mode], dest / "encode.log", args.cpu)
    decode = run_cli(["decode", archive, restored], dest / "decode.log", args.cpu)
    if fingerprint(restored) != identity or not filecmp.cmp(source, restored, shallow=False):
        raise ValueError("restored bytes differ from the reference")
    receipt = dict(format=args.format, mode=args.mode, input_bytes=source.stat().st_size, input_sha256=identity,
                   canonical_enwik9=(identity == ENWIK9), stream_bytes=archive.stat().st_size,
                   stream_sha256=fingerprint(archive), restored_sha256=identity, byte_comparison="equal",
                   encode=encode, decode=decode)
    (dest / "verified.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Verified {args.format} on {source.stat().st_size} bytes", flush=True)


if __name__ == "__main__":
    main()
