# DenseWiki v0.0.5 experiments

## Native preprocessing with fast PPMd

The upstream intermediate contains 501,062,281 bytes. Its SHA-256 is `c35d3073eeba70f22a2e08a50202b53eb95466e3e9f1f2702f6f9b3f96fd8718`. Its length and first 16 hexadecimal hash digits match the upstream training manifest. Its first 65,536 bytes also match the earlier independent prefix decoded from the native Prize archive. Replacing the expensive predictor with DWX4 Wiki's PPMd coder produced the following sizes.

| Item | Bytes |
|---|---:|
| Preprocessed Wikipedia | 501,062,281 |
| Solid 7z member and container | 169,501,273 |
| Decoder programs, launcher and packaging in the archive | 206,496 |
| Runnable hybrid archive | 169,707,769 |
| Separate complete compressor | 294,169 |
| Archive plus compressor | 170,001,938 |

The word dictionary, contributor names and reconstruction data travel in the transformed stream or in the charged program. Decompression reconstructs the dictionary from its stored article and restores the page order from the recovered page IDs. The 47,166-byte hint file and 40,694-byte article-order residual are encoder inputs. Their compressed entries, metadata and all extractor code are counted in the separate compressor. No trained model weights are used. The public decoder ran in a fresh working directory with the archive and system runtimes as its inputs.

| Build | Runnable archive, bytes | Archive + compressor, bytes | Encode / restore | Peak RSS, encode / restore |
|---|---:|---:|---:|---:|
| v0.0.4 DWX4 Wiki | 202,901,735 | 203,015,143 | 137.2 / 135.3 s | 30.8 / 25.9 MiB |
| v0.0.5 cmix-neif + PPMd | 169,707,769 | 170,001,938 | 376.7 / 228.2 s | 1,703.4 / 1,188.5 MiB |

The combined saving is 33,013,205 bytes after charging both distinct executables. Timings include input/output and scratch I/O. The hybrid checks the XML and intermediate hashes inside the measured commands. DWX4 packages its runnable archive in a separate 0.151-second step. Independent verification ran outside the timers. Each command and its workers shared one logical CPU. Peak RSS is the Linux high-water mark for the largest individual process. Shared libraries, file cache and temporary files have different accounting.

The entropy coder alone was timed separately on the exact 501,062,281-byte representation. Packing reproduced the same 7z payload and unpacking reproduced the same intermediate SHA-256.

| PPMd alone | Seconds | Peak RSS, MiB |
|---|---:|---:|
| pack | 95.9 | 18.5 |
| unpack | 107.5 | 18.6 |

The total command times above use process start and completion. Named scratch files in the hybrid's private directory reached 1,997,625,963 bytes during encode and 1,999,799,005 during restore. The sampler excludes unnamed temporary files and the destination. These are observed lower bounds on total disk use.

On this host `/tmp` is tmpfs. The upstream C library calls for unnamed temporary files use that mount even with the wrapper's named scratch on disk. Two additional native-stage runs sampled allocated blocks of open, unlinked files on that device every 50 ms. Process RSS alone omits that storage. The last column is the largest simultaneous sample of process RSS plus allocated tmpfs file bytes. It excludes disk-backed page cache.

| Native stage | Peak unnamed /tmp files, MiB | Peak simultaneous RSS + unnamed /tmp, MiB |
|---|---:|---:|
| forward | 775.6 | 1,703.5 |
| inverse | 0.0 | 1,188.6 |

```bash
python3 hybrid/scratch_audit.py release/hybrid/comp.pyz --xml ../enwik9
python3 hybrid/scratch_audit.py ../densewiki-v0.0.5-enwik9-hybrid.pyz
```

## Infobox facts and repeated link targets

The shared-payload idea in Chapter 38 of Merlin Numa's *Dense-Region MMO Server Architecture* suggests a direct Wikipedia test. Once a film infobox has spelled out a director, the decoder can copy those exact bytes wherever the name recurs later in the page. A short reference still costs something under PPMd. We measured that cost on 1,118 complete film pages (9,162,172 bytes) and on the full dump using the same coder. In *Jaws (film)*, the exact spelling `Steven Spielberg` occurs eight times after the infobox.

