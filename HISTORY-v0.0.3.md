# DenseWiki v0.0.3

DenseWiki's size profile stores the 1,000,000,000-byte enwik9 Wikipedia corpus in an 88,982,802-byte self-extracting archive. The standalone compressor adds 4,056,809 bytes. The counted total is **93,039,611 bytes**, 64 bytes below v0.0.2. Each executable takes zero option bytes.

| Native profile | v0.0.2 total | v0.0.3 archive9 | v0.0.3 comp9 | v0.0.3 total | Bytes saved |
|---|---:|---:|---:|---:|---:|
| Size, derived from Ex-Girlfriend 2.0 | 93,039,675 | 88,982,802 | 4,056,809 | **93,039,611** | 64 |
| Prize-track candidate, derived from cmix-neif 2.0 | 93,388,814 | 89,346,070 | 4,042,242 | **93,388,312** | 502 |

Two independent experiments address memory and compression of the text itself. The low-memory C++ model allocates semantic-cache pages on demand and reduces the resident PPMd pool. The DWX3 word codec groups article bodies, shares dictionary entries across capitalization variants, and limits its XZ dictionary to one input block. Both have byte-comparison receipts. See [measurements and limitations](RESEARCH.md).

## Run or verify a native release

From the project root on x86-64-v3 Linux, verify the package and run the self-extracting size archive in an empty directory. The native program writes working files next to its output. The size profile's upstream full-run receipt reports about 24.3 GiB peak RAM. Allow about 32 GiB of RAM and 30 GB of scratch space for this profile.

```bash
sha256sum -c SHA256SUMS
mkdir ../densewiki-decode
cp release/size/archive9 ../densewiki-decode/
(
    cd ../densewiki-decode
    chmod +x archive9
    ./archive9
    printf "%s  %s\n" "159b85351e5f76e60cbe32e04c677847a9ecba3adc79addab6f4c6c7aa3744bc" "enwik9_uncompressed" | sha256sum -c -
)
```

The separate pair ZIPs each contain just `comp9` and `archive9`. The main project ZIP carries the complete size pair, both source trees, and enough data to reconstruct the prize compressor. To reconstruct the prize archive from this main ZIP, supply the author's original archive. The command checks its SHA-256. [Original cmix-neif 2.0 files](https://marwoelk.de/cmix-neif-2.0/).

```bash
curl -fL --retry 2 -o ../cmix-neif-2.0-archive9 "https://marwoelk.de/cmix-neif-2.0/archive9"
python3 tools/materialize.py prize ../densewiki-prize --reference-archive ../cmix-neif-2.0-archive9
```

