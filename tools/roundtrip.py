#!/usr/bin/env python3
"""Run a real one-core enwik9 encode, fresh decode and byte comparison on Linux."""
import argparse
import fcntl
import filecmp
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time

from build import PROFILES, ROOT
from materialize import materialize
from payload_probe import CANONICAL, file_hash

WIKI_BYTES = 1_000_000_000


def write_record(path, record):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(record, indent=2) + "\n")
    temp.replace(path)


def artifact(path):
    return {"bytes": path.stat().st_size, "sha256": file_hash(path)}


def process_rss(pid):
    pending = [pid]
    seen = set()
    kib = 0
    while pending:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        proc = Path(f"/proc/{pid}")
        try:
            with (proc / "status").open() as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        kib += int(line.split()[1])
                        break
            for task in (proc / "task").iterdir():
                pending.extend(int(child) for child in (task / "children").read_text().split())
        except (FileNotFoundError, ProcessLookupError):
            continue
    return kib


def launch(binary, folder, cpu):
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LANG": "C", "TZ": "UTC"}
    start = time.monotonic()
    peak = 0
    with (folder / "run.log").open("wb") as log:
        proc = subprocess.Popen([str(binary)], cwd=folder, env=env, stdout=log, stderr=log,
                                preexec_fn=lambda: os.sched_setaffinity(0, {cpu}), start_new_session=True)
        try:
            while proc.poll() is None:
                peak = max(peak, process_rss(proc.pid))
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
        except BaseException:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            raise
    if proc.returncode:
        raise RuntimeError(f"{binary.name} exited with status {proc.returncode}. See {folder / 'run.log'}")
    return {"wall_seconds": round(time.monotonic()-start, 3), "max_sampled_process_tree_rss_kib": peak}


def run_stage(work, mode, executable, wiki, canonical, expected, cpu):
    encoding = mode == "encode"
    program, output = ("comp9", "archive9") if encoding else ("archive9", "enwik9_uncompressed")
    done = work / f"{mode}.json"
    if done.exists():
        record = json.loads(done.read_text())
        saved = work / record["directory"] / output
        if artifact(saved) != record["result"] or (expected and record["result"] != expected):
            raise ValueError(f"completed {mode} output failed revalidation: {saved}")
        return saved
    folder = Path(tempfile.mkdtemp(prefix=f"{mode}-", dir=work))
    shutil.copyfile(executable, folder / program)
    (folder / program).chmod(0o755)
    if encoding:
        (folder / "enwik9").symlink_to(wiki)
    print(f"Running {mode} on CPU {cpu}. Log: {folder / 'run.log'}", flush=True)
    timing = launch(folder / program, folder, cpu)
    produced = folder / output
    result = artifact(produced)
    record = dict(timing, directory=folder.name, result=result)
    if expected and result != expected:
        write_record(folder / "unexpected-output.json", record)
        raise ValueError(f"{mode} produced unexpected bytes. See {folder}")
    if not encoding and (result != canonical or not filecmp.cmp(wiki, produced, shallow=False)):
        raise ValueError(f"decoded output differs from the canonical enwik9: {folder}")
    write_record(done, record)
    return produced


def roundtrip(profile, wiki, work, encoder, resume, cpu):
    wiki = wiki.resolve(strict=True)
    canonical = {"bytes": WIKI_BYTES, "sha256": CANONICAL}
    if artifact(wiki) != canonical:
        raise ValueError("input must be the canonical 1,000,000,000-byte enwik9")
    allowed = os.sched_getaffinity(0)
    cpu = min(allowed) if cpu is None else cpu
    if cpu not in allowed:
        raise ValueError(f"CPU {cpu} is outside this process's affinity")
    work = work.resolve()
    if resume:
        if not (work / "input.json").is_file():
            raise ValueError("--resume requires a directory initialized by this tool")
    else:
        work.mkdir(parents=True, exist_ok=False)
    known = json.loads((ROOT / f"results/{profile}.json").read_text())["files"]
    with (work / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        expected = None
        if encoder is None:
            if profile == "size":
                encoder = ROOT / "release/size/comp9"
            else:
                if not (work / "release").exists():
                    materialize("prize", work / "release")
                encoder = work / "release/comp9"
            expected = {key: known["archive9"][key] for key in ("bytes", "sha256")}
            if file_hash(encoder) != known["comp9"]["sha256"]:
                raise ValueError("release encoder hash mismatch")
        encoder = encoder.resolve(strict=True)
        recipe = {"profile": profile, "canonical_input": canonical, "encoder": artifact(encoder),
                  "expected_archive": expected}
        marker = work / "input.json"
        if marker.exists() and json.loads(marker.read_text()) != recipe:
            raise ValueError("run directory belongs to different inputs or a different encoder")
        write_record(marker, recipe)
        (work / "verified.json").unlink(missing_ok=True)
        archive = run_stage(work, "encode", encoder, wiki, canonical, expected, cpu)
        decoded = run_stage(work, "decode", archive, wiki, canonical, canonical, cpu)
        if not filecmp.cmp(wiki, decoded, shallow=False):
            raise ValueError("fresh comparison to enwik9 failed")
        report = dict(recipe, score_bytes=archive.stat().st_size+encoder.stat().st_size, args_bytes=0,
                      archive=artifact(archive), restored=artifact(decoded), byte_comparison="equal",
                      encode=json.loads((work/"encode.json").read_text()),
                      decode=json.loads((work/"decode.json").read_text()))
        write_record(work / "verified.json", report)
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("profile", choices=PROFILES)
    p.add_argument("enwik9", type=Path)
    p.add_argument("output", type=Path, help="fresh run directory, or existing one with --resume")
    p.add_argument("--encoder", type=Path, help="test an independently built experiment and measure its new archive")
    p.add_argument("--resume", action="store_true", help="revalidate and reuse completed stages")
    p.add_argument("--cpu", type=int, help="one permitted logical CPU, default lowest in affinity")
    a = p.parse_args()
    roundtrip(a.profile, a.enwik9, a.output, a.encoder, a.resume, a.cpu)
