#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Verify the complete stored payload, model, executable images and both native entry points."""
import argparse
import json
import os
from pathlib import Path
import struct
import tempfile

from build import PROFILES, ROOT, digest, prefix_from_encoder
from check_core import compare
from check_startup import check
from materialize import materialize
from prepare_experiment import prepare


def verify():
    pair = ROOT / "release/size"
    with tempfile.TemporaryDirectory() as folder:
        tmp = Path(folder)
        original = tmp / "reference"
        materialize("size", original, original=True)
        files = {}
        for name in ("comp9", "archive9"):
            parent = (original / name).read_bytes()
            candidate = (pair / name).read_bytes()
            old = struct.unpack_from("<I", parent, 120)[0]
            new = struct.unpack_from("<I", candidate, 120)[0]
            if parent[old:] != candidate[new:] or digest(parent) != PROFILES["size"][name]:
                raise ValueError(f"{name} suffix or reference reconstruction differs")
            files[name] = dict(reference_sha256=digest(parent), candidate_sha256=digest(candidate),
                               identical_suffix_bytes=len(parent)-old, identical_suffix_sha256=digest(parent[old:]))
        archive = (pair / "archive9").read_bytes()
        prefix = prefix_from_encoder((pair / "comp9").read_bytes())
        payload, model = struct.unpack_from("<II", archive, len(archive)-8)
        if not archive.startswith(prefix) or len(prefix) + model + payload + 8 != len(archive):
            raise ValueError("archive framing differs from the compressor's decoder prefix")
        images = compare("size", original, pair)
        source = tmp / "source"
        prepare("size-original", source)
        fixture = source / "prof_input/input2"
        checks = {mode: check(pair, fixture if mode == "encode" else None, mode) for mode in ("encode", "decode")}
        return dict(profile="size", reference="Ex-Girlfriend 2.0", files=files,
                    native_images=images, decoder_prefix_bytes=len(prefix), weights_bytes=model,
                    payload_bytes=payload, trailer_bytes=8, entry_points=checks,
                    encoder_prefix_test_input={"description": "upstream profiling fixture, used only to reach decoder-prefix emission",
                                               "bytes": fixture.stat().st_size, "sha256": digest(fixture.read_bytes())},
                    full_candidate_enwik9_roundtrip=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new JSON verification record")
    dest = parser.parse_args().output
    if dest.exists():
        parser.error("output already exists")
    report = verify()
    with tempfile.NamedTemporaryFile(dir=dest.parent, mode="w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
        f.flush()
        os.link(f.name, dest)
    print(f"Verified both native images and all {report['payload_bytes']} compressed Wikipedia bytes")
