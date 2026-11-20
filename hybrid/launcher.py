#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Encode canonical enwik9, or restore it from the hybrid executable archive."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile, ZipInfo

XML_BYTES = 1_000_000_000
XML_HASH = "159b85351e5f76e60cbe32e04c677847a9ecba3adc79addab6f4c6c7aa3744bc"
TAPE_BYTES = 501_062_281
TAPE_HASH = "c35d3073eeba70f22a2e08a50202b53eb95466e3e9f1f2702f6f9b3f96fd8718"
CODE = ("__main__.py", "transform", "ppmd")
ENCODER_DATA = (".hints", ".new_article_order")


def verify(path, size, expected_hash):
    if path.stat().st_size != size:
        raise ValueError(f"unexpected length for {path.name}")
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if digest != expected_hash:
        raise ValueError(f"unexpected SHA-256 for {path.name}")


def write_bundle(destination, members, payload=None):
    with destination.open("wb") as raw:
        raw.write(b"#!/usr/bin/env python3\n")
        with ZipFile(raw, "w") as out:
            for name, data in members:
                out.writestr(ZipInfo(name), data, compress_type=ZIP_DEFLATED, compresslevel=9)
            if payload is not None:
                info = ZipInfo("payload.7z")
                info.compress_type = ZIP_STORED
                info.file_size = payload.stat().st_size
                with payload.open("rb") as source, out.open(info, "w") as target:
                    shutil.copyfileobj(source, target, 1 << 20)
    destination.chmod(0o755)


def run(bundle, args):
    decoding = "payload.7z" in bundle.namelist()
    if len(args) != (1 if decoding else 2):
        raise ValueError("usage: ARCHIVE OUTPUT" if decoding else "usage: COMPRESSOR ENWIK9 NEW_ARCHIVE")
    destination = Path(args[-1]).absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"destination exists: {destination}")
    if not decoding:
        source = Path(args[0]).resolve(strict=True)
        verify(source, XML_BYTES, XML_HASH)

    with tempfile.TemporaryDirectory(prefix="densewiki-") as directory:
        work = Path(directory).resolve()
        program = {name: bundle.read(name) for name in CODE}
        transform, ppmd = work / "transform", work / "ppmd"
        for helper in (transform, ppmd):
            helper.write_bytes(program[helper.name])
            helper.chmod(0o700)
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as reserved:
            staging = Path(reserved.name)
        try:
            tape, payload = work / "tape", work / "payload.7z"
            if decoding:
                with bundle.open(payload.name) as src, payload.open("wb") as out:
                    shutil.copyfileobj(src, out, 1 << 20)
                subprocess.run([ppmd, "unpack", payload, tape], cwd=work, check=True)
                payload.unlink()
                verify(tape, TAPE_BYTES, TAPE_HASH)
                subprocess.run([transform, "inverse", tape, staging], cwd=work, check=True)
                verify(staging, XML_BYTES, XML_HASH)
            else:
                for name in ENCODER_DATA:
                    (work / name).write_bytes(bundle.read(name))
                subprocess.run([transform, "forward", source, tape], cwd=work, check=True)
                verify(tape, TAPE_BYTES, TAPE_HASH)
                subprocess.run([ppmd, "pack", tape, payload], cwd=work, check=True)
                write_bundle(staging, program.items(), payload)
            os.link(staging, destination)
        finally:
            staging.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        with ZipFile(sys.argv[0]) as archive:
            run(archive, sys.argv[1:])
    except (BadZipFile, OSError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(f"DenseWiki hybrid: {error}")
