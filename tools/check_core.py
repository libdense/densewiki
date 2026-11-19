#!/usr/bin/env python3
"""Compare the complete native images produced by the published and candidate startup code."""
import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

from build import PROFILES, ROOT, digest
from payload_probe import file_hash

MARK = b"B5C2SELFPATH_V1\0"


def native_image(capture, program):
    data = capture.read_bytes()
    words = struct.unpack_from("<6I", program.read_bytes(), 120)
    image_bytes = words[3]
    path = os.fsencode(str(program.resolve()))
    expected = path + struct.pack("<I", len(path)) + MARK
    if data[image_bytes:] != expected:
        raise ValueError(f"{program} produced an unexpected self-path trailer")
    return data[:image_bytes]


def compare(profile, source, candidate):
    manifest = json.loads((ROOT / f"results/{profile}.json").read_text())
    results = {}
    with tempfile.TemporaryDirectory() as folder:
        temp = Path(folder)
        helper = temp / "capture.so"
        subprocess.run([os.environ.get("CC", "cc"), "-shared", "-fPIC", "-O2",
                        ROOT / "upstream/stub_capture.c", "-o", helper], check=True)
        for name in ("comp9", "archive9"):
            images = []
            for tag, path, known in [("reference", source/name, PROFILES[profile][name]),
                                     ("candidate", candidate/name, manifest["files"][name]["sha256"])]:
                if file_hash(path) != known:
                    raise ValueError(f"{tag} {name} hash differs from release manifest")
                capture = temp / f"{name}-{tag}"
                env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LD_PRELOAD": str(helper),
                       "STUB_CAPTURE": str(capture)}
                subprocess.run([path], env=env, cwd=temp, check=True, timeout=600,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                images.append(native_image(capture, path))
            if images[0] != images[1]:
                raise ValueError(f"{profile} {name} native images differ")
            results[name] = {"native_bytes_compared": len(images[0]), "native_sha256": digest(images[0]),
                             "self_path_trailers_valid": True}
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("profile", choices=PROFILES)
    p.add_argument("reference", type=Path)
    p.add_argument("candidate", type=Path)
    a = p.parse_args()
    print(json.dumps(compare(a.profile, a.reference.resolve(), a.candidate.resolve()), indent=2))
