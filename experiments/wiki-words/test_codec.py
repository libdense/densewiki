import io
import random
import unittest

from codec import BLOCK, dictionary_stream, encode, reference, uint
from decoder import decode, expand


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
