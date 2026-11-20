#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fit exact count features over subsets of the preceding eight bytes."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STAGE = ROOT / "experiments/startup.bin"
DYNAMICS = ((63, 2, 2, 1), (63, 3, 2, 1), (31, 2, 2, 1), (63, 2, 1, 1))
WIDTHS = (8, 12, 16, 24, 32)

def fit(hits, totals, masks, prior=16):
    x = np.ascontiguousarray(hits[:, masks])
    y = np.ascontiguousarray(totals[:, masks])
    def objective(w):
        good = prior + x @ w
        all_bits = 2 * prior + y @ w
        return (np.log(all_bits) - np.log(good)).sum(), y.T @ (1 / all_bits) - x.T @ (1 / good)
    result = minimize(objective, np.full(len(masks), 6.0), jac=True, method="L-BFGS-B",
                      bounds=[(0, 255)] * len(masks), options={"ftol": 1e-10, "maxiter": 120})
    return result.x

def rank(hits, totals, masks, weights):
    # A rare feature can carry a high weight while contributing very few bits.
    right = 16 + hits[:, masks] @ weights
    both = 32 + totals[:, masks] @ weights
    impact = []
    for m, w in zip(masks, weights):
        delta = np.log1p(-totals[:, m] * w / both) - np.log1p(-hits[:, m] * w / right)
        impact.append(delta.sum())
    return masks[np.argsort(-np.asarray(impact), kind="stable")]

def train(output):
    bits = np.unpackbits(np.frombuffer(STAGE.read_bytes(), dtype=np.uint8))
    candidates = []
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        cmd = work / "trace"
        subprocess.run([os.environ.get("CC", "cc"), "-O3", HERE / "trace.c", "-o", cmd], check=True)
        for dynamics in DYNAMICS:
            trace = work / "trace.bin"
            subprocess.run([cmd, STAGE, trace, *map(str, dynamics)], check=True)
            shape = (256, len(bits), 2)
            z = np.memmap(trace, dtype="<u2", mode="r", shape=shape).transpose(1, 0, 2)
            hits = np.where(bits[:, None], z[:, :, 1], z[:, :, 0]).astype(np.float64)
            totals = z.sum(axis=2, dtype=np.uint16).astype(np.float64)
            # Add masks in groups so a 256-variable dense solve is unnecessary.
            active = np.empty(0, dtype=int)
            for group in np.array_split(np.arange(256), 8):
                choices = np.union1d(active, group)
                weights = fit(hits, totals, choices)
                active = rank(hits, totals, choices, weights)[:40]
            for width in WIDTHS:
                masks = np.sort(active[:width])
                w = np.rint(fit(hits, totals, masks)).astype(int)
                policy = dict(masks=masks[w > 0].tolist(), weights=[w[w > 0].tolist()],
                              dynamics=list(dynamics), region_shift=31, bit_shift=3, prior=16,
                              exact=True, optimization="-Os")
                candidates.append(policy)
            print(f"Finished {dynamics}, {len(candidates)} candidates", flush=True)
            del z, hits, totals
    output.write_text(json.dumps(candidates, indent=2) + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    train(parser.parse_args().output)
