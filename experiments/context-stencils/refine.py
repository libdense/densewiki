#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Refit the selected stencil weights to the observed counts in the deployed table."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from fit import ROOT, STAGE, fit, np
sys.path.insert(0, str(ROOT / "tools"))
from build import encode_policy, linked_image

def refine(seed, output):
    base = json.loads(seed.read_text())
    bits = np.unpackbits(np.frombuffer(STAGE.read_bytes(), dtype=np.uint8))
    pos = np.arange(len(bits))
    candidates = [base]
    trials = []
    output.mkdir(exist_ok=False)
    with tempfile.TemporaryDirectory() as folder:
        tmp = Path(folder)
        cmd = tmp / "mix"
        subprocess.run([os.environ.get("CC", "cc"), "-O3", ROOT / "src/mix.c", "-o", cmd], check=True)
        cfg = tmp / "policy"
        cfg.write_bytes(encode_policy(base))
        subprocess.run([cmd, "trace", cfg, STAGE, tmp / "trace"], check=True)
        z = np.fromfile(tmp / "trace", dtype="<u2").reshape(len(bits), -1, 2)
        hits = np.where(bits[:, None], z[:,:,1], z[:,:,0]).astype(float)
        totals = z.sum(axis=2).astype(float)
        for region, bit_shift in ((31,3),(31,2),(31,1),(31,0),(13,3),(13,2),(12,3)):
            group = ((pos >> 3) >> region) * (8 >> bit_shift) + ((pos % 8) >> bit_shift)
            # A small fitting prior allows a wider range of weight-to-prior ratios.
            weights = []
            for g in range(group.max() + 1):
                choose = group == g
                weights.append(fit(hits[choose], totals[choose], np.arange(z.shape[1]), prior=4))
            for prior in (2, 4, 8, 12, 16, 24, 32):
                w = np.rint(np.array(weights) * prior / 4).clip(0, 255).astype(int)
                # Keep the stencil indexes stable: the deployed hash includes their ordinal.
                candidates.append(dict(base, prior=prior, weights=w.tolist(),
                                       region_shift=region, bit_shift=bit_shift))
        for index, policy in enumerate(candidates):
            cfg.write_bytes(encode_policy(policy))
            out = tmp / "stream"
            out.unlink(missing_ok=True)
            subprocess.run([cmd, "encode", cfg, STAGE, out], check=True)
            stream = out.read_bytes()
            for flag in ("-Os", "-Oz"):
                choice = dict(policy, optimization=flag)
                head = linked_image(choice, stream, tmp)
                trials.append((len(head), len(stream), index, flag, choice))
    trials.sort(key=lambda r: r[:4])
    (output / "policy.json").write_text(json.dumps(trials[0][-1], indent=2) + "\n")
    with (output / "linked.tsv").open("w") as f:
        f.write("startup_bytes\tcoded_bytes\tcandidate\tcompiler\tprior\tregion_shift\tbit_shift\n")
        for size, stream, index, flag, model in trials:
            f.write(f"{size}\t{stream}\t{index}\t{flag}\t{model['prior']}\t{model['region_shift']}\t{model['bit_shift']}\n")
    print(f"Selected {trials[0][:4]} from {len(trials)} linked programs")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("seed", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    refine(args.seed, args.output)
