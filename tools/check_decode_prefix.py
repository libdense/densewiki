#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare an initial range-decoded model stream from two unmodified, no-argument native archives."""
import argparse
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import tempfile
import time

from build import PROFILES, ROOT, digest
from payload_probe import file_hash
from roundtrip import process_rss


def observe(archive, expected_hash, count, cpu):
    if file_hash(archive) != expected_hash:
        raise ValueError("native archive SHA-256 mismatch")
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        program = folder / "archive9"
        shutil.copyfile(archive, program)
        program.chmod(0o755)
        env = dict(PATH="/usr/bin:/bin", LC_ALL="C", LANG="C", TZ="UTC")
        with (folder / "decode.log").open("wb") as log:
            start = time.monotonic()
            proc = subprocess.Popen([program], cwd=folder, env=env, stdout=log, stderr=log,
                                    start_new_session=True, preexec_fn=lambda: os.sched_setaffinity(0, {cpu}))
            peak = 0
            try:
                while proc.poll() is None and time.monotonic() - start < 420:
                    peak = max(peak, process_rss(proc.pid))
                    stream = folder / ".cmix.temp"
                    if stream.is_file() and stream.stat().st_size >= count:
                        with stream.open("rb") as inp:
                            prefix = inp.read(count)
                        if len(prefix) == count:
                            return prefix, dict(archive_sha256=expected_hash, prefix_bytes=count,
                                prefix_sha256=digest(prefix), sampled_peak_tree_rss_kib=peak,
                                wall_seconds=round(time.monotonic()-start,3))
                    time.sleep(0.1)
                raise RuntimeError(f"model stream unavailable, exit {proc.poll()}: "
                                   f"{(folder/'decode.log').read_text(errors='replace')[-500:]}")
            finally:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("profile", choices=PROFILES)
    p.add_argument("upstream", type=Path)
    p.add_argument("candidate", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--bytes", type=int, default=16384)
    args = p.parse_args()
    if args.bytes < 1:
        p.error("--bytes must be positive")
    cpu = min(os.sched_getaffinity(0))
    known = json.loads((ROOT / f"results/{args.profile}.json").read_text())
    ref, before = observe(args.upstream.resolve(), PROFILES[args.profile]["archive9"], args.bytes, cpu)
    new, after = observe(args.candidate.resolve(), known["files"]["archive9"]["sha256"], args.bytes, cpu)
    if ref != new:
        raise ValueError("initial native model outputs differ")
    result = dict(profile=args.profile, unit="first decoded model-stream bytes before inverse Wikipedia preprocessing",
                  reference=before, candidate=after, prefix_byte_comparison="equal", full_enwik9_decode=False)
    with args.output.open("x") as out:
        out.write(json.dumps(result, indent=2) + "\n")
    print(f"Compared {len(ref)} native model-stream bytes", flush=True)
