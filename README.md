# DenseWiki v0.0.1

DenseWiki is a lossless compression research release for the Hutter Prize's **1,000,000,000-byte enwik9**. The ZIP contains a runnable **88,983,053-byte self-extracting archive** of the corpus and its **4,057,060-byte compressor**. Both include everything they need to run on a compatible Linux host. The combined size is **93,040,113 bytes**, 142 bytes below Ryan Landay's published Ex-Girlfriend 2.0 pair. The smaller startup decoder accounts for the whole improvement.

| Profile | Self-extracting archive (bytes) | Compressor (bytes) | Counted total (bytes) | Saving against its parent |
|---|---:|---:|---:|---:|
| Ex-Girlfriend 2.0, published | 88,983,124 | 4,057,131 | 93,040,255 | |
| **DenseWiki size** | **88,983,053** | **4,057,060** | **93,040,113** | **142 B** |
| cmix-neif 2.0, published | 89,346,392 | 4,042,564 | 93,388,956 | |
| **DenseWiki prize** | **89,346,321** | **4,042,493** | **93,388,814** | **142 B** |

All four pairs take zero option bytes. The score charges every byte of both standalone executables, including both copies of the weights. The outer distribution ZIP also contains source, experiments and validation results. All MB in the size comparisons are decimal. [Contest rules](https://hutter1.net/prize/hrules.htm) and [benchmark results](https://www.mattmahoney.net/dc/text.html).

**Verification status.** Both candidate pairs were physically built and measured. Their executable entry points were launched on Linux. Each restored exactly the same native program image as its published parent, and the launched decoders extracted the complete expected Wikipedia bitstreams and weights. We also hashed the original 1 GB corpus. End-to-end encode, fresh decode, byte comparison, elapsed time and peak RAM for the complete model runs are available from upstream. A fresh full run of either modified pair remains outstanding. The release host had 9.73 GiB of total RAM. See `results/native-checks.json` and `upstream/ex2-verification.json`.

**Prize status as of November 19, 2026.** The official site lists 100,424,672 bytes as the awarded result, with a displayed next target below 99,420,425. Marcus Woelk's 93,388,956-byte submission is pending an award. The unrestricted size profile inherits a parent measured at 24.3 GiB and about 95 hours per direction, outside the prize limits. The prize profile starts from Woelk's original CPU design, measured by its author at 9.77 GiB and 49.18 hours for encoding and 9.75 GiB and 49.30 hours for decoding on his machine. Neither DenseWiki build has been submitted or judged. Relative to its own parent, 142 bytes is below the prize's 1% requirement. The prize profile needs another 348,560 bytes to beat the published unrestricted total of 93,040,255. [Awarded results](https://hutter1.net/prize/index.htm), [cmix-neif submission](https://github.com/marwoelk/cmix-neif-2.0), [Ex-Girlfriend release](https://github.com/rlanday/ex-girlfriend/releases/tag/v2.0).

## Decode the included Wikipedia archive

Run from the root of the unpacked ZIP. Use x86-64-v3 Linux with AVX2 and FMA. The Ryzen 5 5600X can run these binaries. For the size profile, allow 32 GiB of RAM and 30 GB of free working disk. The binaries use one CPU core and need no GPU, Python environment, model download or root installation. Use a fresh working directory. The output file is named `enwik9_uncompressed`.

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

For a raw source file, extract the official `enwik9.zip`. It contains the first billion bytes of the March 2006 English Wikipedia XML dump. [Canonical dataset and downloads](https://www.mattmahoney.net/dc/textdata.html).

## Encode and independently verify

```bash
python3 tools/roundtrip.py prize /absolute/path/to/enwik9 ../densewiki-prize-run
```

The runner requires Python 3.11+ on Linux. It hashes the input, pins the native process to one permitted logical CPU, runs the no-argument encoder, checks the expected archive size and SHA-256, then starts that archive in a fresh directory. It hashes and byte-compares the output to the input. The two phase logs and a final `verified.json` go into the chosen run directory. An interrupted run can be restarted with the same command and `--resume`. Completed phases are revalidated, and an interrupted phase starts from its beginning. Its process-tree RSS counter samples once per second. Official judging has its own resource measurement.

Choose `size` in place of `prize` to run the smaller archive's model. The size pair is in `release/size/`. The prize encoder can also be rebuilt directly from the bundled bytes as follows.

```bash
python3 tools/materialize.py prize ../prize-bin
```

Place this `comp9` beside the original file named `enwik9` and run `./comp9`. It writes the self-extracting `archive9`. The ZIP ships the complete size archive and one shared copy of the weights needed to reconstruct the alternative encoder. To obtain the prize archive immediately from an existing copy of Woelk's published archive, add `--reference-archive /path/to/original/cmix-neif-2.0/archive9` to the materialize command and choose a fresh output directory. The tool checks both upstream and generated hashes. [Woelk's original binary files](https://marwoelk.de/cmix-neif-2.0/).

## Inspect or rebuild the released change

```bash
python3 tools/materialize.py size ../ex2-original --original
python3 tools/build.py size ../ex2-original ../size-rebuilt
cmp release/size/comp9 ../size-rebuilt/comp9
cmp release/size/archive9 ../size-rebuilt/archive9
python3 tools/check_core.py size ../ex2-original ../size-rebuilt
```

This rebuild decodes the original calibration image, reproduces its original stream, encodes the same image with the selected policy, checks it with a separate decoder, and links the native startup program. It charges the complete linked image. The exact release was built with Debian GCC 14.2.0 and GNU ld 2.44. Different toolchains can change the executable length. The same sequence accepts `prize` and its original encoder with optional matching archive. On either profile, `tools/check_startup.py PAIR /path/to/enwik9 encode` or `decode` runs the actual executable and verifies its extracted components before deliberately stopping it.

Both complete upstream source distributions, training code, weights and original notices are in `upstream/sources.tar.xz`. For example, `python3 tools/prepare_experiment.py size-original ../ex2-source` extracts the original tree. Its `README.md` and build scripts specify the upstream LLVM 18.1.3 and GCC 13.3 support files for a byte-identical base on Ubuntu. The source extractor uses Python 3.12 or Python 3.11 with the tarfile data-filter backport. See [research, experiments and attribution](RESEARCH.md) for the actual cache patches, model search and evidence.
