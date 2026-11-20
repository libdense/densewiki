#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Exercise the public CLI, executable archive and format boundaries."""
import argparse
import hashlib
from pathlib import Path
import random
import subprocess
import tempfile


def execute(args, success=True):
    p = subprocess.run(args, capture_output=True)
    if (p.returncode == 0) != success:
        raise RuntimeError(f"{args}: {p.returncode}: {p.stderr[-500:]!r}")


def main(binary):
    rng = random.Random(48531)
    page = (b"  <page>\n    <title>Lake Example (river)</title>\n    <id>04321</id>\n"
            b"      <text xml:space=\"preserve\">Lake Example flows into [[Lake Example (river)]].\n"
            b"An example includes the LAKE and lake Example in 000.01, 2,402 and 7 households.\n"
            b"Values 003,500.00 and 0.75 for the district.\nValues 7 and 99.000 for the district.\n"
            b"[[Category:Rivers]]\n[[fr:Lake Example]]</text>\n  </page>\n")
    fixtures = [b"", b"x", bytes(range(256))*3, rng.randbytes(18017),
                b"  <page>\n    <title>Ab\x10c</title>\nAb\x10c\n  </page>",
                b"x"*(2**20-9)+b"  <page>\n" + page*23 + b"partial\x00",
                page*81 + b"\n".join(f"row {i:08}, cost {i/100:.2f} each".encode() for i in range(5100)),
                b"\n"*(2**18+2), b"\x1b"*(2**18+3), b"z"*(2**20+257)]
    modes = ["raw", "words", "fields", "templates", "topics", "titles", "wiki", "lean"]
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        for j, data in enumerate(fixtures):
            source = folder / f"source-{j}"
            source.write_bytes(data)
            for mode in modes:
                packed = folder / f"{j}-{mode}"
                result = folder / f"{j}-{mode}.back"
                execute([binary, "encode", source, packed, mode])
                execute([binary, "decode", packed, result])
                if result.read_bytes() != data:
                    raise AssertionError(f"round trip {j}/{mode}")
            if j == 6:
                one = folder / f"{j}-wiki"
                same = folder / "repeat"
                execute([binary, "encode", source, same])
                if one.read_bytes() != same.read_bytes():
                    raise AssertionError("default encoder is nondeterministic")
                sfx = folder / "self.run"
                execute([binary, "pack", one, sfx])
                for command in ([sfx], [binary, "decode", sfx]):
                    result = folder / f"restore-{len(command)}"
                    execute([*command, result])
                    if result.read_bytes() != data:
                        raise AssertionError("self-extractor")
                    execute([*command, result], success=False)
                packed = one.read_bytes()
                mutated = bytearray(packed)
                mutated[len(mutated)//2] ^= 85
                for k, broken in enumerate((packed[:16], packed[:-1], mutated, packed+b"extra")):
                    damaged = folder / f"damaged-{k}"
                    damaged.write_bytes(broken)
                    absent = folder / f"absent-{k}"
                    execute([binary, "decode", damaged, absent], success=False)
                    if absent.exists():
                        raise AssertionError("failed decode published an output")
                expected = hashlib.sha256(sfx.read_bytes()).hexdigest()
                execute([binary, "encode", source, sfx, "wiki"], success=False)
                if hashlib.sha256(sfx.read_bytes()).hexdigest() != expected:
                    raise AssertionError("existing output was overwritten")
        if list(folder.glob("*.part-*")):
            raise AssertionError("partial output remains")
    print(f"{len(fixtures)*len(modes)} fixture round trips passed, plus standalone and corruption checks")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    main(parser.parse_args().binary.resolve(strict=True))
