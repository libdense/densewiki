#!/usr/bin/env python3
"""Fit counted context mixtures on the shipped startup data, using a shared causal replay."""
import argparse
import json
import os
import subprocess
from pathlib import Path

for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"

import numpy as np
from scipy.optimize import minimize

ORIGINAL = [1, 2, 3, 4, 0, 17, 6, 5, 9]
EXTENDED = ORIGINAL + [7, 8, 16, 12, 10, 33, 18, 15, 32, 24, 65, 129, 20, 11, 13, 48,
                       64, 128, 19, 34, 40, 96, 14]
SEARCH_SHAPES = [(31, 3), (31, 2), (31, 1), (31, 0), (12, 3), (12, 2), (12, 1),
                 (11, 3), (11, 2), (10, 3)]


def policy_bytes(model):
    header = [len(model["masks"]), model["region_shift"], model["bit_shift"], model["prior"]]
    return b"DWM1" + bytes(header + model["masks"]) + bytes(x for row in model["weights"] for x in row)


def fit_weights(hits, totals, prior):
    # Each mask has a causal pair of counts per bit. All mixtures can reuse these pairs.
    # The objective is the number of natural-log units needed for the observed bits.
    initial = np.full(hits.shape[1], 8.0)
    initial[:9] = np.array([4, 2, 8, 1, 1, 8, 4, 8, 4]) * (prior / 3)
    def loss(w):
        right = prior + hits @ w
        both = 2 * prior + totals @ w
        nll = np.log(both).sum() - np.log(right).sum()
        grad = totals.T @ (1 / both) - hits.T @ (1 / right)
        return nll, grad
    res = minimize(loss, initial, jac=True, method="L-BFGS-B",
                   bounds=[(0, 255)] * len(initial),
                   options={"maxiter": 110, "ftol": 1e-10, "gtol": 1e-5})
    return np.rint(res.x).clip(0, 255).astype(int).tolist()


def run(mix, raw_file, work, counts):
    raw = np.fromfile(raw_file, dtype=np.uint8)
    if len(raw) != 12311:
        raise ValueError("expected the 12,311-byte upstream bootstrap image")
    bits = np.unpackbits(raw)
    bit_no = np.arange(len(bits), dtype=np.int32)
    rows = []
    for size in counts:
        masks = EXTENDED[:size]
        base = {"masks": masks, "region_shift": 31, "bit_shift": 3, "prior": 3,
                "weights": [[1] * size]}
        trace_file = work / f"trace-{size}.bin"
        config = work / f"trace-{size}.policy"
        config.write_bytes(policy_bytes(base))
        subprocess.run([mix, "trace", config, raw_file, trace_file], check=True)
        trace = np.fromfile(trace_file, dtype="<u2").reshape(len(bits), size, 2)
        totals = trace.astype(np.float64).sum(axis=2)
        hits = np.where(bits[:, None], trace[:, :, 1], trace[:, :, 0]).astype(np.float64)
        for region_shift, bit_shift in SEARCH_SHAPES:
            group = ((bit_no >> 3) >> region_shift) * (8 >> bit_shift) + ((bit_no % 8) >> bit_shift)
            for prior in (8, 24):
                rows_w = [fit_weights(hits[group == g], totals[group == g], prior)
                          for g in range(int(group.max()) + 1)]
                model = dict(base, region_shift=region_shift, bit_shift=bit_shift,
                             prior=prior, weights=rows_w)
                name = f"m{size}-r{region_shift}-b{bit_shift}-p{prior}"
                config_path = work / f"{name}.policy"
                config_path.write_bytes(policy_bytes(model))
                out = work / f"{name}.coded"
                subprocess.run([mix, "encode", config_path, raw_file, out], check=True)
                bits_bytes = out.stat().st_size
                # The complete, actually linked program is measured by the release builder.
                rows.append({"name": name, "stream": bits_bytes,
                             "stream_and_table": bits_bytes + len(masks) * (len(rows_w) + 1),
                             "model": model})
        trace_file.unlink()
        print(f"Evaluated {len(rows)} policies, best stream + table "
              f"{min(r['stream_and_table'] for r in rows)} bytes", flush=True)
        (work / "candidates.json").write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mix", type=Path)
    parser.add_argument("stage", type=Path)
    parser.add_argument("output", type=Path, help="fresh experiment directory")
    parser.add_argument("--models", type=int, nargs="+", choices=[9, 12, 17, 24, 32],
                        default=[9, 12, 17, 24, 32])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    run(args.mix.resolve(), args.stage.resolve(), args.output, args.models)
