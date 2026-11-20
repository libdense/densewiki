#!/usr/bin/env python3
"""Stop each genuine no-argument entry point once its extracted components are observable."""
import argparse
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import tempfile
import time

from build import digest, prefix_from_encoder
from payload_probe import file_hash, CANONICAL


def check(directory, wiki, mode):
    archive = (directory / "archive9").read_bytes()
    encoder = (directory / "comp9").read_bytes()
    payload, weight = struct.unpack_from("<II", archive, len(archive) - 8)
    wname = "weights-poc8m_w2048_tf2t3_pruned_v5k_np2.c5"
    prefix = prefix_from_encoder(encoder)
    if not archive.startswith(prefix):
        raise ValueError("encoder-selected decoder differs from the supplied archive")
    if mode == "encode":
        exe = "comp9"
        expected = {".decomp_bin": (len(prefix), digest(prefix))}
    else:
        exe = "archive9"
        expected = {".ready4cmix_decomp": (payload, digest(archive[-8-payload:-8])),
                    wname: (weight, digest(archive[-8-weight-payload:-8-payload]))}
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        # The executable uses its own path. A hard or symbolic link is sufficient.
        (d/exe).symlink_to(directory/exe)
        if mode == "encode":
            (d/"enwik9").symlink_to(wiki)
        with (d/"log").open("wb") as log:
            proc = subprocess.Popen([str(d/exe)], cwd=d, stdout=log, stderr=log,
                                    start_new_session=True, env=dict(os.environ, LC_ALL="C"))
            try:
                deadline = time.monotonic() + 600
                while True:
                    if all((d/k).is_file() and (d/k).stat().st_size == size for k,(size,h) in expected.items()):
                        observed = {k:file_hash(d/k) for k in expected}
                        if observed == {k:h for k,(n,h) in expected.items()}:
                            return {"mode": mode, "files": {k:{"bytes":n,"sha256":h} for k,(n,h) in expected.items()}}
                    if proc.poll() is not None:
                        raise RuntimeError(f"{exe} exited early ({proc.returncode}): {(d/'log').read_text(errors='replace')[-900:]}")
                    if time.monotonic() > deadline:
                        raise TimeoutError(f"{exe} startup exceeded 600 seconds")
                    time.sleep(0.04)
            finally:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="contains both candidate files")
    parser.add_argument("enwik9", nargs="?", type=Path, help="canonical input, required for encode")
    parser.add_argument("mode", choices=["encode","decode"])
    args = parser.parse_args()
    if args.mode == "encode" and args.enwik9 is None:
        parser.error("encode requires a path to enwik9")
    if args.enwik9 is not None and file_hash(args.enwik9) != CANONICAL:
        raise ValueError("input must be original enwik9")
    print(json.dumps(check(args.directory.resolve(), args.enwik9.resolve() if args.enwik9 else None, args.mode), indent=2))
