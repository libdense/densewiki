#!/usr/bin/env python3
"""Restore the standalone prize-track compressor or an original reference pair."""
import argparse
import json
from pathlib import Path
import struct
import tempfile
from build import PROFILES, ROOT, digest

def reference_head(data, head):
    old_size = struct.unpack_from("<I", data, 120)[0]
    header = bytearray(head)
    header[120:144] = struct.pack("<I", len(head)) + data[124:144]
    return bytes(header) + data[old_size:]


def materialize(profile, output, original=False, reference_archive=None):
    if output.exists():
        raise FileExistsError(f"output must be a new directory: {output}")
    record = json.loads((ROOT / f"results/{profile}.json").read_text())
    if profile == "size":
        files = {name:(ROOT / "release/size" / name).read_bytes() for name in ("comp9","archive9")}
    else:
        strong = (ROOT / "release/size/comp9").read_bytes()
        strong_hash = json.loads((ROOT/"results/size.json").read_text())["files"]["comp9"]["sha256"]
        if digest(strong) != strong_hash:
            raise ValueError("size encoder SHA-256 mismatch")
        n = struct.unpack_from("<I", strong, len(strong)-4)[0]
        here = ROOT / "release/prize"
        comp = (here/"comp9-prefix.bin").read_bytes() + strong[-12-n:-12] + (here/"comp9-footer.bin").read_bytes()
        files = {"comp9": comp}
        if reference_archive:
            arc = reference_archive.read_bytes()
            if digest(arc) != PROFILES[profile]["archive9"]:
                raise ValueError("original cmix-neif 2.0 archive SHA-256 mismatch")
            head_size = struct.unpack_from("<I",comp,120)[0]
            files["archive9"] = reference_head(arc, comp[:head_size])
    original_head = (ROOT/"upstream/original-startup.bin").read_bytes()
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        dest = Path(tmp) / "publish"
        dest.mkdir()
        for name, data in files.items():
            if digest(data) != record["files"][name]["sha256"]:
                raise ValueError(f"candidate {name} SHA-256 mismatch")
            if original:
                data = reference_head(data, original_head)
                if digest(data) != PROFILES[profile][name]:
                    raise ValueError(f"restored upstream {name} SHA-256 mismatch")
            (dest/name).write_bytes(data)
            (dest/name).chmod(0o755)
        if output.exists():
            raise FileExistsError(output)
        dest.rename(output)
    return sorted(files)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("profile", choices=PROFILES)
    p.add_argument("output", type=Path)
    p.add_argument("--original", action="store_true", help="recover original, hash-pinned upstream artifacts")
    p.add_argument("--reference-archive", type=Path, help="optional original cmix-neif 2.0 archive9")
    a = p.parse_args()
    print(", ".join(materialize(a.profile, a.output.resolve(), a.original, a.reference_archive)))
