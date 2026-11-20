#!/usr/bin/env python3
"""Compare native bootstrap peak RSS and the entire restored ELF for the two releases."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from build import ROOT, digest, prefix_from_encoder
from check_core import native_image
from materialize import materialize, reference_head


def capture(executable, hook, folder, cpu):
    dump = folder / "captured"
    dump.unlink(missing_ok=True)
    env = dict(PATH="/usr/bin:/bin", LC_ALL="C", LD_PRELOAD=str(hook), STUB_CAPTURE=str(dump))
    start = time.monotonic()
    child = subprocess.Popen([executable], cwd=folder, env=env, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, preexec_fn=lambda: os.sched_setaffinity(0, {cpu}))
    _, status, usage = os.wait4(child.pid, 0)
    child.returncode = os.waitstatus_to_exitcode(status)
    if child.returncode:
        raise RuntimeError(f"{executable} exited with status {child.returncode}")
    flat = native_image(dump, executable)
    return dict(peak_rss_kib=usage.ru_maxrss, wall_seconds=round(time.monotonic()-start, 3),
                native_bytes=len(flat), native_sha256=digest(flat), self_path_verified=True)


def measure():
    cpu = min(os.sched_getaffinity(0))
    out = {}
    with tempfile.TemporaryDirectory() as scratch:
        tmp = Path(scratch)
        hook = tmp / "capture.so"
        subprocess.run([os.environ.get("CC", "cc"), "-shared", "-fPIC", "-O2",
                        ROOT / "upstream/stub_capture.c", "-o", hook], check=True)
        for profile in ("size", "prize"):
            release = tmp / profile
            materialize(profile, release)
            current = (release / "comp9").read_bytes()
            old_result = json.loads((ROOT / "results/v0.0.2" / f"{profile}.json").read_text())
            old_head = (ROOT / "experiments/low-memory" / f"{profile}-v002-head.bin").read_bytes()
            older = reference_head(current, old_head)
            if digest(older) != old_result["files"]["comp9"]["sha256"]:
                raise ValueError("historical reference compressor hash differs")
            pairs = {"compressor": (older, current)}
            if profile == "size":
                arc = (release / "archive9").read_bytes()
                original = reference_head(arc, old_head)
                if digest(original) != old_result["files"]["archive9"]["sha256"]:
                    raise ValueError("historical reference archive hash differs")
                pairs["archive"] = original, arc
            else:
                pairs["decoder_prefix_only"] = prefix_from_encoder(older), prefix_from_encoder(current)
            out[profile] = {}
            for entry, pair in pairs.items():
                obs = {}
                for tag, data in zip(("v0.0.2", "v0.0.3"), pair):
                    exe = tmp / f"{profile}-{entry}-{tag}"
                    exe.write_bytes(data)
                    exe.chmod(0o755)
                    obs[tag] = capture(exe, hook, tmp, cpu)
                if obs["v0.0.2"]["native_sha256"] != obs["v0.0.3"]["native_sha256"]:
                    raise ValueError(f"{profile}/{entry} restored different images")
                out[profile][entry] = obs
                print(f"Compared {profile} {entry}, RSS {obs['v0.0.2']['peak_rss_kib']} -> {obs['v0.0.3']['peak_rss_kib']} KiB", flush=True)
    return dict(scope="Linux wait4 peak RSS through native image reconstruction; stops before Wikipedia model main", profiles=out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    path = parser.parse_args().output
    result = measure()
    with path.open("x") as out:
        out.write(json.dumps(result, indent=2) + "\n")
