#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Time, package, and byte-compare a DWX4 profile on Linux."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import stat
import sys
import tempfile
import time

CANONICAL = "159b85351e5f76e60cbe32e04c677847a9ecba3adc79addab6f4c6c7aa3744bc"


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def byte_equal(a, b):
    with a.open("rb") as x, b.open("rb") as y:
        while True:
            chunk = x.read(1 << 20)
            if chunk != y.read(1 << 20):
                return False
            if not chunk:
                return True


def temporary_bytes(pid):
    files = {}
    try:
        for fd in Path(f"/proc/{pid}/fd").iterdir():
            try:
                if not os.readlink(fd).endswith(" (deleted)"):
                    continue
                info = fd.stat()
                if stat.S_ISREG(info.st_mode):
                    files[info.st_dev, info.st_ino] = info.st_size
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                continue
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        pass
    return sum(files.values())


def run(args, cpu, scratch, log):
    start = time.monotonic()
    pid = os.fork()
    if pid == 0:
        try:
            os.sched_setaffinity(0, {cpu})
            with log.open("wb") as f:
                os.dup2(f.fileno(), 1)
                os.dup2(f.fileno(), 2)
            os.execve(args[0], args, dict(os.environ, TMPDIR=str(scratch), LC_ALL="C"))
        except BaseException:
            os._exit(127)
    peak_temp = 0
    while True:
        done, status, usage = os.wait4(pid, os.WNOHANG)
        if done:
            break
        peak_temp = max(peak_temp, temporary_bytes(pid))
        time.sleep(0.05)
    if os.waitstatus_to_exitcode(status):
        raise RuntimeError(f"command failed: {args}, see {log}")
    return dict(wall_seconds=round(time.monotonic()-start,3), peak_rss_kib=usage.ru_maxrss,
                user_seconds=round(usage.ru_utime,3), system_seconds=round(usage.ru_stime,3),
                sampled_temporary_file_bytes=peak_temp)


def bench(binary, source, output, profile, cpu, scratch_parent):
    output.mkdir()
    with tempfile.TemporaryDirectory(dir=scratch_parent) as td:
        scratch = Path(td).resolve()
        stream = output / "enwik9.dwx"
        executable = output / "enwik9.run"
        restored = output / "restored"
        original_sha = digest(source)
        info = dict(profile=profile, cpu=cpu, machine=platform.machine(), kernel=platform.release(),
                    executable_sha256=digest(binary), input_bytes=source.stat().st_size, input_sha256=original_sha)
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                info["cpu_model"] = line.partition(":")[2].strip()
                break
        info["encode"] = run([binary,"encode",source,stream,profile],cpu,scratch,output/"encode.log")
        info["pack"] = run([binary,"pack",stream,executable],cpu,scratch,output/"pack.log")
        info["standalone_decode"] = run([executable,restored],cpu,scratch,output/"decode.log")
        info.update(stream_bytes=stream.stat().st_size, stream_sha256=digest(stream),
                    archive_bytes=executable.stat().st_size, archive_sha256=digest(executable),
                    restored_sha256=digest(restored), byte_comparison=byte_equal(source,restored))
        if not info["byte_comparison"] or info["restored_sha256"] != original_sha:
            raise ValueError("restored file differs from input")
        info["canonical_enwik9"] = info["input_bytes"] == 10**9 and original_sha == CANONICAL
        info["decoder_and_trailer_bytes"] = info["archive_bytes"]-info["stream_bytes"]
        (output/"verified.json").write_text(json.dumps(info,indent=2)+"\n")
        print(json.dumps(info,indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input",type=Path)
    p.add_argument("new_directory",type=Path)
    p.add_argument("--binary",type=Path,default=Path(__file__).with_name("dwx4"))
    p.add_argument("--profile",default="wiki")
    p.add_argument("--cpu",type=int,default=min(os.sched_getaffinity(0)))
    p.add_argument("--scratch",type=Path,help="directory on a filesystem with spare disk space")
    a=p.parse_args()
    if a.cpu not in os.sched_getaffinity(0):
        sys.exit("CPU outside process affinity")
    bench(a.binary.resolve(strict=True),a.input.resolve(strict=True),a.new_directory.resolve(),
          a.profile,a.cpu,a.scratch)
