#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure a complete hybrid encode and a restore in a fresh scratch directory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import tempfile
import time
from zipfile import ZipFile

from launcher import TAPE_BYTES, TAPE_HASH, XML_BYTES, XML_HASH, verify


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def sample_workers(parent, observations):
    # Each public command waits for its two native workers in sequence.
    try:
        children = Path(f"/proc/{parent}/task/{parent}/children").read_text().split()
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        children = []
    if not children:
        for proc in Path("/proc").iterdir():
            if not proc.name.isdecimal():
                continue
            try:
                status = (proc / "status").read_text().splitlines()
                if any(row.startswith("PPid:") and int(row.split()[1]) == parent for row in status):
                    children.append(proc.name)
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                continue
    now = time.monotonic()
    for child in children:
        proc = Path("/proc") / child
        try:
            name = (proc / "comm").read_text().strip()
            if name not in ("transform", "ppmd"):
                continue
            status = (proc / "status").read_text().splitlines()
            high = next((int(row.split()[1]) for row in status if row.startswith("VmHWM:")), 0)
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        span = observations.setdefault(name, [now, now, 0])
        span[1] = now
        span[2] = max(span[2], high)


def measure(command, cpu, output, label):
    with tempfile.TemporaryDirectory(dir=output) as directory:
        root = Path(directory)
        temporary = root / "scratch"
        temporary.mkdir()
        start = time.monotonic()
        pid = os.fork()
        if pid == 0:
            try:
                os.chdir(root)
                os.sched_setaffinity(0, {cpu})
                with (output / f"{label}.log").open("wb") as log:
                    os.dup2(log.fileno(), 1)
                    os.dup2(log.fileno(), 2)
                os.execve(command[0], command, dict(os.environ, TMPDIR=str(temporary), LC_ALL="C"))
            except BaseException:
                os._exit(127)
        largest = 0
        observed = {}
        while True:
            done, status, usage = os.wait4(pid, os.WNOHANG)
            if done:
                break
            sample_workers(pid, observed)
            named = 0
            for path in temporary.glob("**/*"):
                try:
                    if path.is_file():
                        named += path.stat().st_size
                except (FileNotFoundError, PermissionError, ProcessLookupError):
                    pass
            largest = max(largest, named)
            time.sleep(0.1)
        if os.waitstatus_to_exitcode(status):
            raise RuntimeError(f"{label} failed; see {output / (label + '.log')}")
        return {
            "wall_seconds": round(time.monotonic() - start, 3),
            "user_seconds": round(usage.ru_utime, 3),
            "system_seconds": round(usage.ru_stime, 3),
            "peak_rss_kib": usage.ru_maxrss,
            "sampled_named_scratch_bytes": largest,
            "worker_samples": {
                name: {"observed_wall_span_seconds": round(last - first, 3), "peak_observed_hwm_kib": peak}
                for name, (first, last, peak) in observed.items()
            },
        }


def benchmark(comp, src, output, cpu):
    verify(src, XML_BYTES, XML_HASH)
    output.mkdir()
    archive = output / "enwik9-hybrid.pyz"
    restored = output / "enwik9"
    encode = measure([comp, src, archive], cpu, output, "encode")
    decode = measure([archive, restored], cpu, output, "decode")
    with src.open("rb") as x, restored.open("rb") as y:
        for chunk in iter(lambda: x.read(1 << 20), b""):
            if chunk != y.read(len(chunk)):
                raise ValueError("restored file differs from canonical enwik9")
        if y.read(1):
            raise ValueError("extra bytes after canonical enwik9")
    verify(restored, XML_BYTES, XML_HASH)
    members = {}
    for filename in (comp, archive):
        with ZipFile(filename) as z:
            members[filename.name] = {
                i.filename: {"size": i.file_size, "stored_bytes": i.compress_size}
                for i in z.infolist()
            }
    payload = members[archive.name]["payload.7z"]["size"]
    result = {
        "profile": "cmix-neif 2.0 preprocessing + DWX4 Wiki PPMd",
        "input_bytes": XML_BYTES, "input_sha256": XML_HASH, "restored_sha256": digest(restored),
        "byte_comparison": True, "canonical_enwik9": True,
        "intermediate_bytes": TAPE_BYTES, "intermediate_sha256": TAPE_HASH,
        "ppmd_member_with_7z_container_bytes": payload,
        "archive_bytes": archive.stat().st_size, "archive_sha256": digest(archive),
        "decoder_and_packaging_bytes": archive.stat().st_size - payload,
        "compressor_bytes": comp.stat().st_size, "compressor_sha256": digest(comp),
        "archive_plus_compressor_bytes": comp.stat().st_size + archive.stat().st_size,
        "members": members, "cpu": cpu, "kernel": platform.release(),
        "cpu_model": next(line.partition(":")[2].strip() for line in
                          Path("/proc/cpuinfo").read_text().splitlines() if line.startswith("model name")),
        "encode": encode, "standalone_decode": decode,
        "measurement": "Wall times include validation inside the public CLI, scratch I/O and executable packaging. External comparisons are excluded. Each command and its sequential workers shared one pinned logical CPU. Linux wait4 peak RSS is the highest individual process in the waited tree, including workers. Worker spans and per-worker high-water marks were sampled about every 100 ms. Named scratch samples exclude unnamed files, output and filesystem cache.",
    }
    (output / "verified.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compressor", type=Path)
    parser.add_argument("input", type=Path)
    parser.add_argument("new_directory", type=Path)
    parser.add_argument("--cpu", type=int, default=min(os.sched_getaffinity(0)))
    args = parser.parse_args()
    benchmark(args.compressor.resolve(strict=True), args.input.resolve(strict=True),
              args.new_directory.resolve(), args.cpu)
