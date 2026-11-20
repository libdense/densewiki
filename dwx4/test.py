#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Exercise the public CLI, executable archive and format boundaries."""
import argparse
import hashlib
from pathlib import Path
import random
import re
import subprocess
import tempfile


def execute(args, success=True):
    p = subprocess.run(args, capture_output=True)
    if (p.returncode == 0) != success:
        raise RuntimeError(f"{args}: {p.returncode}: {p.stderr[-500:]!r}")


def article_cases(binary, folder):
    directory = b"[[Steven Spielberg]]"
    filler = b" ".join(f"[[Target {i}]]".encode() for i in range(32))
    film = (b"  <page>\n    <title>Sample</title>\n"
            b"      <text xml:space=\"preserve\">{{Infobox Film |\n"
            b"  director = [[Steven Spielberg]] |\n"
            b"  starring = [[Roy Scheider]], [[First (actor)|Actor Name]] |\n"
            b"  released = [[June 20]], [[1975]] |\n"
            b"  location = New York |\n  nested = {{x|k=v}} |\n}}\n"
            b"Steven Spielberg directed Actor Name in New York on June 20, 1975.\n"
            b"[[Steven Spielberg|Director]], [[Roy Scheider]] and Steven Spielberg.\n"
            b"Literal marks \r \x00 [ [[broken [ [[valid]] [[valid|shown]] [[#A]] [[#A]].\n"
            b"  </page>\n")
    taxon = (b"  <page>\n{{Taxobox\n| binomial = ''Orycteropus afer''\n}}\n"
             b"Orycteropus afer, Orycteropus afer. Steven Spielberg.\n  </page>\n")
    other = b"  <page>\nSteven Spielberg and Actor Name in New York.\n  </page>\n"
    eviction = (b"  <page>\n[[Ejected]] " + filler + b" [[Ejected]] [[Target 31|x]]"
                b" [[Target 31]]\n  </page>\n  <page>\n[[Target 31]]\n  </page>\n")
    long_target = b"[[A deliberately long target]]"
    guarded = (b"  <page>\n" + long_target + b" and " + long_target + b"\n" +
               b"In 1212 and 1414 the text mentions " + long_target + b".\n  </page>\n")
    cases = [(guarded, "links-select", "link_refs", 1),
             (film + taxon + other, "facts-select", "fact_refs", None),
             (guarded + film, "article-select", "link_refs", None),
             (film + taxon + other, "film", "fact_refs", 8),
             (film + taxon + other, "facts", "fact_refs", 10),
             (eviction, "links", "link_refs", 2),
             (eviction + film + taxon, "article", "link_refs", None)]
    for i, (source, mode, counter, expected) in enumerate(cases):
        plain, stream, restored = [folder / f"local-{i}-{s}" for s in ("in", "stream", "out")]
        plain.write_bytes(source)
        encoded = subprocess.run([binary, "encode", plain, stream, mode], capture_output=True, check=True)
        observed = int(re.search(rf"\b{counter}=(\d+)", encoded.stderr.decode())[1])
        if (expected is not None and observed != expected) or not observed:
            raise AssertionError(f"{mode}: {counter}={observed}, expected {expected}")
        execute([binary, "decode", stream, restored])
        if restored.read_bytes() != source:
            raise AssertionError(f"local fixture {mode}")
    # An incomplete physical record cannot supply facts to a reordered fragment.
    # Literal bytes at the split include both reference markers and malformed links.
    boundary = (film[:-10] + (b"x" * (512 * 1024)) + b"\n  </page>\n" + other +
                b"\x00\r" * (512 * 1024) + b"  <page>\n" + directory + b"\n")
    plain, packed, result = [folder / f"boundary-{s}" for s in ("in", "stream", "out")]
    plain.write_bytes(boundary)
    execute([binary, "encode", plain, packed, "article"])
    execute([binary, "decode", packed, result])
    if result.read_bytes() != boundary:
        raise AssertionError("partial-page boundaries or literal markers")


def film_sample_regression(binary, source):
    expected = "3c89d6cfb611abf807fb7e2bd25d57b8c2c8fc5cd8141bee9f8c41bb03cf80d4"
    with source.open("rb") as page_file:
        if hashlib.file_digest(page_file, "sha256").hexdigest() != expected:
            raise ValueError("generate the 1,118-page film sample with tools/film_sample.py")
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        stream, runnable, restored = [folder / n for n in ("stream", "archive", "restored")]
        execute([binary, "encode", source, stream, "facts"])
        execute([binary, "pack", stream, runnable])
        execute([runnable, restored])
        if source.read_bytes() != restored.read_bytes():
            raise AssertionError("film-sample PPMd restore")
    print("Full film-sample archive passed the contiguous-read regression")


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
    modes = ["raw", "words", "fields", "templates", "topics", "titles", "wiki", "lean", "film", "facts", "links", "article", "facts-select", "links-select", "article-select"]
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        article_cases(binary, folder)
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
    parser.add_argument("--film-sample", type=Path, help="test the exact corpus fixture from tools/film_sample.py")
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True)
    main(binary)
    if args.film_sample:
        film_sample_regression(binary, args.film_sample.resolve(strict=True))
