# DenseWiki v0.0.5

The hybrid restores the original 1,000,000,000 bytes of enwik9 from a **169,707,769-byte executable archive**. That saves 33,193,966 bytes (16.36%) against the released v0.0.4 DWX4 Wiki archive. It combines Marcus Woelk's cmix-neif 2.0 Wikipedia preprocessor with the continuous PPMd coder from DWX4 Wiki. The native preprocessor uses more time and RAM. The general-purpose CLI still defaults to Wiki.

| Full enwik9 build | Runnable archive, bytes | Archive + compressor, bytes | Encode / restore | Peak RSS, encode / restore |
|---|---:|---:|---:|---:|
| v0.0.4 DWX4 Wiki | 202,901,735 | 203,015,143 | 137.2 / 135.3 s | 30.8 / 25.9 MiB |
| v0.0.5 cmix-neif + PPMd | 169,707,769 | 170,001,938 | 376.7 / 228.2 s | 1,703.4 / 1,188.5 MiB |

Both rows are fresh measurements on one logical CPU of an AMD EPYC 9V74. Peak RSS excludes the native preprocessor's unnamed files on the host's memory-backed /tmp. The research report measures those separately. Each archive restored the canonical SHA-256 and passed a full byte comparison. The hybrid archive includes the native transform program and the entropy coder. Its separate compressor is 294,169 bytes and includes the dictionary hints and the article-order residual. The decoder rebuilds the full word dictionary from the compressed Wikipedia representation.

## Restore the hybrid download

```bash
python3 densewiki-v0.0.5-enwik9-hybrid.pyz enwik9
sha256sum enwik9
```

Use a new output filename. The expected XML SHA-256 is `159b85351e5f76e60cbe32e04c677847a9ecba3adc79addab6f4c6c7aa3744bc`. The downloadable archive's own SHA-256 is `836850e1c4895b2d089d81f9e5927bc425b1f33f5f64bcb122d4bb84870d6aa8`.

The x86-64 Linux download runs with Python 3.11+, libarchive.so.13 and the system C/C++ runtimes. The bundled native preprocessor needs x86-64-v3 (AVX2 and FMA). Both native helpers import glibc symbols through 2.34. The preprocessor also imports GLIBCXX_3.4.26. Set `TMPDIR` to an executable, disk-backed directory with several GiB available for intermediate files. The decoder creates and removes its own private work directory and publishes the restored file after verification.

## Reproduce the hybrid

```bash
sha256sum -c --quiet SHA256SUMS
python3 hybrid/build.py ../rebuilt-comp.pyz
python3 hybrid/benchmark.py ../rebuilt-comp.pyz ../enwik9 ../hybrid-benchmark
```

Run these from the extracted project on Linux with GCC 12+ or a compatible C++20 compiler, libarchive.so.13 and Python 3.12+ (or Python 3.11 with tarfile extraction filters) for building. The compressor is already included at `release/hybrid/comp.pyz`. For a direct encode, run `python3 release/hybrid/comp.pyz ../enwik9 ../enwik9-hybrid.pyz`. This profile accepts the canonical enwik9 corpus. For other inputs, use the DWX4 CLI.

## Reproduce the article experiments

```bash
make -B -C dwx4
make -C dwx4 test
python3 tools/film_sample.py ../enwik9 ../film-pages.xml
python3 dwx4/test.py dwx4/dwx4 --film-sample ../film-pages.xml
python3 dwx4/benchmark.py ../film-pages.xml ../film-pilot --profile film
python3 dwx4/benchmark.py ../enwik9 ../fact-bench --profile facts
python3 dwx4/benchmark.py ../enwik9 ../link-bench --profile links
python3 dwx4/benchmark.py ../enwik9 ../combined-bench --profile article
```

The film-only sample saved 22,972 bytes from infobox references. On all of enwik9, each tested article-local version grew the Wiki stream. The new profiles are opt-in. The research report gives the size of every complete stream, including those tradeoffs. The native Size and Prize candidates from v0.0.4 remain under `release/size` and `release/prize`.

[Measurements and interpretation](RESEARCH.md) | [Machine-readable results](results/enwik9-v0.0.5.json) | [DWX4 and DWX5 formats](dwx4/FORMAT.md) | [v0.0.4 results and native build instructions](HISTORY-v0.0.4.md).

## Credits

DenseWiki's article transforms and hybrid driver are GPL-3.0-only. The new driver calls cmix-neif 2.0's file stages in upstream order, including its deterministic census arithmetic. DWX4 uses libarchive's PPMd implementation. The supplied upstream source package, original notices, Wikipedia attribution and license texts accompany this release. [Native credits](upstream/EX2-NOTICE.md) | [Training attribution](upstream/TRAINING-ATTRIBUTION.md) | [License](LICENSE).
