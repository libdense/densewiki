# DenseWiki v0.0.4 measurements

## What the book predicted correctly

Chapter 38 of Merlin Numa's *Dense-Region MMO Server Architecture* separates a reusable body from per-recipient details. Chapter 39 groups fields that change together. The libdense 0.4.4 research note on factored worksets retains one shared base plus exact exceptions. DWX4 applies these ideas to Wikipedia pages. When two census sentences have identical text around different numbers, the decoder reuses the whole sentence pattern and inserts the exact digit strings. A title such as `Lake Example (river)` can also supply `Lake Example` or its initial-lowercase variant. The compression transcript's deterministic replay principle applies to the numeric template cache. The stored row order and actual equality comparison are enough for both sides to recreate the same state.

In the final Wiki run, the encoder used 1,824,403 title references. Its 613,332 numeric-template hits covered 103,811,079 bytes of title-transformed line content. That coverage counts the lengths of matching lines. The measured compressed-byte contribution is in the table.

## Full-corpus ablation

| Step | Complete stream bytes | Saved at this step |
|---|---:|---:|
| Original XML, same framed PPMd backend | 219,177,276 | Baseline |
| One corpus-wide word table and case/space rules | 209,164,230 | 10,013,046 |
| XML fields and link-language rows | 208,534,385 | 629,845 |
| Exact numeric templates | 208,362,910 | 171,475 |
| Page order by shared topics | 205,874,624 | 2,488,286 |
| Page-title references | 203,506,076 | 2,368,548 |
| Wiki markup spellings | 202,788,311 | 717,765 |

Every row used a single continuous PPMd member and restored all 1,000,000,000 bytes. Each row adds to the previous configuration. Page order changes which sentences reach the numeric cache, so these marginal effects depend on the order of the experiment. The complete representation saves **16,388,965 stream bytes** over framed raw PPMd. A separate unframed libarchive control stored raw enwik9 in 219,169,689 bytes including its 7z container. The comparison with the v0.0.3 runnable archive combines the new representation, backend and executable packaging.

The handoff specifically asked whether v0.0.3 lost bytes by resetting XZ history. We extracted the actual LZMA2 members of all 954 shipped DWX3 blocks. The same 720,286,803 transformed bytes with a one-MiB dictionary used 249,684,076 independent raw LZMA2 bytes and 240,740,752 continuous bytes. The saving was **8,943,324 bytes**. These counts exclude DWX3 headers and XZ container overhead. Both paths restored the same transformed-byte hash. This separate control uses the older DWX3 representation. Its saving cannot be added to the DWX4 ladder.

```bash
python3 experiments/wiki-words/history_control.py ../densewiki-v0.0.3-enwik9-lowmem.pyz
```

## Which alternatives lost

A separate paid dictionary of full wikilink targets emitted 2,597,413 references but grew the Wiki stream from 202,788,311 to 203,266,235 bytes, a cost of 477,924 bytes. The shipped vocabulary codes repeat words cheaply already. A high hit count alone gave the wrong decision.

A block-local LZP pass used the last position following four bytes to copy matching passages without sending an offset. On the 8 MiB prefix, a minimum copy of eight bytes grew the word-and-row pilot from 2,082,085 to 2,109,675 bytes. At 64 bytes, the prefix saved 533 bytes, while the middle and late samples grew by 231 and 212 bytes respectively. Prefix, middle and late start at byte offsets 0, 429,000,000 and 903,000,000. The shipped design omits this pass.

The Lean branch also tried LZMA2 levels 2 and 3 on the same earlier 8,192-word, 256 KiB representation before title and markup substitutions. Level 1 used 245,257,125 stream bytes, level 2 used 238,861,539, and level 3 used 234,366,056. Encoder RSS rose from 18.36 MiB to 25.86 MiB and 40.86 MiB in those trials. The release keeps level 1 and gains additional bytes through title and markup reuse. All three experimental streams passed full comparisons.

## Actual memory and runtime

| Released executable archive | Bytes with program | Encode seconds | Standalone decode seconds | Peak RSS encode / decode |
|---|---:|---:|---:|---:|
| Wiki | 202,901,735 | 132.457 | 119.419 | 30.80 / 25.87 MiB |
| Lean | 238,629,600 | 114.514 | 32.157 | 14.96 / 7.58 MiB |

The release runs used GCC 14.2.0, libarchive 3.7.4 and Linux 6.18.57 on an AMD EPYC 9V74. Each process was pinned to one logical CPU. Other work used other logical CPUs. Encode and standalone decode times include file I/O and exclude verification. The runnable adds 113,424 bytes to either stream, including its trailer. The v0.0.3 benchmark recorded 339.824 s and 30.01 MiB for its CLI encode and 172.240 s and 16.00 MiB for its CLI decode. Those historical timings are stream measurements. Peak RSS excludes the filesystem cache. The final encodes used seekable scratch files on a disk-backed filesystem, while decode sought directly within its eventual output file.

A separate Lean decode with a small C launcher reported 6.94 MiB peak RSS and 31.270 seconds, with a complete byte comparison. The Python harness's fork can set a pre-exec high-water floor in the main table's Linux wait4 figures. All memory and time figures in this release concern these specific runs.

As one historical size reference, Matt Mahoney lists Boa 0.58b at 213,901,294 bytes including its program and about 17 MB of compression memory. His memory column is approximate and excludes temporary files. This is a published size comparison across different implementations and hosts. [Large Text Compression Benchmark](https://mattmahoney.net/dc/text.html).

## Native builds

A 32-bit displacement depends on where an instruction sits. The startup transform stores eligible signed 27-bit operands in a common image coordinate system before entropy coding and reconstructs the original displacements before execution. The flat 12,311-byte image contained 500 recognized operand shapes, representing 494 distinct original displacements and 166 distinct normalized values. Recognition is a reversible byte-pattern rule. It does not require an instruction disassembler.

The new mixer policy used 6,399 coded bytes for that flat image. The previous policy used 6,841. Including the inverse transform and model, the startup fell from 7,597 to 7,286 bytes. Both the compressor and the archive carry it, saving 622 combined bytes per profile. The complete compressed Wikipedia streams were identical to the respective parent streams, 85,039,910 bytes for Size and 85,417,870 bytes for Prize. The fresh native checks compare complete program images, suffixes, weights, payloads and decoder-prefix generation. The prize decoder reproduced 65,536 upstream model-stream bytes. Original XML and regenerated archive from a fresh multi-day native run remain unverified for these two builds.

[Native size checks](results/native-checks.json) | [Prize checks](results/native-checks-prize.json) | [Prize prefix](results/native-model-prefix-prize.json) | [Address counts](results/native-addresses.json).
