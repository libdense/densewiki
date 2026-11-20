#!/usr/bin/env python3
"""Choose the smallest complete linked image across both startup searches."""
import argparse
import json
from pathlib import Path
import tempfile

from build import linked_image


def select(inputs, dest):
    trials = []
    with tempfile.TemporaryDirectory() as temp:
        for folder in inputs:
            for entry in json.loads((folder / "candidates.json").read_text()):
                name = entry["name"]
                payload = (folder / f"{name}.coded").read_bytes()
                if len(payload) != entry["stream"]:
                    raise ValueError(f"unexpected stream size for {name}")
                for flag in ("-Os", "-Oz"):
                    cfg = dict(entry["model"], optimization=flag)
                    image = linked_image(cfg, payload, Path(temp))
                    trials.append((len(image), name, flag, len(payload), cfg))
    trials.sort(key=lambda row: row[:3])
    total, name, flag, _, best = trials[0]
    fields = ("masks", "region_shift", "bit_shift", "prior", "dynamics", "branches", "weights", "optimization")
    best = {key: best[key] for key in fields if key in best}
    dest.mkdir(parents=True, exist_ok=False)
    (dest / "policy.json").write_text(json.dumps(best, indent=2) + "\n")
    with (dest / "model-search.tsv").open("w") as f:
        f.write("candidate\tcompiler\tcoded_bytes\tstartup_bytes\n")
        for size, trial, opt, coded, _ in trials:
            f.write(f"{trial}\t{opt}\t{coded}\t{size}\n")
    print(f"{len(trials)} linked candidates. Selected {name} {flag}, {total} bytes.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("initial", type=Path)
    p.add_argument("counter_sweep", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    select([args.initial, args.counter_sweep], args.output)
