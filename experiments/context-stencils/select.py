#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare complete linked loaders using the candidate and reference entropy coders."""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from build import encode_policy, linked_image

def select(source, output, additional=()):
    output.mkdir(exist_ok=False)
    candidates = json.loads(source.read_text())
    for path in additional:
        candidates.extend(json.loads(path.read_text()))
    rows = []
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        mix = work / "mix"
        subprocess.run([os.environ.get("CC", "cc"), "-O3", ROOT / "src/mix.c", "-o", mix], check=True)
        for ordinal, candidate in enumerate(candidates):
            modes = ("tree16", "tree18", "tree20") if "classes" in candidate else ("legacy", "exact", "tree16", "tree18", "tree20")
            for mode in modes:
                policy = dict(candidate, exact=(mode == "exact"))
                if mode.startswith("tree"):
                    policy["tree_bits"] = int(mode[4:])
                cfg = work / "fit.dat"
                cfg.write_bytes(encode_policy(policy))
                out = work / "coded"
                out.unlink(missing_ok=True)
                subprocess.run([mix, "encode", cfg, ROOT / "experiments/startup.bin", out], check=True)
                coded = out.read_bytes()
                for flag in ("-Os", "-Oz"):
                    policy = dict(policy, optimization=flag)
                    image = linked_image(policy, coded, work)
                    rows.append((len(image), len(coded), ordinal, mode, flag, policy))
    rows.sort(key=lambda row: row[:5])
    (output / "policy.json").write_text(json.dumps(rows[0][-1], indent=2) + "\n")
    with (output / "linked.tsv").open("w") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(["startup_bytes", "coded_bytes", "candidate", "layout", "compiler"])
        writer.writerows(row[:5] for row in rows)
    print(f"Selected {rows[0][:5]} from {len(rows)} linked programs")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidates", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--add", action="append", type=Path, default=[])
    args = parser.parse_args()
    select(args.candidates, args.output, args.add)