The round-trip runner pins the encoder and fresh decoder to one CPU and compares the output with the input. The receipts below identify exactly which shorter native checks ran during this release. A full candidate model run on enwik9 remains open. [Size checks](results/native-checks.json), [prize checks](results/native-checks-prize.json), [Ex-Girlfriend's upstream full run](upstream/ex2-verification.json), [canonical corpus](https://mattmahoney.net/dc/textdata.html).

```bash
python3 tools/roundtrip.py prize /absolute/path/to/enwik9 ../prize-roundtrip
python3 tools/roundtrip.py size /absolute/path/to/enwik9 ../size-roundtrip
```

## File verification

| File | SHA-256 |
|---|---|
| size / archive9 | `4659522f09a1055b6663d0467960e352bbf93f687b19ad2277a574476b2a3c07` |
| size / comp9 | `b7efc3e8aafec92353e5047397510e6a92ef357be9f101fd5f066e1f46aea4a2` |
| prize / archive9 | `3f0cada1b781742be9312b20c00bc6f3d56298d507e1e4b347d9bea21c8b247d` |
| prize / comp9 | `066a801fb5a1844f82732f650c003742dd6aaccf71ea3a16cfa3d4447e7ca1f2` |
| densewiki-v0.0.3-enwik9-pair.zip | `53f1b0a5a70f034eea8838932679b026ebc189cc555154f9c44a2a0cf62760d0` |
| densewiki-v0.0.3-prize-pair.zip | `ef20f74ae576d6fe27b9ee0e822c2d88f183795a70d64365859fff0b307c0744` |
| densewiki-v0.0.3-enwik9-lowmem.pyz | `7558a7fb41294325a4a152f37a3ddc757682e124239f8411c2293d88e32b4f85` |

Each two-file native ZIP adds 200 bytes of container metadata. The project ZIP also includes the sources, experiments and verification records.

## Reproduce the native packages

The reference inputs are hash-pinned. The release build used GCC 14.2.0 and GNU ld 2.44 on x86-64 Linux. Python 3.11 or newer with tarfile's data extraction filter is required. Other code generators can change the executable bytes. The startup RSS comparison measures the Linux peak through reconstruction of the complete inner program.

```bash
python3 tools/materialize.py size ../original-size --original
python3 tools/build.py size ../original-size ../rebuilt-size
cmp release/size/comp9 ../rebuilt-size/comp9
cmp release/size/archive9 ../rebuilt-size/archive9
python3 tools/materialize.py prize ../original-prize --original --reference-archive ../cmix-neif-2.0-archive9
python3 tools/build.py prize ../original-prize ../rebuilt-prize
python3 tools/measure_startup.py ../startup-memory.json
```

## Reproduce the lower-memory model test

```bash
python3 experiments/low-memory/benchmark.py ../model-memory --sizes 16384 32768 65536
python3 tools/prepare_experiment.py prize-lowmem ../prize-lowmem-source
```

The benchmark builds two fresh native model binaries from the bundled sources using GCC, enters the article-text phase, and invokes the original model's range encoder and decoder. It records semantic insertions, peak RSS and exact cross-decoded bytes. The second command prepares the production source without the benchmark entry point. Upstream's production build instructions and toolchain requirements are in the extracted tree.

To build the experimental no-argument compressor for a full measurement, use the production toolchain listed in the prepared project's README (including Clang and LLD 18). Build in an empty directory and give the resulting executable to the same verification runner. It records the actual score and compares the restored bytes.

```bash
mkdir ../prize-lowmem-build
(cd ../prize-lowmem-build && bash ../prize-lowmem-source/build.sh)
python3 tools/roundtrip.py prize /absolute/path/to/enwik9 ../prize-lowmem-roundtrip --encoder ../prize-lowmem-build/comp9
```

## Decode the full low-memory archive

The standalone `densewiki-v0.0.3-enwik9-lowmem.pyz` is 249,753,359 bytes including its decoder. It restored canonical enwik9 in a fresh Python process with **15.75 MiB peak RSS** on the release host. It uses the installed Python standard library and XZ runtime. Allow space for the 1 GB output file. [Full-file memory and hash receipt](results/lowmem-runnable.json).

```bash
python3 -I densewiki-v0.0.3-enwik9-lowmem.pyz enwik9.restored
printf "%s  %s\n" "159b85351e5f76e60cbe32e04c677847a9ecba3adc79addab6f4c6c7aa3744bc" "enwik9.restored" | sha256sum -c -
```

## Run the lightweight text codec

```bash
python3 experiments/wiki-words/codec.py encode /absolute/path/to/input ../input.dwx
python3 experiments/wiki-words/codec.py decode ../input.dwx ../restored
cmp /absolute/path/to/input ../restored
python3 -I release/word-pilot/wiki-excerpt-v3.pyz ../wiki-excerpt.xml
```

All 954 canonical enwik9 blocks selected the same article-field and capitalization transform. For this corpus, `--mode wiki` selects it directly. To assemble a standalone Python archive from a DWX3 stream, run `python3 experiments/wiki-words/standalone.py input.dwx wikipedia.pyz`.

The CLI writes DWX3 by default and reads DWX2 and DWX3. The standalone Python example restores the 880,672-byte canonical Wikipedia prefix with the standard library. To compare both complete streams on enwik9, use the following command. It writes the same archive bytes with any positive worker count. Each extra worker has its own bounded state. The default is one worker.

```bash
python3 experiments/wiki-words/verify_corpus.py /absolute/path/to/enwik9 ../word-comparison --workers 7
```

## Attribution

DenseWiki extends Ryan Landay's Ex-Girlfriend 2.0 and Marcus Woelk's cmix-neif 2.0. The models, pretrained weights, preprocessors and most of the native compression result come from those projects and their predecessors. DenseWiki modifications use GPL-3.0-only. The upstream source, training attribution and Wikipedia license texts are included. [Upstream notices](upstream/EX2-NOTICE.md), [training attribution](upstream/TRAINING-ATTRIBUTION.md), [v0.0.2 research](HISTORY-v0.0.2.md).
