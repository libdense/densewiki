#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure the native model on a reversible excerpt of the bundled Wikipedia fixture."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "tools"))
from prepare_experiment import prepare


def sha(data):
    return hashlib.sha256(data).hexdigest()


def replace_once(path, old, new):
    source = path.read_text()
    if source.count(old) != 1:
        raise ValueError(f"could not locate unique probe insertion in {path}")
    path.write_text(source.replace(old, new))


def build_model(arm, work, jobs):
    tree = work / arm
    prepare(arm, tree)
    replace_once(tree / "src/enc_only.h", 'noinline, section(".text.enc_only")', "noinline")
    replace_once(tree / "makefile", "-c src/predictor.cpp\n",
                 "-c src/predictor.cpp\n\t$(CC) $(CPPFLAGS_PART-THAT-SHOULD-BE-FAST) "
                 "-fno-fast-math -ffp-contract=off -c src/mixer/mixer-input.cpp\n")
    # The excerpt starts in article text, downstream of the full-corpus metadata preamble.
    replace_once(tree / "src/tf1/tf1_gate.cpp", "  r_anker_.Init(kAnker, 8);",
                 "  mf_raus_ = true;\n  st_state_ = kBody;\n  r_anker_.Init(kAnker, 8);")
    replace_once(tree / "src/predictor.h", " private:\n",
                 "  unsigned long long DenseInsertions() const { return sem_.nins; }\n"
                 "  unsigned long long DensePositions() const { return sem_.spos; }\n private:\n")
    entry = "int main(int argc, char** argv) {"
    replace_once(tree / "src/runner.cpp", entry,
                 (HERE / "stream_probe.inc").read_text() + "\n" + entry +
                 '\n  if (argc > 1 && (!strcmp(argv[1], "encode-stream") || !strcmp(argv[1], "decode-stream"))) '
                 "return DenseStreamTest(argc, argv);")
    with (work / f"{arm}-build.log").open("wb") as log:
        subprocess.run(["make", f"-j{jobs}", "CC=" + str(HERE / "gcc-bench"), "cmix"],
                       cwd=tree, stdout=log, stderr=subprocess.STDOUT, check=True)
    return tree


def read_excerpt(tree, offset, size):
    fixture = tree / "prof_input/input2"
    if offset < 0 or size < 1 or offset + size > fixture.stat().st_size:
        raise ValueError("requested range lies outside the profiling fixture")
    raw = fixture.read_bytes()[offset:offset + size]
    table = (tree / "src/vocab_frozen.h").read_text().split("kBitmap[32] = {")[1].split("}")[0]
    bitmap = bytes(int(s, 16) for s in re.findall(r"0x[\da-fA-F]+", table))
    coded = bytearray()
    for byte in raw:
        if byte != 255 and bitmap[byte >> 3] & (1 << (byte & 7)):
            coded.append(byte)
        else:
            coded.extend((255, 128 + (byte >> 4), 128 + (byte & 15)))
    return raw, bytes(coded), sha(fixture.read_bytes())


def unescape(data):
    out = bytearray()
    source = iter(data)
    for byte in source:
        if byte == 255:
            hi, lo = next(source), next(source)
            if not (128 <= hi < 144 and 128 <= lo < 144):
                raise ValueError("invalid escaped nibble")
            byte = (hi - 128) * 16 + lo - 128
        out.append(byte)
    return bytes(out)


def run_model(tree, mode, source, n, run_dir, cpu):
    run_dir.mkdir()
    weight, = tree.glob("weights-*.c5")
    (run_dir / weight.name).symlink_to(weight)
    output = run_dir / "output"
    start = time.monotonic()
    log = run_dir / "run.log"
    with log.open("wb") as stream:
        child = subprocess.Popen([tree / "cmix", mode + "-stream", str(n), source, output],
                                 cwd=run_dir, stdout=stream, stderr=subprocess.STDOUT,
                                 preexec_fn=lambda: os.sched_setaffinity(0, {cpu}))
        _, status, usage = os.wait4(child.pid, 0)
        child.returncode = os.waitstatus_to_exitcode(status)
    if child.returncode:
        raise RuntimeError(f"{mode} failed with status {child.returncode}. See {log}")
    observations = re.search(rb"DENSE_OBSERVATIONS (\d+) (\d+)", log.read_bytes())
    if not observations:
        raise ValueError(f"missing observation counts in {log}")
    record = dict(peak_rss_kib=usage.ru_maxrss, wall_seconds=round(time.monotonic()-start, 3),
                  output_bytes=output.stat().st_size, output_sha256=sha(output.read_bytes()),
                  semantic_insertions=int(observations[1]), semantic_positions=int(observations[2]))
    (run_dir / "result.json").write_text(json.dumps(record, indent=2) + "\n")
    return output, record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workdir", type=Path, help="new build and run directory")
    parser.add_argument("--offset", type=int, default=87537)
    parser.add_argument("--sizes", type=int, nargs="+", default=[16384, 32768])
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    work = args.workdir.resolve()
    work.mkdir()
    cpu = min(os.sched_getaffinity(0))
    models = {key: build_model(arm, work, args.jobs) for key, arm in
              (("baseline", "prize-original"), ("lowmem", "prize-lowmem"))}
    receipt = dict(platform=platform.platform(), compiler=subprocess.check_output(["g++", "-dumpfullversion"], text=True).strip(),
                   units="Linux wait4 ru_maxrss, KiB per fresh process", offset=args.offset, trials=[])
    for size in args.sizes:
        row = trial(models, work, args.offset, size, cpu)
        receipt["trials"].append(row)
        (work / "result.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(f"Verified both encoders and both cross-decodes on {size} source bytes", flush=True)


def trial(models, work, offset, size, cpu):
    folder = work / f"excerpt-{size}"
    folder.mkdir()
    raw, escaped, source_hash = read_excerpt(models["baseline"], offset, size)
    src = folder / "stream"
    src.write_bytes(escaped)
    row = dict(raw_bytes=size, raw_sha256=sha(raw), stream_bytes=len(escaped), stream_sha256=sha(escaped),
               source_file="prof_input/input2", source_sha256=source_hash, runs={})
    files = {}
    for key, tree in models.items():
        files[key], row["runs"][key + "_encode"] = run_model(tree, "encode", src, len(escaped), folder/(key+"-encode"), cpu)
    if files["baseline"].read_bytes() != files["lowmem"].read_bytes():
        raise ValueError("encoded streams differ")
    for key, peer in (("baseline", "lowmem"), ("lowmem", "baseline")):
        output, row["runs"][key + "_cross_decode"] = run_model(
            models[key], "decode", files[peer], len(escaped), folder/(key+"-decode"), cpu)
        restored = output.read_bytes()
        if restored != escaped or unescape(restored) != raw:
            raise ValueError(f"{key} cross-decode did not restore the source bytes")
    observations = {(run["semantic_insertions"], run["semantic_positions"]) for run in row["runs"].values()}
    if len(observations) != 1 or next(iter(observations))[0] == 0:
        raise ValueError("live semantic-cache paths were not exercised consistently")
    row["encoded_equal"] = True
    row["both_cross_decodes_match_raw_xml"] = True
    return row


if __name__ == "__main__":
    main()
