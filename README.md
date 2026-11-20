# DenseWiki v0.0.4

DenseWiki restores the canonical 1,000,000,000 bytes of enwik9 from a **202,901,735-byte DWX4 Wiki archive**. This saves 46,851,624 bytes (18.76%) against the runnable v0.0.3 DWX3 archive. The Lean profile uses a smaller dictionary and shorter blocks for faster restoration with less RAM.

| Full enwik9 profile | Runnable bytes | Encode / standalone decode | Peak RSS, encode / standalone decode |
|---|---:|---:|---:|
| DWX4 Wiki | 202,901,735 | 132.457 / 119.419 s | 30.80 / 25.87 MiB |
| DWX4 Lean | 238,629,600 | 114.514 / 32.157 s | 14.96 / 7.58 MiB |

Both archives passed a byte-by-byte comparison with canonical enwik9. Each run used one logical CPU on an AMD EPYC 9V74. Encoding writes a seekable temporary file. The largest sampled temporary-file totals were 659,455,402 bytes for Wiki and 744,278,878 bytes for Lean. Output files are additional. Decoding writes directly to the destination's temporary sibling and publishes it on success. A disk-backed `TMPDIR` keeps the encoder's scratch file off a RAM filesystem.

## Restore the download

From the directory containing the chosen ZIP, use the matching archive. Both write the original Wikipedia XML. Use a new output filename.

```bash
unzip densewiki-v0.0.4-enwik9-wiki.zip
./enwik9-wiki.run enwik9
sha256sum enwik9
```

The Lean ZIP contains `enwik9-lean.run`. The expected output SHA-256 is `159b85351e5f76e60cbe32e04c677847a9ecba3adc79addab6f4c6c7aa3744bc`.

| Executable inside download | Bytes | SHA-256 |
|---|---:|---|
| enwik9-wiki.run | 202,901,735 | `7b1ed487c288c6250f749341171766d0f4dff7f2b8f4ef0cbea04d55dc0e8310` |
| enwik9-lean.run | 238,629,600 | `e33c36e2a1e6d8bed0d1279de61ce17d2add67fed43a2a70eec64c1915925e71` |

The executable includes the program, all file-specific vocabularies, page ordering, compressed data and a 16-byte trailer. The x86-64 Linux build uses the installed libarchive 3 runtime and system C/C++ libraries. Download ZIP metadata is additional. For another Linux installation, build the source below and use `./dwx4/dwx4 decode enwik9-wiki.run enwik9`.

## Build, test and reproduce DWX4

Run these commands from the extracted project with GCC 12 or later, C++20, GNU Make, the libarchive 3 runtime and Python 3.11+ for the test harness. The supplied native executable was built with GCC 14.2.0 on Debian 13. Its Linux symbol requirements include GLIBC_2.34 and GLIBCXX_3.4.29. The Makefile defines the supported GNU string ABI explicitly.

```bash
sha256sum -c --quiet SHA256SUMS
make -B -C dwx4
make -C dwx4 test
python3 tools/test_native_addresses.py
mkdir -p ../densewiki-tmp
python3 dwx4/benchmark.py ../enwik9 ../wiki-bench --profile wiki --scratch ../densewiki-tmp
python3 dwx4/benchmark.py ../enwik9 ../lean-bench --profile lean --scratch ../densewiki-tmp
```

The benchmark records a fresh encode, packaging, standalone decode, memory, scratch-file use, hashes and a byte comparison. Each output directory contains `verified.json`, the stream, the runnable archive and the restored file. Compilers and libarchive versions can change executable or stream bytes. The CLI also handles arbitrary binary files. The earlier Python CLI under `experiments/wiki-words/` remains available for DWX2 and DWX3 archives.

```bash
./dwx4/dwx4 encode input.bin output.dwx wiki
./dwx4/dwx4 decode output.dwx restored.bin
cmp input.bin restored.bin
./dwx4/dwx4 pack output.dwx example.run
```

## Sub-100 MB native profiles

| Profile | archive9 | comp9 | Combined | Combined saving vs v0.0.3 |
|---|---:|---:|---:|---:|
| Size, derived from Ex-Girlfriend 2.0 | 88,982,491 | 4,056,498 | 93,038,989 | 622 |
| Prize candidate, derived from cmix-neif 2.0 | 89,345,759 | 4,041,931 | 93,387,690 | 622 |

Both pairs are present under `release/size/` and `release/prize/`. Each uses a 7,286-byte startup block. Full inner executable images, complete model and Wikipedia payloads and both startup entry points were checked. The prize decoder also matched the upstream decoder for 65,536 model-stream bytes before inverse Wikipedia preprocessing. Full-corpus native encode/decode runs remain open. The measured DWX4 times in the first table apply only to those two lightweight profiles.

```bash
python3 tools/materialize.py size ../original-size --original
python3 tools/build.py size ../original-size ../rebuilt-size
cmp release/size/archive9 ../rebuilt-size/archive9
python3 tools/materialize.py prize ../original-prize --original
python3 tools/build.py prize ../original-prize ../rebuilt-prize
cmp release/prize/archive9 ../rebuilt-prize/archive9
```

The long-run harness for a suitably provisioned x86-64-v3 Linux host is `python3 tools/roundtrip.py prize ../enwik9 ../prize-roundtrip`. It verifies the canonical input, regenerated archive, restored output and complete byte comparison. Use `size` and a separate directory for the other profile.

The research report includes full-corpus ablations and the experiments that lost bytes. The JSON receipt contains exact timings and checked hashes. [Research](RESEARCH.md) | [Benchmark](results/enwik9-v0.0.4.json) | [DWX4 format](dwx4/FORMAT.md).

## Attribution

DenseWiki's DWX4 transformations use GPL-3.0-only. The entropy coders come from libarchive's PPMd implementation and liblzma. The two native Wikipedia models derive from Ryan Landay's Ex-Girlfriend 2.0 and Marcus Woelk's cmix-neif 2.0. The scientific and implementation credits, upstream source packages, dataset notices and earlier research are included. [Native notices](upstream/EX2-NOTICE.md) | [Training attribution](upstream/TRAINING-ATTRIBUTION.md) | [Wikipedia license](upstream/CC-BY-SA-4.0.txt).
