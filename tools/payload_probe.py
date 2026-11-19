#!/usr/bin/env python3
"""Measure the whole coded payload and cold Plausible controls on canonical inputs."""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import tempfile
import zlib

CANONICAL = "159b85351e5f76e60cbe32e04c677847a9ecba3adc79addab6f4c6c7aa3744bc"
REFERENCE = "0b65bc79917f84b78f4974a2dc94d4d4c3fc6c0c53234bdcb6c282db802635a3"


def file_hash(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("enwik9", type=Path)
    ap.add_argument("reference_archive9", type=Path)
    ap.add_argument("--plausible", type=Path, help="optional binary built from the supplied plausible source")
    a = ap.parse_args()
    if file_hash(a.enwik9) != CANONICAL or file_hash(a.reference_archive9) != REFERENCE:
        raise ValueError("canonical inputs required")
    ref = a.reference_archive9.read_bytes()
    n, model = struct.unpack_from("<II", ref, len(ref)-8)
    payload = ref[-8-n:-8]
    histogram = collections.Counter(payload)
    entropy = -sum(f / n * math.log2(f / n) for f in histogram.values())
    result = {"enwik9_sha256": CANONICAL, "reference_sha256": REFERENCE,
              "payload_sha256": hashlib.sha256(payload).hexdigest(), "payload_bytes": n,
              "weights_bytes": model, "payload_order_zero_bits_per_byte": entropy,
              "payload_zlib9_bytes": len(zlib.compress(payload, 9)), "samples": []}
    if a.plausible:
        exe = a.plausible.resolve()
        with tempfile.TemporaryDirectory() as wd, a.enwik9.open("rb") as raw:
            d = Path(wd)
            for label, offsets in [("enwik9", (0, 440000000, 903000000)),
                                   ("coded-payload", (0, 40000000, 80000000))]:
                for off in offsets:
                    if label == "enwik9":
                        raw.seek(off)
                        data = raw.read(1000000)
                    else:
                        data = payload[off:off+1000000]
                    (d/"raw").write_bytes(data)
                    subprocess.run([exe,"-q","c",d/"raw",d/"out"],check=True,stdout=subprocess.DEVNULL)
                    subprocess.run([exe,"-q","d",d/"out",d/"restored"],check=True,stdout=subprocess.DEVNULL)
                    if (d/"restored").read_bytes() != data:
                        raise ValueError("Plausible round-trip failure")
                    result["samples"].append({"source": label, "offset": off, "bytes": len(data),
                                             "sha256": hashlib.sha256(data).hexdigest(),
                                             "plausible_bytes": (d/"out").stat().st_size, "exact": True})
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
