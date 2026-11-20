#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Stream a reversible vocabulary transform over arbitrary bytes, including raw enwik9."""
import argparse
from collections import Counter, defaultdict
import lzma
from pathlib import Path
import re
import sys
import tempfile
import os
import zlib

from decoder import BLOCK, HEADER, MAGIC, MAX_WORDS, decode

WORD = re.compile(rb"[A-Za-z]+")
ESCAPE = re.compile(rb"[\x7f-\xff]")


def uint(value):
    out = bytearray()
    while value >= 128:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


def reference(i):
    if i < 96:
        return bytes([128 + i])
    i -= 96
    if i < 31 * 256:
        return bytes([224 + i // 256, i % 256])
    return b"\xff" + uint(i - 31 * 256)


def dictionary_stream(data, threshold=32, layout="lexical"):
    counts = Counter(m[0] for m in WORD.finditer(data) if 3 <= m.end() - m.start() <= 64)
    words = sorted((w for w, n in counts.items() if (n - 1) * (len(w) - 2) > threshold),
                   key=lambda w: (-counts[w], w))[:MAX_WORDS]
    if layout == "lexical":
        # Keep the cheapest 96 references, then put related spellings next to each other.
        words = sorted(words[:96]) + sorted(words[96:])
    elif layout == "predecessor":
        chosen = set(words)
        edges = defaultdict(Counter)
        prev = None
        for token in WORD.finditer(data):
            current = token[0]
            if current in chosen and prev is not None:
                edges[current][prev] += 1
            prev = current if current in chosen else None
        def neighborhood(w):
            incoming = edges[w]
            parent = min(incoming, key=lambda k: (-incoming[k], k)) if incoming else b""
            return parent, w
        words = sorted(words[:96], key=neighborhood) + sorted(words[96:], key=neighborhood)
    elif layout != "frequency":
        raise ValueError("unknown word layout")
    codes = {word: reference(i) for i, word in enumerate(words)}
    buf = bytearray(uint(len(words)))
    for word in words:
        buf.extend(word + b"\n")
    mark = 0
    def literal(match):
        return b"\x7f" + match[0]
    for match in WORD.finditer(data):
        ref = codes.get(match[0])
        if ref is not None:
            buf.extend(ESCAPE.sub(literal, data[mark:match.start()]))
            buf.extend(ref)
            mark = match.end()
    buf.extend(ESCAPE.sub(literal, data[mark:]))
    return buf


def encode(source, dest, mode="auto", threshold=32, layout="lexical"):
    dest.write(MAGIC)
    raw_blocks = shared_blocks = 0
    while data := source.read(BLOCK):
        choices = []
        if mode != "words":
            choices.append((0, lzma.compress(data, preset=6)))
        if mode != "raw":
            choices.append((1, lzma.compress(dictionary_stream(data, threshold, layout), preset=6)))
        flag, payload = min(choices, key=lambda item: (len(item[1]), item[0]))
        dest.write(HEADER.pack(flag, len(data), len(payload), zlib.crc32(data)))
        dest.write(payload)
        raw_blocks += flag == 0
        shared_blocks += flag == 1
    dest.write(b"\xff")
    return {"raw_blocks": raw_blocks, "dictionary_blocks": shared_blocks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("encode", "decode"))
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--mode", choices=("auto", "raw", "words"), default="auto")
    args = parser.parse_args()
    # Publish only a fully written file, and preserve an existing output on failure.
    with args.source.open("rb") as source, tempfile.NamedTemporaryFile(dir=args.output.parent) as out:
        if args.operation == "encode":
            stats = encode(source, out, args.mode)
            print(f"{stats['raw_blocks']} raw blocks, {stats['dictionary_blocks']} dictionary blocks", file=sys.stderr)
        else:
            decode(source, out)
        out.flush()
        os.link(out.name, args.output)


if __name__ == "__main__":
    main()
