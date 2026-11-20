# DenseWiki v0.0.2

DenseWiki ships an **88,982,834-byte self-extracting archive** of the 1,000,000,000-byte enwik9 Wikipedia benchmark. The matching standalone compressor is **4,056,841 bytes**. The pair totals **93,039,675 bytes**, 438 bytes smaller than DenseWiki v0.0.1. All release commands take zero option bytes when invoked as the native compressor or archive.

| Size profile | archive9 | comp9 | Counted total |
|---|---:|---:|---:|
| Ex-Girlfriend 2.0 | 88,983,124 | 4,057,131 | 93,040,255 |
| DenseWiki v0.0.1 | 88,983,053 | 4,057,060 | 93,040,113 |
| DenseWiki v0.0.2 | **88,982,834** | **4,056,841** | **93,039,675** |

The startup program in each file is 219 bytes smaller. It reconstructs a 12,311-byte native loader by predicting its bytes from selected positions in recent history. Some predictors group byte values that share the same bits. Each group keeps one set of counts for predicting the next byte. The Wikipedia model and all **85,039,910 compressed Wikipedia bytes** are identical to the published parent.

A separate word-reference codec produced a smaller encoding of an 880,672-byte Wikipedia excerpt, including its own decoder. Its runnable archive used **249,424 bytes**, against **256,587 bytes** for an XZ archive carrying its decoder. The 50,051-byte profiling tail cost 1,069 bytes more with the word codec. This experiment has its own format and results. See [measurements and methods](RESEARCH.md).

## Files and verification

The project ZIP contains both native executables under `release/size/`, source, the complete upstream source distributions, licenses and measurements. The pair-only ZIP contains just `archive9` and `comp9`. The scored total is the sum of the two extracted file lengths.

| File | SHA-256 |
|---|---|
| archive9 | `9c6049f0f190685dd460637c3927356b63ccf14d65fa737417cdc16bc4ba5ecd` |
| comp9 | `6b8f2b51de02bdd5c91cf52240332f8b454d98e04798dac8c367f4706e6a3748` |
| Expected decoded enwik9 | `159b85351e5f76e60cbe32e04c677847a9ecba3adc79addab6f4c6c7aa3744bc` |

The build reconstructed both complete, hash-pinned parent files and reproduced the v0.0.1 and v0.0.2 release files byte for byte. Both v0.0.2 native entry points were exercised and their decoded program images and extracted inputs were compared. A fresh full billion-byte model run is outstanding for v0.0.2. The upstream full encode and fresh decode took about 95 hours each and used about 24.3 GiB of RAM. The CPU-only size profile exceeds the upstream prize-track resource envelope. The retained `prize` profile and its manifests correspond to v0.0.1. [Native checks](results/native-checks.json) and [upstream full run](upstream/ex2-verification.json).

## Decode the included archive

Use x86-64-v3 Linux with AVX2 and FMA. Allow about 32 GiB of RAM and 30 GB of free working disk. From the project root, use a fresh directory. The native entry points create working files relative to their current directory.

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

## Encode and verify on the original corpus

```bash
python3 tools/roundtrip.py size /absolute/path/to/enwik9 ../densewiki-002-run
```

This runner checks the input hash, pins the encode and decode to one allowed CPU, checks the generated archive against v0.0.2, and byte-compares the fresh decoder output with the input. Completed stages can be reused with `--resume`. The result is `verified.json`. The source corpus is the first billion bytes of the March 2006 English Wikipedia dump. [Canonical dataset](https://www.mattmahoney.net/dc/textdata.html).

## Rebuild from the included bytes

```bash
python3 tools/materialize.py size ../densewiki-original --original
python3 tools/build.py size ../densewiki-original ../densewiki-rebuilt
cmp release/size/archive9 ../densewiki-rebuilt/archive9
cmp release/size/comp9 ../densewiki-rebuilt/comp9
python3 tools/verify_layers.py ../densewiki-native-checks.json
```

Release reconstruction uses Python 3.11+ with the tarfile data filter, GCC 14.2.0 and GNU ld 2.44 on x86-64 Linux. The build checks the original compressed startup, encodes the selected policy, decodes the result independently, and checks the final linked bytes. Other toolchains can emit different executable lengths. Use `tools/materialize.py prize NEW_DIRECTORY` to recover the retained alternative encoder. The original prize archive can be supplied using `--reference-archive`.

## Restore the included word-codec example

```bash
python3 -I release/word-pilot/wiki-excerpt.pyz ../wiki-excerpt.bin
```

The output is the 880,672-byte excerpt. Its reference bytes and SHA-256 are identified in `results/wiki-words.json`.

## Run the word codec on a Wikipedia dump

```bash
python3 experiments/wiki-words/full_corpus.py /absolute/path/to/enwik9 ../densewiki-word-test
```

The benchmark writes a continuous XZ archive, a blocked XZ control, a vocabulary-coded archive, and a JSON receipt. It compares every recovered byte from each archive to the original. It streams the input in 1 MiB blocks for the vocabulary experiment and uses Python's standard library. The native size profile and this text benchmark can run independently.

## Attribution

DenseWiki extends the Ex-Girlfriend 2.0 release by Ryan Landay, based on Marcus Woelk's cmix-neif 2.0. The upstream notices identify the earlier cmix, transformer, BITLSTM and training contributors. DenseWiki modifications use GPL-3.0-only. Wikipedia content retains its original contributor attribution and licensing. The upstream source, training code, notices and applicable license texts are included. [Upstream notices](upstream/EX2-NOTICE.md), [training attribution](upstream/TRAINING-ATTRIBUTION.md), [v0.0.1 history](HISTORY-v0.0.1.md).
