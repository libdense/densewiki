#!/usr/bin/env python3
"""Rebuild the two named enwik9 release files after fitting their common startup block."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FLAT_SIZE = 12311
FLAT_HASH = "d3d7d0708597baef9b55259f7a63541494e173e93b046de06444d6819b29715a"
ORIGINAL = {"masks": [1, 2, 3, 4, 0, 17, 6, 5, 9], "region_shift": 31, "bit_shift": 3,
            "prior": 3, "weights": [[4, 2, 8, 1, 1, 8, 4, 8, 4]]}
PROFILES = {
    "size": {"comp9": "8d2a5fd03da10e671286726ab620183c0b6072ba68021c03076304e29f80406a",
             "archive9": "0b65bc79917f84b78f4974a2dc94d4d4c3fc6c0c53234bdcb6c282db802635a3"},
    "prize": {"comp9": "976bf2d309707ab555e0c92720da5508ff0e5e6b846fc7082234262b06767f82",
              "archive9": "88dd7087404122d010261e6855afd88875d34dde1f0539377d3e832fc0f6b3fd"},
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode_policy(p):
    m = len(p["masks"])
    if not 1 <= m <= 32 or not 0 <= p["region_shift"] <= 31 or not 0 <= p["bit_shift"] <= 3:
        raise ValueError("invalid context geometry")
    groups = (1 + ((FLAT_SIZE - 1) >> p["region_shift"])) * (8 >> p["bit_shift"])
    if not 1 <= groups <= 256 or len(p["weights"]) != groups or not 1 <= p["prior"] <= 255:
        raise ValueError("invalid prior or bank count")
    if any(len(w) != m for w in p["weights"]):
        raise ValueError("incomplete bank")
    cap, boost, decay, keep = p.get("dynamics", [255, 2, 1, 1])
    if not (1 <= cap <= 255 and 1 <= boost <= 32 and 1 <= decay <= 4 and keep in (0, 1)):
        raise ValueError("invalid counter dynamics")
    return b"DWM2" + bytes([m, p["region_shift"], p["bit_shift"], p["prior"], cap, boost, decay, keep] + p["masks"] +
                           [x for bank in p["weights"] for x in bank])


def linked_image(p, coded, cwd):
    encode_policy(p)
    if p.get("optimization", "-Os") not in ("-Os", "-Oz"):
        raise ValueError("unsupported compiler optimization")
    masks = p["masks"]
    weights = [x for bank in p["weights"] for x in bank]
    bits = 8 >> p["bit_shift"]
    cap, boost, decay, keep = p.get("dynamics", [255, 2, 1, 1])
    macros = {"DW_BOOST": boost, "DW_DECAY": decay, "DW_KEEP": keep, "DW_BRANCHES": int(p.get("branches", False)),
              "BOOT_NM": len(masks), "BOOT_TB": 22, "BOOT_SHIFT": 42, "BOOT_TSZ": 8388608,
              "BOOT_EPS": p["prior"], "BOOT_CAP": cap, "DW_REGION_SHIFT": p["region_shift"],
              "DW_BIT_SHIFT": p["bit_shift"], "DW_BIT_GROUPS": bits,
              "DW_BIT_GROUP_LOG2": 3 - p["bit_shift"], "DW_REGIONS": len(p["weights"]) // bits,
              "DW_BANKS": len(p["weights"]), "BOOT_MASK_LIST": ",".join(map(str, masks)),
              "BOOT_WT_LIST": ",".join(map(str, weights))}
    (cwd / "policy.h").write_text("".join(f"#define {key} {v}\n" for key, v in macros.items()))
    (cwd / "stage.coded").write_bytes(coded)
    cc = os.environ.get("CC", "cc")
    subprocess.run([cc, p.get("optimization", "-Os"), "-nostdlib", "-static", "-ffreestanding", "-fno-pie", "-no-pie",
                    "-fno-asynchronous-unwind-tables", "-fno-stack-protector", "-fcf-protection=none",
                    "-fdata-sections", "-ffunction-sections", "-I.", "-DS2BASE=0x10000000",
                    "-DS2MEM=0x18aa000", f"-DS2LEN={FLAT_SIZE}", '-DS2CM="stage.coded"',
                    f"-Wl,-T,{ROOT / 'src/stage1.ld'}", "-Wl,--build-id=none", "-Wl,--gc-sections",
                    "-Wl,-e,_start", str(ROOT / "src/stage1.c"), "-o", "stage.elf"],
                   cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    elf = bytearray((cwd / "stage.elf").read_bytes())
    if (elf[:7] != b"\x7fELF\x02\x01\x01" or struct.unpack_from("<Q", elf, 32)[0] != 64 or
        struct.unpack_from("<HH", elf, 54) != (56, 1)):
        raise ValueError("unexpected ELF layout")
    typ, flags, offset, vaddr, _, file_size, mem_size, _ = struct.unpack_from("<IIQQQQQQ", elf, 64)
    if (typ != 1 or flags != 7 or offset or vaddr != 0x400000 or file_size != mem_size or
        file_size > len(elf) or elf[file_size-len(coded):file_size] != coded):
        raise ValueError("linked data differs from the checked coder stream")
    if elf[144:144 + len(masks) + len(weights)] != bytes(masks + weights):
        raise ValueError("linked model table mismatch")
    # Strip link-time sections exactly as the upstream release build does.
    elf[40:48] = bytes(8)
    elf[58:64] = bytes(6)
    return bytes(elf[:file_size])


def checked_input(directory, name, profile):
    data = (directory / name).read_bytes()
    if digest(data) != PROFILES[profile][name]:
        raise ValueError(f"upstream {profile} {name} SHA-256 mismatch")
    return data


def with_head(data, head):
    fields = struct.unpack_from("<6I", data, 120)
    if fields[0] != 7919:
        raise ValueError("unexpected upstream Hutter-format header")
    header = bytearray(head)
    struct.pack_into("<6I", header, 120, len(head), *fields[1:])
    return bytes(header) + data[fields[0]:]


def prefix_from_encoder(encoder):
    h = list(struct.unpack_from("<6I", encoder, 120))
    end = h[0] + h[5]
    data = bytearray(encoder[:end])
    h[1], h[2] = h[5], h[4]
    struct.pack_into("<6I", data, 120, *h)
    return bytes(data)


def branch_transform(data, inverse=False):
    out = bytearray(data)
    i = 0
    while i + 5 <= len(out):
        if out[i] in (232, 233):
            value = struct.unpack_from("<I", out, i + 1)[0]
            step = i + 5
            struct.pack_into("<I", out, i + 1, (value + (-step if inverse else step)) & 0xffffffff)
            i += 5
        else:
            i += 1
    return bytes(out)


def build(args):
    source = args.upstream.resolve()
    destination = args.output.resolve()
    if destination.exists():
        raise FileExistsError(f"output must be new: {destination}")
    inputs = {"comp9": checked_input(source, "comp9", args.profile)}
    if (source / "archive9").exists():
        inputs["archive9"] = checked_input(source, "archive9", args.profile)
    policy = json.loads(args.policy.read_text())
    with tempfile.TemporaryDirectory() as scratch, tempfile.TemporaryDirectory(dir=destination.parent) as staging:
        temp, stage = Path(scratch), Path(staging) / "publish"
        stage.mkdir()
        mix = temp / "mix"
        subprocess.run([os.environ.get("CC", "cc"), "-O3", "-std=c11", ROOT / "src/mix.c", "-o", mix],
                       check=True)
        def convert(mode, name, input_data, settings):
            src, dst, cfg = (temp / f"{name}.{ext}" for ext in ("src", "out", "policy"))
            src.write_bytes(input_data)
            cfg.write_bytes(encode_policy(settings))
            subprocess.run([mix, mode, cfg, src, dst], check=True)
            return dst.read_bytes()
        original = inputs["comp9"][757:7919]
        raw = convert("decode", "unpack-original", original, ORIGINAL)
        if digest(raw) != FLAT_HASH or convert("encode", "recode-original", raw, ORIGINAL) != original:
            raise ValueError("canonical upstream bootstrap did not round-trip")
        prepared = branch_transform(raw) if policy.get("branches") else raw
        encoded = convert("encode", "encode-candidate", prepared, policy)
        restored = convert("decode", "decode-candidate", encoded, policy)
        if (branch_transform(restored, True) if policy.get("branches") else restored) != raw:
            raise ValueError("candidate bootstrap did not round-trip")
        head = linked_image(policy, encoded, temp)
        files = {name: with_head(data, head) for name, data in inputs.items()}
        prefix = prefix_from_encoder(files["comp9"])
        if "archive9" in files and not files["archive9"].startswith(prefix):
            raise ValueError("compressor-selected decoder differs from the archive")
        report = {"profile": args.profile, "flat_sha256": digest(raw), "flat_bytes": len(raw),
                  "old_head_bytes": 7919, "new_head_bytes": len(head), "candidate_coded_bytes": len(encoded),
                  "candidate_decoder_prefix_sha256": digest(prefix), "files": {}}
        for name, data in files.items():
            target = stage / name
            target.write_bytes(data)
            target.chmod(0o755)
            report["files"][name] = {"upstream_bytes": len(inputs[name]), "bytes": len(data),
                                     "sha256": digest(data), "unchanged_suffix_bytes": len(data)-len(head),
                                     "unchanged_suffix_sha256": digest(data[len(head):])}
            if data[len(head):] != inputs[name][7919:]:
                raise ValueError("bytes beyond the replaced startup block differ")
        if "archive9" in files:
            report["total_bytes"] = sum(map(len, files.values()))
            report["saving_bytes"] = sum(map(len, inputs.values())) - report["total_bytes"]
        (stage / "build.json").write_text(json.dumps(report, indent=2) + "\n")
        if destination.exists():
            raise FileExistsError(destination)
        stage.rename(destination)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=PROFILES)
    parser.add_argument("upstream", type=Path, help="directory with published comp9 and optional archive9")
    parser.add_argument("output", type=Path, help="new output directory")
    parser.add_argument("--policy", type=Path, default=ROOT / "results/policy.json")
    build(parser.parse_args())
