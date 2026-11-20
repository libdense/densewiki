#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compress arbitrary bytes in independent blocks with a bounded XZ dictionary."""
import lzma
import re
import zlib

from codec import dictionary_stream, uint
from decoder import BLOCK, HEADER
from wiki3_decoder import CLOSE_TEXT, MAGIC3, OPEN_TEXT

TOKENS = re.compile(rb"[A-Za-z]+|[\x04-\x06]")


def fold_case(data):
    out = bytearray()
    start = 0
    for match in TOKENS.finditer(data):
        word = match[0]
        if word[0] in (4, 5, 6):
            folded = b"\x04" + word
        elif len(word) > 1 and word.isupper():
            folded = b"\x06" + word.lower()
        elif 65 <= word[0] <= 90 and word[1:] == word[1:].lower():
            folded = b"\x05" + word.lower()
        else:
            continue
        out.extend(data[start:match.start()])
        out.extend(folded)
        start = match.end()
    out.extend(data[start:])
    return out


def group_fields(data):
    pos = count = 0
    meta = bytearray()
    bodies = bytearray()
    while True:
        tag = data.find(OPEN_TEXT, pos)
        if tag < 0:
            break
        tag += len(OPEN_TEXT)
        stop = data.find(CLOSE_TEXT, tag)
        if stop < 0:
            break
        stop += len(CLOSE_TEXT)
        meta.extend(data[pos:tag])
        bodies.extend(data[tag:stop])
        count += 1
        pos = stop
    meta.extend(data[pos:])
    return uint(count) + uint(len(meta)) + meta + bodies


def pack(data, dictionary, contexts):
    filters = [dict(id=lzma.FILTER_LZMA2, dict_size=dictionary, lc=contexts, lp=0, pb=0,
                    mode=lzma.MODE_NORMAL, nice_len=192, mf=lzma.MF_BT4)]
    return lzma.compress(data, filters=filters)


def encode_v3(source, dest, modes=(0, 1, 3)):
    dest.write(MAGIC3)
    selected = [0] * 5
    while data := source.read(BLOCK):
        dictionary = max(4096, min(BLOCK, 1 << (len(data)-1).bit_length()))
        short = len(data) < 1 << 17
        threshold = 40 if short else 24
        contexts = 3 if short else 4
        best = None
        for mode in modes:
            if mode not in (0, 1, 2, 3, 4):
                raise ValueError("invalid block mode")
            transformed = group_fields(data) if mode in (3, 4) else data
            if mode in (2, 3):
                transformed = fold_case(transformed)
            if mode:
                transformed = dictionary_stream(transformed, threshold)
            payload = pack(transformed, dictionary, contexts)
            if best is None or len(payload) < len(best[1]):
                best = mode, payload
        if best is None:
            raise ValueError("at least one mode is required")
        flag, payload = best
        selected[flag] += 1
        dest.write(HEADER.pack(flag, len(data), len(payload), zlib.crc32(data)))
        dest.write(payload)
    dest.write(b"\xff")
    return dict(blocks_by_mode=selected)
