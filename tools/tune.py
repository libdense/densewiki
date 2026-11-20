#!/usr/bin/env python3
"""Fit a second-stage shortlist, then score the actual linked startup block."""
import argparse
import concurrent.futures
import itertools
import json
import subprocess
import tempfile
from pathlib import Path
from build import ORIGINAL, branch_transform, encode_policy, linked_image
from fit import fit_weights
import numpy as np


def tune(mix, flat, work):
    raw = flat.read_bytes()
    variants = [raw, branch_transform(raw)]
    paths = [work / "plain", work / "relative-targets"]
    for path, data in zip(paths, variants):
        path.write_bytes(data)
    sequence = list(itertools.product((False, True), (15, 31, 63, 127, 255),
                                      (1, 2, 4, 8, 16), (1, 2, 3), (0, 1)))
    def screen(record):
        index, (branch, cap, boost, decay, keep) = record
        config = dict(ORIGINAL, dynamics=[cap, boost, decay, keep], branches=branch)
        policy = work / f"screen-{index}.policy"
        stream = work / f"screen-{index}.coded"
        policy.write_bytes(encode_policy(config))
        subprocess.run([mix, "encode", policy, paths[int(branch)], stream], check=True)
        return stream.stat().st_size, index, config
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as exe:
        screened = sorted(exe.map(screen, enumerate(sequence)), key=lambda x: (x[0], x[1]))
    shortlist = []
    for branch in (False, True):
        shortlist += [s for s in screened if s[2]["branches"] == branch][:12]
    code = [(n, f"screen-{i}", m) for n,i,m in screened]
    for _, i, config in shortlist:
        branch = int(config["branches"])
        trace = work / f"trace-{i}"
        subprocess.run([mix, "trace", work / f"screen-{i}.policy", paths[branch], trace], check=True)
        counts = np.fromfile(trace, dtype="<u2").reshape(-1, 9, 2)
        bits = np.unpackbits(np.frombuffer(variants[branch], dtype=np.uint8))
        total = counts.astype(np.float64).sum(axis=2)
        hit = np.where(bits[:,None], counts[:,:,1], counts[:,:,0]).astype(np.float64)
        for bit_shift in (2, 3):
            groups = (np.arange(len(bits)) % 8) >> bit_shift
            for prior in (6, 16, 40):
                weight = [fit_weights(hit[groups == g], total[groups == g], prior)
                          for g in range(8 >> bit_shift)]
                cfg = dict(config, prior=prior, bit_shift=bit_shift, weights=weight)
                name = f"fit-{i}-{bit_shift}-{prior}"
                pol, dst = work / (name + ".policy"), work / (name + ".coded")
                pol.write_bytes(encode_policy(cfg))
                subprocess.run([mix, "encode", pol, paths[branch], dst], check=True)
                code.append((dst.stat().st_size, name, cfg))
        trace.unlink()
    candidates = [{"name": name, "model": model, "stream": count} for count, name, model in code]
    (work / "candidates.json").write_text(json.dumps(candidates, indent=2) + "\n")
    ranking = []
    with tempfile.TemporaryDirectory() as folder:
        for n, name, cfg in code:
            head = linked_image(cfg, (work / (name+".coded")).read_bytes(), Path(folder))
            ranking.append((len(head), name, n, cfg))
    ranking.sort(key=lambda x: (x[0], x[1]))
    (work / "ranked.tsv").write_text("candidate\tcoded_bytes\tcomplete_head_bytes\n" +
                                   "".join(f"{name}\t{n}\t{s}\n" for s,name,n,_ in ranking))
    (work / "winner.json").write_text(json.dumps(ranking[0][3], indent=2) + "\n")
    print(f"Scored {len(ranking)} linked models. Best head {ranking[0][0]} bytes ({ranking[0][1]}).")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mix", type=Path)
    p.add_argument("raw", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    tune(a.mix.resolve(), a.raw.resolve(), a.output.resolve())
