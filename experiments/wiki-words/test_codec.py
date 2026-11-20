import io
import lzma
import random
import unittest

from codec import BLOCK, dictionary_stream, encode, reference, uint
from decoder import decode, expand
from wiki3 import encode_v3, fold_case, group_fields
from wiki3_decoder import CLOSE_TEXT, OPEN_TEXT, decode as decode_v3, restore_case, restore_fields


class CodecTest(unittest.TestCase):
    def test_reference_boundaries(self):
        for rank in (0, 95, 96, 97, 8031, 8032, 8192):
            entries = b"abc\n" * rank + b"last\n"
            packed = uint(rank + 1) + entries + reference(rank)
            self.assertEqual(expand(packed, 4), b"last")

    def test_literal_and_dictionary(self):
        raw = bytes(range(256)) + (b"[[World|world]] and Wiki\x00\x7f\xff\n" * 100) + b"A" * 101
        for layout in ("frequency", "lexical"):
            self.assertEqual(expand(dictionary_stream(raw, 0, layout), len(raw)), raw)

    def test_stream_boundaries(self):
        for sample in (b"", b"x", b"Wikipedia articles " * (BLOCK // 19 + 2),
                       random.Random(9).randbytes(8192)):
            stream = io.BytesIO()
            encode(io.BytesIO(sample), stream)
            stream.seek(0)
            restored = io.BytesIO()
            decode(stream, restored)
            self.assertEqual(sample, restored.getvalue())

    def test_v3_reversible_layers(self):
        samples = [bytes(range(256)), b"New YORK and eBay XYZ bZ aX AbC aA",
                   b"alpha\x04Beta\x05USA\x06Gamma", OPEN_TEXT + CLOSE_TEXT,
                   b"before" + OPEN_TEXT + b"first" + OPEN_TEXT + b"nested" + CLOSE_TEXT +
                   b"between" + OPEN_TEXT + CLOSE_TEXT + OPEN_TEXT + b"incomplete"]
        for raw in samples:
            self.assertEqual(restore_case(fold_case(raw)), raw)
            self.assertEqual(restore_fields(group_fields(raw)), raw)
            for mode in range(5):
                packed, restored = io.BytesIO(), io.BytesIO()
                encode_v3(io.BytesIO(raw), packed, (mode,))
                packed.seek(0)
                decode_v3(packed, restored)
                self.assertEqual(restored.getvalue(), raw)

    def test_v3_block_boundaries_and_damage(self):
        raw = b"X" * (BLOCK - 9) + OPEN_TEXT + b"Mixed CASE" + CLOSE_TEXT
        packed, restored = io.BytesIO(), io.BytesIO()
        encode_v3(io.BytesIO(raw), packed)
        packed.seek(0)
        decode_v3(packed, restored)
        self.assertEqual(restored.getvalue(), raw)
        frame = packed.getvalue()
        for broken in (frame[:-1], frame + b"!", frame[:4] + b"\x07" + frame[5:],
                       frame[:12] + bytes([frame[12] ^ 64]) + frame[13:]):
            with self.assertRaises((ValueError, lzma.LZMAError)):
                decode_v3(io.BytesIO(broken), io.BytesIO())
        for escaped in (b"abc\x04", b"\x05X", b"\x06!", b"\x04x"):
            with self.assertRaises(ValueError):
                restore_case(escaped)
        for grouped in (b"\x01\x00", b"\x00\x00X", b"\x00\x07"):
            with self.assertRaises(ValueError):
                restore_fields(grouped)

    def test_invalid_stream(self):
        stream = io.BytesIO()
        encode(io.BytesIO(b"Wikipedia"), stream)
        valid = stream.getvalue()
        for broken in (valid[:-1], valid + b"!", valid[:10], valid[:13] + bytes([valid[13] ^ 1]) + valid[14:]):
            with self.assertRaises(ValueError):
                decode(io.BytesIO(broken), io.BytesIO())
        for malformed in (b"\x00\x80", b"\x00\x7f", b"\x00\xe0", b"\xff\xff\xff"):
            with self.assertRaises(ValueError):
                expand(malformed, 2)


if __name__ == "__main__":
    unittest.main()
