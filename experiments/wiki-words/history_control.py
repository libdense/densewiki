#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Hold DWX3's exact transformed bytes and one-MiB XZ dictionary constant."""
import argparse
import hashlib
import json
import lzma
from pathlib import Path
import struct
import zipfile

from decoder import HEADER, read_exact

FILTERS = [{"id": lzma.FILTER_LZMA2, "dict_size": 1 << 20, "lc": 4, "lp": 0, "pb": 0,
            "mode": lzma.MODE_NORMAL, "nice_len": 192, "mf": lzma.MF_BT4}]


def vint(data, p):
    value = 0
    for shift in range(0, 63, 7):
        b = data[p]
        p += 1
        value |= (b & 127) << shift
        if b < 128:
            return value, p
    raise ValueError("invalid XZ index")


def raw_member(member):
    if member[:6] != bytes.fromhex("fd377a585a00") or member[-2:] != b"YZ" or member[7] != 4:
        raise ValueError("expected XZ with CRC64")
    size = 4 * (1 + struct.unpack_from("<I", member, len(member) - 8)[0])
    index = member[-12-size:-12]
    if index[:2] != bytes((0,1)):
        raise ValueError("expected one XZ block")
    unpadded, _ = vint(index, 2)
    header = 4 * (1 + member[12])
    return member[12+header:12+unpadded-8]


def run(path):
    sha = hashlib.sha256()
    verified = hashlib.sha256()
    reset = continuous = transformed = blocks = total = 0
    enc = lzma.LZMACompressor(format=lzma.FORMAT_RAW, filters=FILTERS)
    dec = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=FILTERS)
    with zipfile.ZipFile(path) as pkg, pkg.open("payload") as source:
        if read_exact(source, 4) != b"DWX3":
            raise ValueError("expected DWX3 standalone archive")
        while (mark := read_exact(source, 1)) != b"\xff":
            mode, raw_size, n, _ = HEADER.unpack(mark + read_exact(source, HEADER.size-1))
            if mode != 3 or raw_size < 1 << 19:
                raise ValueError("this control requires the full enwik9 fixed-mode member geometry")
            member = read_exact(source, n)
            pre = lzma.decompress(member)
            coded = raw_member(member)
            if lzma.decompress(coded, format=lzma.FORMAT_RAW, filters=FILTERS) != pre:
                raise ValueError("independent raw LZMA2 member differs")
            reset += len(coded)
            total += raw_size
            transformed += len(pre)
            sha.update(pre)
            chunk = enc.compress(pre)
            continuous += len(chunk)
            verified.update(dec.decompress(chunk))
            blocks += 1
        tail = enc.flush()
        continuous += len(tail)
        verified.update(dec.decompress(tail))
        if not dec.eof or dec.unused_data or verified.digest() != sha.digest() or source.read(1):
            raise ValueError("continuous LZMA2 round trip failed")
    return dict(raw_input_bytes=total, transformed_bytes=transformed, blocks=blocks,
                transformed_sha256=sha.hexdigest(), continuous_restored_sha256=verified.hexdigest(),
                independent_raw_lzma2_bytes=reset, continuous_raw_lzma2_bytes=continuous,
                excluded="XZ and DWX3 framing. The totals contain only the LZMA2 members.",
                dict_bytes=1 << 20)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dwx3_standalone", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.dwx3_standalone), indent=2))
