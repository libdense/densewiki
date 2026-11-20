#!/usr/bin/env python3
"""Extract a verified upstream source tree and optionally apply one cache experiment."""
import argparse
import hashlib
import io
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

from build import ROOT

SOURCES = {
    "size": ("ex-girlfriend-2.0", "de6e996caa4fa978d663e3ff3c419f90a5e9a712a7d2b358d92899031a3ed410", "ex2"),
    "prize": ("cmix-neif-2.0", "bb7a8ab89bdabdd680d592da1c4c8bd2be26c1e6bc0412c8c4126758f2086f3f", "neif"),
}
ARMS = ("size-original", "size-shared", "prize-original", "prize-shared", "prize-47", "prize-lowmem")


def prepare(arm, output):
    if output.exists():
        raise FileExistsError(f"output must be a new directory: {output}")
    profile, mode = arm.split("-")
    name, expected, patch_name = SOURCES[profile]
    with tarfile.open(ROOT / "upstream/sources.tar.xz", "r:xz") as outer:
        with outer.extractfile(f"{name}.tar") as member:
            raw = member.read()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f"{name} source tar hash mismatch")
    with tempfile.TemporaryDirectory(dir=output.parent) as t:
        staging = Path(t)
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as source:
            source.extractall(staging, filter="data")
        tree = staging / name
        if mode != "original":
            patches = ROOT / "experiments/shared-sketch"
            shutil.copy2(patches / "densewiki_sketch.h", tree / "src")
            names = [patches / f"{patch_name}-shared-sketch.patch"]
            if mode == "47":
                names.append(patches / "neif-wide47.patch")
            if mode == "lowmem":
                names.append(ROOT / "experiments/low-memory/prize-low-memory.patch")
            for patch in names:
                with patch.open("rb") as diff:
                    subprocess.run(["patch", "--batch", "--forward", "-p1"], stdin=diff, cwd=tree, check=True)
        if output.exists():
            raise FileExistsError(output)
        tree.rename(output)
    print(f"Prepared {arm} in {output}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("arm", choices=ARMS)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    prepare(args.arm, args.output.resolve())