The film selector preserves original XML and page order. Its SHA-256 is `3c89d6cfb611abf807fb7e2bd25d57b8c2c8fc5cd8141bee9f8c41bb03cf80d4`. The broad facts profile also tries cast, writers, places, dates, and selected taxonomic fields. Box counters refer to recognized template occurrences. A page can contain several. The link profile keeps the last 32 distinct exact targets in most-recently-used order. On replacement it reproduces a plain or piped link, including its delimiters. Capacity, input fragments and malformed target rules affect the number of usable references.

| Profile | Full stream, bytes | Change vs Wiki | Film stream, bytes | Change vs film Wiki | Full fact references | Full link references |
|---|---:|---:|---:|---:|---:|---:|
| wiki | 202,788,311 | +0 | 2,072,961 | +0 | 0 | 0 |
| film | 202,797,615 | +9,304 | 2,049,989 | -22,972 | 26,115 | 0 |
| facts | 202,822,238 | +33,927 | 2,050,169 | -22,792 | 200,965 | 0 |
| links | 203,293,397 | +505,086 | 2,064,558 | -8,403 | 0 | 809,860 |
| article | 203,324,839 | +536,528 | 2,051,083 | -21,878 | 200,965 | 788,773 |
| facts-select | 202,806,553 | +18,242 | 2,051,759 | -21,202 | 56,137 | 0 |
| links-select | 202,998,672 | +210,361 | 2,074,555 | +1,594 | 0 | 114,684 |
| article-select | 203,001,777 | +213,466 | 2,052,913 | -20,048 | 56,137 | 112,734 |

A positive change means a larger stream. Each row restores its input exactly. Packaging adds 133,952 bytes to every released article CLI stream, including the complete executable and trailer. Every archive was also tested through its standalone entry point. The low-memory baseline stream has the same SHA-256 as v0.0.4 Wiki.

The broad link pass emitted 809,860 exact references. Numeric-template hits fell from 613,332 to 559,831. DWX4 excludes lines containing a literal NUL from its numeric templates, and the new link token uses that byte. The selective pass preserves eligible numeric lines and only substitutes targets of at least 16 bytes. It reduced the link penalty to 210,361 bytes. Infobox references can also displace an existing one-byte page-title substitution. The selective facts pass skips short values and spellings the title coder already predicts. Its full stream still grew by 18,242 bytes.

On film pages alone, shared facts cut the stream by 22,972 bytes (1.11%). In the full dump, the film-only rule grew the stream by 9,304 bytes. A separate control grouped film pages inside each existing reorder window. Grouping alone produced 202,813,746 stream bytes. With film facts it produced 202,828,774, another 15,028 bytes. Both restored the complete canonical input. The optional patch reproduces those two comparisons.

```bash
cp -a dwx4 ../film-order-build
patch --batch -d ../film-order-build -p1 < experiments/film-order/film-order.patch
make -B -C ../film-order-build
python3 dwx4/benchmark.py ../enwik9 ../grouping-control --binary ../film-order-build/dwx4 --profile film-order
python3 dwx4/benchmark.py ../enwik9 ../grouping-with-facts --binary ../film-order-build/dwx4 --profile film-group
```

## Verification

The hybrid was built twice from the bundled sources. Its independently generated archive matched byte for byte. Full enwik9 restored to `159b85351e5f76e60cbe32e04c677847a9ecba3adc79addab6f4c6c7aa3744bc`. The published archive's SHA-256 is `836850e1c4895b2d089d81f9e5927bc425b1f33f5f64bcb122d4bb84870d6aa8`. The compressor's SHA-256 is `b533780aee02e20ddb72dc053c2cc9118881b15c4ab09cb82fde8b8f8c773e61`.

The CLI passed 150 fixture/profile round trips plus tests for the 32-target eviction boundary, nested templates, literal marker bytes, page/frame boundaries, damaged inputs, existing destinations and executable archives. Old and new CLIs also read each other's regular Wiki stream of the complete *Jaws (film)* page. The general facts film-sample stream exposed a libarchive read-size issue. With 64 KiB compressed-input chunks the system library reported truncated data. Reading the same bytes contiguously restored all 9,162,172 sample bytes. The released reader retries this case without changing the archive or skipping any CRC check. The full-corpus article streams were repackaged and byte-compared with this released reader. The original native Size and Prize archives retain their v0.0.4 validation status.

[Detailed JSON](results/enwik9-v0.0.5.json) | [Previous full-corpus benchmark](results/enwik9-v0.0.4.json).
