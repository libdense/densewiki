#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Exercise the startup transform near signed wrap and truncated operands."""
from pathlib import Path
import random
import struct
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "tools"))
from build import FLAT_HASH, digest, relative27

image = (root / "experiments/startup.bin").read_bytes()
assert digest(relative27(relative27(image), inverse=True)) == FLAT_HASH
rng = random.Random(19)
inputs = [rng.randbytes(n) for n in (0, 1, 4, 5, 6, 1024, 12311, 32000)]
for prefix in (b"\xe8", b"\xe9", b"\x8b\x05", b"\x89\x3d", b"\x8b\xc0"):
    for v in (0, 1, (1 << 26)-1, 1 << 26, -(1 << 26), -(1 << 26)-1, -1):
        test = b"\x00"*3 + prefix + struct.pack("<I", v & 0xffffffff)
        inputs.extend(test[:i] for i in range(len(test)+1))
for sample in inputs:
    if relative27(relative27(sample), inverse=True) != sample:
        raise AssertionError("relative operand transform mismatch")
print(f"Native startup image and {len(inputs)} short inputs restored")
