# SPDX-License-Identifier: GPL-3.0-only
"""Decode the DWX2 block format using the Python standard library."""
import lzma
import struct
import zlib

MAGIC = b"DWX2"
BLOCK = 1 << 20
HEADER = struct.Struct("<BIII")
MAX_WORDS = 65536


def read_exact(stream, size):
    data = stream.read(size)
    if len(data) != size:
        raise ValueError("truncated DWX2 stream")
    return data


def varint(buf, pos):
    value = 0
    for shift in (0, 7, 14):
        if pos == len(buf):
            raise ValueError("truncated word index")
        byte = buf[pos]
        pos += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, pos
    raise ValueError("oversized word index")


def expand(buf, expected):
    count, pos = varint(buf, 0)
    if count > MAX_WORDS:
        raise ValueError("oversized vocabulary")
    words = []
    for _ in range(count):
        end = buf.find(b"\n", pos, pos + 65)
        if end < 0 or not buf[pos:end].isalpha():
            raise ValueError("invalid dictionary entry")
        words.append(buf[pos:end])
        pos = end + 1
    out = bytearray()
    while pos < len(buf):
        code = buf[pos]
        pos += 1
        if code < 127:
            out.append(code)
        elif code == 127:
            if pos == len(buf) or buf[pos] < 127:
                raise ValueError("invalid literal escape")
            out.append(buf[pos])
            pos += 1
        else:
            if code < 224:
                rank = code - 128
            elif code < 255:
                if pos == len(buf):
                    raise ValueError("truncated two-byte reference")
                rank = 96 + (code - 224) * 256 + buf[pos]
                pos += 1
            else:
                extra, pos = varint(buf, pos)
                rank = 96 + 31 * 256 + extra
            if rank >= len(words):
                raise ValueError("reference outside vocabulary")
            out.extend(words[rank])
        if len(out) > expected:
            raise ValueError("decoded block exceeds its declared size")
    return out


def decode(source, dest):
    if read_exact(source, 4) != MAGIC:
        raise ValueError("unknown stream format")
    while True:
        flag = read_exact(source, 1)
        if flag == b"\xff":
            if source.read(1):
                raise ValueError("unexpected data after DWX2 end")
            return
        mode, size, packed, crc = HEADER.unpack(flag + read_exact(source, HEADER.size - 1))
        if mode > 1 or not 0 < size <= BLOCK or not 0 < packed <= 5 * BLOCK:
            raise ValueError("invalid DWX2 block header")
        unpacker = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=128 << 20)
        data = unpacker.decompress(read_exact(source, packed), max_length=4 * BLOCK + 1)
        if not unpacker.eof or unpacker.unused_data or len(data) > 4 * BLOCK:
            raise ValueError("invalid XZ member")
        raw = expand(data, size) if mode else data
        if len(raw) != size or zlib.crc32(raw) != crc:
            raise ValueError("incorrect block length or checksum")
        dest.write(raw)
