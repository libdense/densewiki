#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Sample resident memory and allocated, unlinked scratch during one native file stage."""
import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import time
from zipfile import ZipFile

from launcher import ENCODER_DATA, TAPE_BYTES, TAPE_HASH, XML_BYTES, XML_HASH, verify


def sample(pid, tmp_device):
    proc = Path("/proc") / str(pid)
    status = (proc / "status").read_text().splitlines()
    rss = next((int(row.split()[1]) * 1024 for row in status if row.startswith("VmRSS:")), 0)
    files = {}
    for fd in (proc / "fd").iterdir():
        try:
            if os.readlink(fd).endswith(" (deleted)"):
                info = fd.stat()
                if stat.S_ISREG(info.st_mode):
                    files[info.st_dev, info.st_ino] = info.st_blocks * 512
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    tmp = sum(size for (device, _), size in files.items() if device == tmp_device)
    return {
        "observed_rss_bytes": rss,
        "open_unlinked_allocated_bytes": sum(files.values()),
        "open_unlinked_tmp_allocated_bytes": tmp,
        "rss_plus_tmp_allocated_bytes": rss + tmp,
    }


def audit(bundle, xml, cpu):
    tmp_device = os.stat("/tmp").st_dev
    with tempfile.TemporaryDirectory(prefix="hybrid-audit-") as td, ZipFile(bundle) as z:
        work = Path(td).resolve()
        helper, tape = work / "transform", work / "tape"
        helper.write_bytes(z.read("transform"))
        helper.chmod(0o700)
        if xml is None:
            direction = "inverse"
            ppmd, payload = work / "ppmd", work / "payload.7z"
            ppmd.write_bytes(z.read("ppmd"))
            ppmd.chmod(0o700)
            with z.open("payload.7z") as src, payload.open("wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
            subprocess.run([ppmd, "unpack", payload, tape], cwd=work, check=True)
            verify(tape, TAPE_BYTES, TAPE_HASH)
            payload.unlink()
            source, result, size, digest = tape, work / "xml", XML_BYTES, XML_HASH
        else:
            direction = "forward"
            source, result, size, digest = xml.resolve(strict=True), tape, TAPE_BYTES, TAPE_HASH
            verify(source, XML_BYTES, XML_HASH)
            for name in ENCODER_DATA:
                (work / name).write_bytes(z.read(name))
        maxima = {}
        with subprocess.Popen([helper, direction, source, result], cwd=work,
                              preexec_fn=lambda: os.sched_setaffinity(0, {cpu})) as worker:
            while worker.poll() is None:
                try:
                    for key, value in sample(worker.pid, tmp_device).items():
                        maxima[key] = max(maxima.get(key, 0), value)
                except (FileNotFoundError, PermissionError, ProcessLookupError):
                    pass
                time.sleep(0.05)
            if worker.returncode:
                raise RuntimeError(f"native {direction} failed with status {worker.returncode}")
        verify(result, size, digest)
        return dict(direction=direction, output_sha256=digest, cpu=cpu, **maxima)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="compressor for forward, enwik9 hybrid archive for inverse")
    parser.add_argument("--xml", type=Path, help="canonical XML for a forward audit")
    parser.add_argument("--cpu", type=int, default=min(os.sched_getaffinity(0)))
    args = parser.parse_args()
    print(json.dumps(audit(args.bundle, args.xml, args.cpu), indent=2))
