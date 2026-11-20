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
from payload_probe import CANONICAL, file_hash
from materialize import materialize
from prepare_experiment import prepare


def verify(profile="size", reference_archive=None, wiki=None):
    with tempfile.TemporaryDirectory() as folder:
        tmp = Path(folder)
        original = tmp / "reference"
        materialize(profile, original, original=True, reference_archive=reference_archive)
        if profile == "size":
            pair = ROOT / "release/size"
        else:
            if reference_archive is None:
                raise ValueError("prize verification needs the original cmix-neif 2.0 archive")
            pair = tmp / "prize"
            materialize(profile, pair, reference_archive=reference_archive)
        files = {}
        for name in ("comp9", "archive9"):
            parent = (original / name).read_bytes()
            candidate = (pair / name).read_bytes()
            old = struct.unpack_from("<I", parent, 120)[0]
            new = struct.unpack_from("<I", candidate, 120)[0]
            if parent[old:] != candidate[new:] or digest(parent) != PROFILES[profile][name]:
                raise ValueError(f"{name} suffix or reference reconstruction differs")
            files[name] = dict(reference_sha256=digest(parent), candidate_sha256=digest(candidate),
                               identical_suffix_bytes=len(parent)-old, identical_suffix_sha256=digest(parent[old:]))
        archive = (pair / "archive9").read_bytes()
        prefix = prefix_from_encoder((pair / "comp9").read_bytes())
        payload, model = struct.unpack_from("<II", archive, len(archive)-8)
        if not archive.startswith(prefix) or len(prefix) + model + payload + 8 != len(archive):
            raise ValueError("archive framing differs from the compressor's decoder prefix")
        images = compare(profile, original, pair)
        if wiki is None:
            source = tmp / "source"
            prepare(f"{profile}-original", source)
            fixture = source / "prof_input/input2"
            description = "upstream profiling fixture for decoder-prefix emission"
        else:
            fixture = wiki.resolve(strict=True)
            if fixture.stat().st_size != 1_000_000_000 or file_hash(fixture) != CANONICAL:
                raise ValueError("expected the canonical enwik9 input")
            description = "canonical enwik9 used for decoder-prefix emission"
        checks = {mode: check(pair, fixture if mode == "encode" else None, mode) for mode in ("encode", "decode")}
        return dict(profile=profile, reference={"size": "Ex-Girlfriend 2.0", "prize": "cmix-neif 2.0"}[profile], files=files,
                    native_images=images, decoder_prefix_bytes=len(prefix), weights_bytes=model,
                    payload_bytes=payload, trailer_bytes=8, entry_points=checks,
                    encoder_prefix_test_input={"description": description,
                                               "bytes": fixture.stat().st_size, "sha256": file_hash(fixture)},
                    full_candidate_enwik9_roundtrip=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new JSON verification record")
    parser.add_argument("--profile", choices=PROFILES, default="size")
    parser.add_argument("--reference-archive", type=Path, help="original cmix-neif archive9 for prize")
    parser.add_argument("--enwik9", type=Path, help="canonical input for the native encoder entry point")
    args = parser.parse_args()
    dest = args.output
    if dest.exists():
        parser.error("output already exists")
    report = verify(args.profile, args.reference_archive, args.enwik9)
    with tempfile.NamedTemporaryFile(dir=dest.parent, mode="w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
        f.flush()
        os.link(f.name, dest)
    print(f"Verified both native images and all {report['payload_bytes']} compressed Wikipedia bytes")
