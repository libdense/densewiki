# DenseWiki v0.0.3 measurements

## What got smaller

The size-profile pair saved 64 bytes relative to v0.0.2 and 644 bytes relative to Ex-Girlfriend 2.0. The prize-profile pair saved 502 bytes relative to v0.0.2 and 644 bytes relative to cmix-neif 2.0. Each native program and archive uses the same 7,597-byte startup block, with profile-specific header fields. The program that runs after unpacking, pretrained weights and complete compressed Wikipedia stream match the corresponding upstream profile byte for byte.

| Profile | Archive bytes | Compressor bytes | Total bytes | Wikipedia stream inside archive |
|---|---:|---:|---:|---:|
| size | 88,982,802 | 4,056,809 | 93,039,611 | 85,039,910 |
| prize | 89,346,070 | 4,042,242 | 93,388,312 | 85,417,870 |

Prefix offsets, full SHA-256 values, suffix hashes, native image captures and no-argument startup checks are recorded in the release. The author-provided SHA-256 of the 89,346,392-byte original cmix-neif archive is `88dd7087404122d010261e6855afd88875d34dde1f0539377d3e832fc0f6b3fd`. [Size build](results/size.json), [prize build](results/prize.json), [original release directory](https://marwoelk.de/cmix-neif-2.0/).

## Native startup memory

The first stage hashes each byte history to a row of binary counts. v0.0.2's size profile addressed a 512 MiB table directly. v0.0.3 keeps a 4 MiB directory and gives a 512-byte row to a hash slot on its first use. Hash collisions still select the same row on both sides of the arithmetic coder. The 24 stencils over 12,311 bytes can allocate at most 295,464 rows. Including the directory and row zero, the reserved count arena is 148.27 MiB. The ELF loader supplies zero-filled pages, and the first stage releases the entire count arena before unpacking the inner executable.

| Profile and entry | v0.0.2 peak RSS (KiB) | v0.0.3 peak RSS (KiB) | Reduction (MiB) |
|---|---:|---:|---:|
| size, compressor | 1,771,008 | 1,530,268 | 235.10 |
| size, archive | 1,768,192 | 1,527,452 | 235.10 |
| prize, compressor | 1,538,048 | 1,529,884 | 7.97 |
| prize, decoder prefix only | 1,534,848 | 1,526,680 | 7.98 |

Each number is Linux `wait4` peak RSS for a separate single-CPU process through reconstruction and handoff of the native ELF. The test hook stops before the Wikipedia model's main function. The prize decoder's startup measurement used the complete executable prefix, and the separate native verification also exercised the full prize archive. [Startup memory](results/startup-memory.json), [size native checks](results/native-checks.json), [prize native checks](results/native-checks-prize.json).

## Lower-memory prize model

The experimental C++ model stores each semantic sketch once and shares it across buckets. Its five semantic-cache arrays use demand-zero base pages. PPMd starts with a 128 MiB resident pool and lets it grow to 1 GiB, backed by the same page file. The controller targets 8 GiB RSS before a 256 MiB safety margin. The original starts with 1 GiB and allows its pool to grow to 4 GiB. Other model allocations contribute to process RSS, and paging can affect runtime.

The fixture starts at offset 87,537 in the included upstream profiling input. The original bytes also occur at the same offset in canonical enwik9. A reversible escape maps the excerpt into the model's 208-byte alphabet. Both benchmark builds set the gate to its article-body state at entry, load the real trained weights, and use the upstream Compress and Decompress functions. Semantic insertion counts show that both models queried and populated the cache. The harness skips the full-corpus preprocessing pass. It uses the same GCC floating-point settings for both models. Each test uses a fresh single-core process.

| Original XML bytes | Model bytes | Identical encoded bytes | Cache inserts per run | Original encode/decode peak GiB | Lower-memory encode/decode peak GiB |
|---:|---:|---:|---:|---:|---:|
| 16,384 | 17,128 | 6,624 | 14,472 | 5.575 / 5.575 | 2.852 / 2.852 |
| 32,768 | 36,110 | 11,464 | 27,080 | 6.365 / 6.364 | 3.670 / 3.670 |
| 65,536 | 74,744 | 18,802 | 47,378 | 6.935 / 6.934 | 4.249 / 4.250 |

Both encoders produced identical bytes on every listed input, and each decoder restored the other encoder's stream to the exact original XML. Longer streams can touch more semantic pages and spill more PPMd data to disk. The 8 GiB controller setting has yet to be tested on a complete native enwik9 encode and decode. The downloadable scored pairs use the upstream inner models. [Cross-decode and memory receipts](results/model-memory.json).

## Full enwik9 text compression

DWX3 stores article bodies together within each 1 MiB block. It writes a count and metadata length, then reconstructs complete text fields in order. Bytes at an incomplete field boundary stay in the original part of that block. A second reversible transform gives capitalized and uppercase words access to lowercase dictionary entries. The encoder compares raw, vocabulary-only and combined representations, including their actual XZ byte cost. It limits the XZ dictionary to the block size, up to 1 MiB. Both codecs use Python and the standard library's XZ implementation.

| Full 1,000,000,000-byte corpus | Complete stream bytes | Bits per original byte | Single-process encode peak MiB | Single-process decode peak MiB |
|---|---:|---:|---:|---:|
| DWX2 | 255,483,667 | 2.043869 | 58.33 | 19.77 |
| DWX3 | 249,751,347 | 1.998011 | 33.69 | 15.67 |

DWX3 saved **5,732,320 bytes (2.24%)** on the full Wikipedia stream. Each single-process CLI run wrote its own archive and restored file, checked SHA-256, and compared all one billion output bytes to the reference. The independent block-parallel build produced the same stream hashes. The measurements above count the entire stream including its block headers and dictionaries. Python and its XZ runtime are installed dependencies. [Corpus verification](results/wiki-enwik9.json), [DWX2 single-process run](results/dwx2-enwik9-memory.json), [DWX3 single-process run](results/dwx3-enwik9-memory.json).

On the 880,672-byte prefix, the DWX3 stream used 246,694 bytes with vocabulary coding alone, 243,566 after folding capitalization, and 242,850 after grouping text fields as well. Thus field grouping saved another 716 bytes with the other settings held fixed. These settings were explored on the two small upstream fixtures before the full-corpus comparison.

| Input | DWX2 stream | DWX3 stream | DWX2 runnable | DWX3 runnable |
|---|---:|---:|---:|---:|
| wiki-prefix, 880,672 bytes | 247,974 | 242,850 | 249,424 | 244,862 |
| profiling-tail, 50,051 bytes | 8,350 | 8,302 | 9,800 | 10,314 |

Runnable sizes include the matching decoder source and ZIP framing. The larger new decoder increased the runnable size on the small tail even though it reduced the stream. [Excerpt benchmarks and ablations](results/wiki-words-v3.json).

## Verification boundary

The two ~93 MB scores use the native enwik9 profiles. Each was checked against a hash-pinned parent, including all unchanged compressed data and the complete restored program image. The native entry points were exercised in fresh directories. The DWX2 and DWX3 figures above have independent full-corpus round trips. Fresh full-corpus native peak memory, elapsed time and decoded output for DenseWiki v0.0.3 remain to be measured. Marcus Woelk reports 9.77 GiB for the original prize model's full encode and 9.75 GiB for its decode. Ryan Landay's size-profile receipt reports roughly 24.3 GiB. [cmix-neif 2.0](https://github.com/marwoelk/cmix-neif-2.0), [Ex-Girlfriend verification](upstream/ex2-verification.json).

## Connection to the project thesis

Merlin Numa's *Dense-Region MMO Server Architecture* describes grouping recipients and reusing a serialized payload in the foreword's core principle. The libdense research note `docs/research/factored-worksets-0.4.4.md` represents shared state with exact exceptions. In the native startup decoder, many visits to the same context use one physical counter row. In DWX3, a word can share a dictionary entry across case variants while marker bytes preserve its exact spelling. The block-level ablation above measures what the grouping contributed to one Wikipedia prefix. Every transformation in the shipped codecs has an exact inverse.

## Additional controls

The published and v0.0.3 prize archives were also started with no arguments in fresh directories. After model initialization, both emitted the same first 16,384 bytes from the actual range-coded stream, preceding inverse Wikipedia preprocessing. This adds a native model observation beyond image and payload equality. [Native prefix comparison](results/native-model-prefix-prize.json).

Reducing the inner native-program packer's table dimensions increased its encoded compressor-plus-decoder-prefix length by 698 bytes in the GCC control. The released native packages keep the original inner coder and use the sparse first-stage row layout. [Packer geometry trial](results/packer-geometry.json).

Continuous XZ at preset 6 produced 230,153,052 bytes and restored the full reference. [Measurement](results/continuous-xz-enwik9.json).

XZ in the v0.0.2 one-MiB block format produced 263,059,071 bytes and restored the full reference. [Measurement](results/blocked-xz-enwik9.json).

All 954 enwik9 blocks selected combined article-field and case coding. The single-process fixed `--mode wiki` encode reproduced the identical stream in 431.6 seconds with 32.08 MiB peak RSS. Automatic selection took 1,141.0 seconds on the same host. These wall times include concurrent independent work. [Fixed-mode run](results/dwx3-wiki-enwik9-memory.json).

The full standalone Python archive is 249,753,359 bytes. Its fresh decode restored all 1,000,000,000 input bytes with 15.75 MiB peak RSS. Its installed dependencies are Python and liblzma. [Standalone run](results/lowmem-runnable.json).
