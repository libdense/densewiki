#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build DWX2 and DWX3 corpus streams and compare both fresh decodes byte for byte."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import io
import json
from pathlib import Path
import time
import zlib

from codec import encode
from decoder import BLOCK, HEADER, MAGIC, decode
from full_corpus import CompareOutput, ENWIK9, fingerprint
from wiki3 import encode_v3
from wiki3_decoder import MAGIC3, decode as decode_v3


def encode_block(source, index):
    with source.open("rb") as src:
        src.seek(index * BLOCK)
        data = src.read(BLOCK)
    frames = []
    for writer, magic in ((encode, MAGIC), (encode_v3, MAGIC3)):
        temp = io.BytesIO()
        writer(io.BytesIO(data), temp)
        packet = temp.getvalue()
        if packet[:4] != magic or packet[-1:] != b"\xff":
            raise ValueError("invalid single-block framing")
        frames.append(packet[4:-1])
    return frames


def read_frame(stream, mode_limit):
    header = stream.read(HEADER.size)
    if len(header) != HEADER.size:
        return None
    mode, size, packed, crc = HEADER.unpack(header)
    if mode > mode_limit or not 0 < size <= BLOCK or not 0 < packed <= 5 * BLOCK:
        return None
    data = stream.read(packed)
    return (header + data, size, crc) if len(data) == packed else None


def recover(source, directory, outputs, counts, modes):
    with (directory / "DWX2.dwx").open("rb") as a, (directory / "DWX3.dwx").open("rb") as b, source.open("rb") as raw:
        if a.read(4) != MAGIC or b.read(4) != MAGIC3:
            raise ValueError("checkpoint format differs")
        for i in range(counts):
            pair = read_frame(a, 1), read_frame(b, 4)
            if any(frame is None for frame in pair):
                return i
            block = raw.read(BLOCK)
            identity = len(block), zlib.crc32(block)
            for j, frame in enumerate(pair):
                packet, size, crc = frame
                if (size, crc) != identity:
                    raise ValueError("checkpoint belongs to different source bytes")
                outputs[j].write(packet)
                modes[j][packet[0]] += 1
    return counts


def verify(source, dest, workers, resume_from=None):
    if workers < 1:
        raise ValueError("worker count must be positive")
    size = source.stat().st_size
    identity = fingerprint(source)
    dest.mkdir()
    paths = {name: dest / (name + ".dwx") for name in ("DWX2", "DWX3")}
    counts = (0 if size == 0 else (size + BLOCK - 1) // BLOCK)
    modes = [[0] * 2, [0] * 5]
    start = time.monotonic()
    with ProcessPoolExecutor(max_workers=workers) as pool, paths["DWX2"].open("xb") as a, paths["DWX3"].open("xb") as b:
        a.write(MAGIC)
        b.write(MAGIC3)
        pending = {}
        start_block = recover(source, resume_from, (a, b), counts, modes) if resume_from else 0
        print(f"Starting at block {start_block + 1} of {counts}", flush=True)
        for i in range(start_block, min(start_block + workers, counts)):
            pending[i] = pool.submit(encode_block, source, i)
        for i in range(start_block, counts):
            first, second = pending.pop(i).result()
            following = i + workers
            if following < counts:
                pending[following] = pool.submit(encode_block, source, following)
            a.write(first)
            b.write(second)
            modes[0][first[0]] += 1
            modes[1][second[0]] += 1
            if (i + 1) % 50 == 0:
                print(f"Encoded {i + 1}/{counts} blocks", flush=True)
        a.write(b"\xff")
        b.write(b"\xff")
    report = dict(input_bytes=size, input_sha256=identity, canonical_enwik9=(identity == ENWIK9),
                  block_bytes=BLOCK, blocks=counts, encoding_workers=workers, recovered_blocks=start_block,
                  combined_encode_wall_seconds=round(time.monotonic()-start, 3), profiles={})
    for j, (name, reader) in enumerate((("DWX2", decode), ("DWX3", decode_v3))):
        archive = paths[name]
        begin = time.monotonic()
        with source.open("rb") as expected, archive.open("rb") as data:
            sink = CompareOutput(expected)
            reader(data, sink)
            if expected.read(1) or sink.total != size or sink.hash.hexdigest() != identity:
                raise ValueError(f"{name} failed full corpus verification")
        report["profiles"][name] = dict(stream_bytes=archive.stat().st_size, sha256=fingerprint(archive),
            restored_sha256=sink.hash.hexdigest(), restored_bytes=sink.total, byte_comparison="equal",
            blocks_by_mode=modes[j], decode_compare_seconds=round(time.monotonic()-begin, 3))
    (dest / "verified.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Verified {size} source bytes against each archive", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path)
    p.add_argument("output", type=Path, help="fresh output directory")
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--resume-from", type=Path, help="copy complete matching blocks from an interrupted run")
    args = p.parse_args()
    verify(args.input.resolve(), args.output, args.workers, args.resume_from)
