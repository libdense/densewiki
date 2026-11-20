#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fit fine and coarse byte contexts and retain them by their cost when omitted."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from fit import HERE, STAGE, fit, rank, np

CLASSES = (255, 248, 240, 224, 192, 15, 7, 199, 252, 56, 128, 63, 31)
DYNAMICS = ((63, 2, 2, 1), (63, 3, 2, 1), (31, 2, 1, 1))

def train(output):
    candidates = []
    bits = np.unpackbits(np.frombuffer(STAGE.read_bytes(), dtype=np.uint8))
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        tool = work / "trace"
        subprocess.run([os.environ.get("CC", "cc"), "-O3", HERE / "trace.c", "-o", tool], check=True)
        for dynamics in DYNAMICS:
            # Keep feature order stable. Every candidate uses the same recorded bits.
            stored = {}
            active = []
            for c in CLASSES:
                limit = 256 if c == 255 else 64
                trace = work / "events"
                subprocess.run([tool, STAGE, trace, *map(str, dynamics), str(c), str(limit)], check=True)
                z = np.memmap(trace, dtype="<u2", mode="r", shape=(limit, len(bits), 2))
                for group in np.array_split(np.arange(0 if c == 255 else 1, limit), (limit + 31) // 32):
                    for m in group:
                        v = z[m]
                        stored[(m,c)] = (np.where(bits, v[:,1], v[:,0]), v.sum(axis=1, dtype=np.uint16))
                    keys = active + [(m, c) for m in group]
                    hits = np.column_stack([stored[k][0] for k in keys]).astype(float)
                    totals = np.column_stack([stored[k][1] for k in keys]).astype(float)
                    indices = np.arange(len(keys))
                    w = fit(hits, totals, indices)
                    indices = rank(hits, totals, indices, w)[:40]
                    active = [keys[j] for j in indices]
                    stored = {k:stored[k] for k in active}
                del z
            for width in (8, 12, 16, 20, 24, 32):
                keys = sorted(active[:width], key=lambda k: (k[0], -k[1]))
                hits = np.column_stack([stored[k][0] for k in keys]).astype(float)
                totals = np.column_stack([stored[k][1] for k in keys]).astype(float)
                for bit_shift in (3, 2):
                    weights = []
                    for group in range(8 >> bit_shift):
                        keep = ((np.arange(len(bits)) % 8) >> bit_shift) == group
                        w = fit(hits[keep], totals[keep], np.arange(len(keys)))
                        weights.append(np.rint(w).astype(int))
                    used = np.any(np.asarray(weights) != 0, axis=0)
                    candidates.append(dict(masks=[int(k[0]) for k,u in zip(keys,used) if u],
                        classes=[k[1] for k,u in zip(keys,used) if u],
                        weights=[w[used].tolist() for w in weights], dynamics=list(dynamics),
                        region_shift=31, bit_shift=bit_shift, prior=16))
            print(f"Finished class fits for {dynamics}", flush=True)
            output.write_text(json.dumps(candidates, indent=2) + "\n")

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    train(p.parse_args().output)
