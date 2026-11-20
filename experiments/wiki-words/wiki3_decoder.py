# SPDX-License-Identifier: GPL-3.0-only
"""Read bounded DWX3 blocks and invert capitalization and article-field grouping."""
import lzma
import zlib

from decoder import BLOCK, HEADER, expand, read_exact, varint

MAGIC3 = b"DWX3"
OPEN_TEXT = b'<text xml:space="preserve">'
CLOSE_TEXT = b"</text>"


def restore_case(data):
    out = bytearray()
    start = 0
    i = 0
    while i < len(data):
        marker = data[i]
        if not 4 <= marker <= 6:
            i += 1
            continue
        out.extend(data[start:i])
        i += 1
        if i == len(data):
            raise ValueError("truncated capitalization escape")
        if marker == 4:
            if not 4 <= data[i] <= 6:
                raise ValueError("invalid escaped control")
            out.append(data[i])
            i += 1
        else:
            end = i
            while end < len(data) and 97 <= data[end] <= 122:
                end += 1
            if end == i:
                raise ValueError("missing lowercase word")
            word = data[i:end]
            out.extend(word.capitalize() if marker == 5 else word.upper())
            i = end
        start = i
    out.extend(data[start:])
    return out


def restore_fields(data):
    count, offset = varint(data, 0)
    length, offset = varint(data, offset)
    body = offset + length
    if body > len(data):
        raise ValueError("metadata ends outside the block")
    meta = data[offset:body]
    pos = 0
    out = bytearray()
    for _ in range(count):
        tag = meta.find(OPEN_TEXT, pos)
        stop = data.find(CLOSE_TEXT, body)
        if tag < 0 or stop < 0:
            raise ValueError("unpaired text field")
        tag += len(OPEN_TEXT)
        stop += len(CLOSE_TEXT)
        out.extend(meta[pos:tag])
        out.extend(data[body:stop])
        pos, body = tag, stop
    if body != len(data):
        raise ValueError("unconsumed text field bytes")
    out.extend(meta[pos:])
    return out


def decode(source, dest):
    if read_exact(source, 4) != MAGIC3:
        raise ValueError("unknown DWX3 stream")
    while True:
        mark = read_exact(source, 1)
        if mark == b"\xff":
            if source.read(1):
                raise ValueError("unexpected bytes after DWX3 end")
            return
        mode, size, packed, crc = HEADER.unpack(mark + read_exact(source, HEADER.size - 1))
        if mode > 4 or not 0 < size <= BLOCK or not 0 < packed <= 5 * BLOCK:
            raise ValueError("invalid DWX3 block")
        coder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=16 << 20)
        data = coder.decompress(read_exact(source, packed), max_length=5 * BLOCK + 1)
        if not coder.eof or coder.unused_data or len(data) > 5 * BLOCK:
            raise ValueError("invalid DWX3 XZ member")
        if mode:
            data = expand(data, 2 * size + 8)
        if mode in (2, 3):
            data = restore_case(data)
        if mode in (3, 4):
            data = restore_fields(data)
        if len(data) != size or zlib.crc32(data) != crc:
            raise ValueError("DWX3 block checksum or size mismatch")
        dest.write(data)
