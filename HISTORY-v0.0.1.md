# v0.0.1 measurements and experimental source

## The comparison that determined the target

The supplied Tufazip v2 decoder lists a 100,958,324-byte coded file. Its 4,430,029-byte decoder package brings the Large Text Compression Benchmark total to 105,388,353 bytes. Its published run used two NVIDIA B200 GPUs. The November 19 benchmark ranks Ex-Girlfriend 2.0 first with an 88,983,124-byte self-extracting archive. Adding its standalone compressor for the Hutter comparison gives 93,040,255 bytes. That was the reference to beat. The Hutter score for a self-extractor is the compressor plus the archive plus any required option bytes. LTCB charges a self-extractor only once. [Benchmark and methods](https://www.mattmahoney.net/dc/text.html), [official rules](https://hutter1.net/prize/hrules.htm).

Ryan Landay's Ex-Girlfriend 2.0 extends Marcus Woelk's cmix-neif 2.0. It widens retrieval, adds two more semantic caches keyed on layer 12 and a different sketch seed, spreads online fast-weight updates over transformer blocks 4 through 15, and carries BITLSTM state across windows. The trained weights come from Woelk, who continued training from Vladimir Malinovskii's cmix-neif-beehive weights. Vladimir Ivanov supplied the earlier transformer framework. David Freelan's cmix-obias contributed the BITLSTM method. The training attribution specifically identifies the byte vocabulary, enwik9 training data, format lineage and separate terms for Wikipedia excerpts. We verified that the attribution at the requested main-branch link matched the copy in the v2.0 source tar. SHA-256 is `c4313830fbc0e4a6f6f6e1a5c61c14323e61a18b04148049bee394ae4757e808`. [Training attribution](https://github.com/rlanday/ex-girlfriend/blob/main/training/ATTRIBUTION.md), [tagged source](https://github.com/rlanday/ex-girlfriend/tree/v2.0), [full-run evidence](https://github.com/rlanday/ex-girlfriend/releases/tag/v2.0).

## Where 142 bytes went

Both released entries use the same 12,311-byte startup image. DenseWiki fits a new causal integer-count mixture to this executable data. The Wikipedia bitstream stays byte-identical to its parent. Every observed bit updates the selected contexts once. Candidate weight vectors reuse the same observed count trace. The native decoder and model constants are part of each scored executable, so selection minimizes actual linked bytes.

| Component in each executable | Original | DenseWiki | Bytes saved |
|---|---:|---:|---:|
| Coded startup image | 7,162 | 7,110 | 52 |
| Headers, constants and startup code | 757 | 738 | 19 |
| Complete startup block | 7,919 | 7,848 | 71 |

The search evaluated 100 mixtures over context masks and byte/bit groups, 300 counter/branch-transform settings, and 144 fitted variants of the best settings. We linked each of these 544 choices with both `-Os` and `-Oz`. A single bank of nine weights won. The smallest coded stream alone did not select the smallest executable. Its complete ranking and winner are in `results/model-search.tsv` and `results/v0.0.1/policy.json`. This is fitting fixed bytes that the decoder is required to carry. Its generalization to other executable images has not been measured.

To replay the search, use Python with NumPy and SciPy (the release used 2.3.5 and 1.17.0 respectively), GCC and GNU ld on x86-64 Linux. Run from the release root and supply new trial directories. Release artifact reconstruction with the chosen policy uses only Python's standard library and the C toolchain.

```bash
cc -O3 -std=c11 src/mix.c -o ../densewiki-mix
python3 tools/fit.py ../densewiki-mix experiments/startup.bin ../dw-mixtures
python3 tools/tune.py ../densewiki-mix experiments/startup.bin ../dw-counters
python3 tools/select_policy.py ../dw-mixtures ../dw-counters ../dw-selection
cmp results/model-search.tsv ../dw-selection/model-search.tsv
```

For both profiles we compared every byte beyond the changed startup block with the published files. The generated archive prefix is exactly the decoder prefix emitted by the candidate compressor. Each candidate was run and its actual unpacked native image compared in full with its parent's unpacked image. The short, variable trailer was separately checked to contain the correct path to the launched executable. Its encoder and decoder start from these same respective native images. The size profile retains all 85,039,910 coded Wikipedia bytes, the 3,744,629-byte weights and the original eight-byte trailer. The prize profile retains its own 85,417,870-byte stream. Each upstream model's published full run remains the source for the end-to-end result. `tools/roundtrip.py` produces independent candidate evidence when run to completion.

## Storing a semantic sketch once

The source's semantic cache inserts each key into 16 hash tables. The same 96-bit sketch was written into every bucket alongside a 32-bit insertion ID. Chapters 38 and 43 of the supplied dense-region MMO book describe producing one shared representation when the same payload has many recipients. Here the recipients are index buckets. DenseWiki stores the sketch once in two packed planes indexed by the key's ring slot. The buckets store only insertion IDs. The search still checks expired and too-recent IDs before reading the shared sketch, and preserves bucket order and first-minimum eviction ties. More indirect reads may cost CPU time.

| Experimental arm | Entries/bucket | Original affected bytes | New affected bytes | Difference |
|---|---:|---:|---:|---:|
| `size-shared`, per cache | 63 | 4,227,858,432 | 1,459,617,792 | 2,768,240,640 fewer |
| `size-shared`, all three caches | 63 | 12,683,575,296 | 4,378,853,376 | 8,304,721,920 fewer |
| `prize-shared`, one cache | 15 | 1,006,632,960 | 452,984,832 | 553,648,128 fewer |
| `prize-47`, one cache | 47 vs. 15 | 1,006,632,960 | 989,855,744 | 16,777,216 fewer |

These are exact byte counts for the index and sketch storage at production dimensions. They exclude keys, model state, candidate buffers, page rounding and allocator overhead. Neither total process RSS nor remaining prize headroom can be read from this table. The two equal-width arms aim to preserve every prediction. The wider prize arm can select additional neighbors and **requires a fresh encode** before it has a compression score.

We compiled the patched upstream predictor translation unit for both baselines and for the 47-entry variant. The differential harness processed every byte of the canonical 1 GB file in 244,141 consecutive 4,096-byte blocks. It derives synthetic 96-bit sketches from those blocks and uses a smaller ring to force expiry, overwrite, collisions, ties and repeated selections. It compares IDs and ordered Hamming distances to the original 16-byte slot representation. It passed 8,189,212 distance comparisons at width 63, 5,982,273 at width 15 and 7,456,253 at width 47. The width-47 oracle also used width 47. These runs exercise the storage algorithm with corpus-derived data. Full transformer traces, production peak RAM, runtime, and complete candidate archive sizes are outstanding for all three experiments. None of these arms is enabled in either measured binary.

```bash
python3 tools/prepare_experiment.py prize-47 ../dw-prize47-src
mkdir ../dw-prize47-build
(cd ../dw-prize47-build && bash ../dw-prize47-src/build.sh)
python3 tools/roundtrip.py prize /absolute/path/to/enwik9 ../dw-prize47-run --encoder ../dw-prize47-build/comp9
```

Use the upstream build environment documented in the extracted tree for this production build. It uses the upstream startup packer. Report the archive and its actual built encoder together. Only compare the full pair after the fresh output matches the canonical input. For the isolated storage check, the release root is sufficient.

```bash
g++ -std=c++17 -O2 -DDENSEWIKI_TEST_WIDTH=47 experiments/shared-sketch/replay.cpp -o ../dw-replay
../dw-replay /absolute/path/to/enwik9
```

## Evidence from the other supplied work

| Input | How it affected this release |
|---|---|
| Plausible C11 codec | Built and round-tripped three cold 1 MB samples from the corpus and from the coded payload. The raw samples became 252,437, 111,876 and 152,099 bytes. All three previously coded samples grew above 1,002,000 bytes. |
| Babelsuite v0.0.2 | Its address-length accounting motivates charging an address, recipe and decoder together. A full-payload control found 7.99999785 bits per byte of empirical zero-order entropy. zlib level 9 expanded that stream by 25,951 bytes. The result applies to this control. |
| DSO v0.0.9 and Eclipse v0.0.61 | Adopted DSO's idea of evaluating candidate changes against an explicit cost, and Eclipse's discipline of testing the exact domain of a claim. Here the cost is the linked executable plus archive. Runtime identity, table allocation and final restored data each have their own checks. |
| Lithify v0.0.43 and Murmuration v0.0.16 | Separate the choice of neighbors from the cost of retrieving them. The equal-width representation and the 47-entry retrieval experiment can be compared independently. |
| Dense-weights and the two handoffs | The Lithify archive already contains dense-weights v0.0.26. Its G010 evidence gives equal next-token winners at 74/74 positions but exact visible vectors at 60/74. A range coder needs the same discrete interval at both ends on every bit. Those figures alone cannot establish that condition. The separate 300 MB package was unnecessary for v0.0.1. |
| OPSD paper and code | Student versus self-teacher accuracy is a candidate-ranking signal. A coding experiment would need a teacher available from the decoded prefix or a small transmitted student, and must measure true-symbol log loss and final bytes. This release charges no projected teacher gain. |
| Tufazip v2 | Provides a GPU-based external comparison and a reproducible decoder specification. The two released profiles run on CPU. |

The full zlib and Plausible controls with offsets and hashes are in `results/payload-probe.json`. `tools/payload_probe.py` reproduces them using the original size reference archive and an optional Plausible executable compiled from the supplied project.

## Source and data notices

The DenseWiki code and modifications are distributed under GPL-3.0-only. The upstream packages retain their authors, notices and third-party licenses. Original code, training sources, weights, profile input, build scripts and their notices are included in full in `upstream/sources.tar.xz`. The compressor descends from Byron Knoll's cmix and the projects credited in `upstream/EX2-NOTICE.md`. The book, private DSO kit, dense-weights and other user projects were research inputs. Their source packages are not redistributed here.

The compressed enwik9 text is by Wikipedia contributors. Its source is the English Wikipedia dump dated March 3, 2006. The upstream training attribution records GFDL / CC-BY-SA for the Wikipedia excerpts included with its source. Article titles and revision IDs in the restored XML identify their sources. Contributors can be found through each article's page history at `https://en.wikipedia.org/w/index.php?title=ARTICLE_TITLE&action=history`. Copies of the GNU Free Documentation License and CC BY-SA 4.0 are included under `upstream/`. [Dataset and original dump information](https://www.mattmahoney.net/dc/textdata.html), [Wikipedia copyright information](https://en.wikipedia.org/wiki/Wikipedia:Copyrights), [upstream attribution](https://github.com/rlanday/ex-girlfriend/blob/main/training/ATTRIBUTION.md).

`upstream/sources.tar.xz` contains the exact decompressed source tars of the two public releases, compressed together for distribution. Their published gzip SHA-256 hashes are `ef635459bba7a19b9582266d4b5a20451798891aa631a5e78b388fe93b1aedfa` (Ex-Girlfriend) and `62da32b97f9909ce5f2d4988a84e1b9cfbff4c9947538cbc6659a2915b024874` (cmix-neif). The source extraction tool verifies the decompressed tar digests. DenseWiki's original changes are in `src/`, `tools/` and `experiments/shared-sketch/`. [Ex-Girlfriend release](https://github.com/rlanday/ex-girlfriend/releases/tag/v2.0), [cmix-neif release](https://marwoelk.de/cmix-neif-2.0/).
