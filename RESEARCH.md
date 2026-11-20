# DenseWiki v0.0.2 measurements

## What changed in the released pair

| Bytes in each startup | v0.0.1 | v0.0.2 | Difference |
|---|---:|---:|---:|
| Range-coded startup image | 7,110 | 6,841 | -269 |
| ELF, decoder code and model tables | 738 | 788 | +50 |
| Complete linked startup | 7,848 | 7,629 | **-219** |

Both native files carry a copy. The combined score drops by **438 bytes** from v0.0.1 and **580 bytes** from Ex-Girlfriend 2.0. The self-extracting archive singly drops by 219 and 290 bytes against those respective releases. The upstream 3,744,629-byte transformer container, the 85,039,910-byte Wikipedia stream and the eight-byte archive trailer are preserved in full.

## Selecting context from the topology of recent bytes

The book's chapters 38 and 43 describe building shared state once for recipients that need the same information. libdense 0.4.8.2's factored-workset notes describe representing a shared base with private differences. The experimental libdense_topo 0.2.0 module represents lattice neighborhoods using a list of offsets. DenseWiki applies these ideas to a sequence. An offset selects an earlier byte. A second mask selects the bits of that byte that a predictor can see. Histories that agree on the selected information contribute observations to the same group.

For example, the chosen policy includes both the most recent byte as an exact value and the same byte masked with `0xfc`. Values `0x48` and `0x49` contribute to the same coarse group but different exact groups. Another predictor uses the low three bits of that byte. At each byte position, the decoder looks up each selected group's tree once. It then walks the tree for the eight successive bits. The encoder and decoder learn from previously restored bytes in the same order.

The winner uses 24 stencils, a 20-bit hashed tree index and one bank of integer mixture weights. The count arena reserves 512 MiB of virtual address space at startup. The process touches entries on demand. Upstream model-run memory remains a separate measurement. The v0.0.11 skills package's bounded hash-search and histogram examples informed the implementation and tests. The shipped native program has no dependency on libdense.

| Model selection stage | Best complete startup |
|---|---:|
| Released v0.0.1 | 7,848 B |
| Best v0.0.2 search using whole prior bytes | 7,715 B |
| Best search allowing coarse byte classes | 7,640 B |
| Refit using counts observed in the deployed hash table | **7,629 B** |

The first search trained whole-byte stencils over all 256 subsets of the previous eight bytes. It considered independent contexts and the original hash layout as controls. The second search introduced byte classes, including 12 coarser masks over short stencils, and ranked each feature by the change in log loss when it was removed. These searches used the fixed 12,311-byte startup image. The table compares the best complete linked solution at each stage. It measures this particular image. The selection made 416 linked comparisons, then 100 more for the final weight refit. Every table byte and the complete native decoder were charged. The measured tables include compiler ties.

```bash
python3 experiments/context-stencils/fit.py ../octets.json
python3 experiments/context-stencils/byte_classes.py ../classes.json
python3 experiments/context-stencils/select.py ../octets.json ../selected --add ../classes.json
python3 experiments/context-stencils/refine.py ../selected/policy.json ../refitted
cmp results/policy.json ../refitted/policy.json
```

The training runs used GCC 14.2.0, Python 3.12.14, NumPy 2.3.5 and SciPy 1.17.0. The archived candidate sets can be passed directly to `select.py` to repeat linking without refitting them. [Octet candidates](results/stencil-octets.json), [class candidates](results/stencil-classes.json), [linked candidates](results/stencil-search.tsv), [refit](results/stencil-refit.tsv), [release policy](results/policy.json).

## A separate test on Wikipedia text

The word codec counts exact, case-sensitive ASCII words 3 to 64 bytes long in each 1 MiB block. A word is eligible when `(occurrences - 1) * (length - 2) > 32`. Each selected spelling appears once in the transmitted dictionary. The 96 most frequent words get one-byte references. Sorting common and remaining words lexically within their two tiers helps XZ compress the dictionary. The format escapes literal high bytes, preserves markup and punctuation, and chooses the smaller of a raw and transformed block in automatic mode. The decoder needs no outside vocabulary, normalization rules or network access.

The upstream training attribution identifies the profiling material as enwik9 excerpts. The upstream profiling file `input2` ends with the entire 50,051-byte file `input`. Removing that overlap leaves an 880,672-byte Wikipedia excerpt. The tail includes markup excerpts and an appended byte sequence. The two test inputs have disjoint positions in the fixture. The vocabulary threshold and layouts were explored on this material, so this is an in-sample result.

| Input | Continuous XZ stream | DWX2 auto stream | XZ with decoder | DWX2 with decoder | Runnable saving |
|---|---:|---:|---:|---:|---:|
| Wikipedia excerpt, 880,672 B | 256,204 | 247,974 | 256,587 | 249,424 | **7,163 B (2.79%)** |
| Profiling tail, 50,051 B | 8,348 | 8,350 | 8,731 | 9,800 | **-1,069 B** |

Runnable totals are measured Python ZIP applications with their respective decoder source and payload. Both use the installed Python runtime and its XZ implementation. The larger winning archive is included under `release/word-pilot/`. Each application ran in a fresh Python process and recreated the exact source bytes. The continuous XZ control has its own smaller decoder. A separate control holds the DWX2 decoder and framing fixed.

| Ordering / control on the 880,672-byte excerpt | Complete DWX2 stream |
|---|---:|
| Raw bytes, same block format | 256,222 B |
| Word references assigned by frequency | 249,370 B |
| Group words by their most frequent selected predecessor within each price tier | 249,302 B |
| Sort words lexically within each price tier | **247,974 B** |

The predecessor experiment instantiates a directed word co-occurrence graph. It saves 68 bytes against frequency order on this excerpt. Lexical order saves another 1,328 bytes. All three serialize the dictionary in full. These numbers apply to the XZ-based experiment. The enwik9 production bitstream still uses the upstream Wikipedia model.

```bash
python3 tools/prepare_experiment.py size-original ../size-source
python3 experiments/wiki-words/test_codec.py
python3 experiments/wiki-words/benchmark.py ../size-source ../wiki-words.json
cmp results/wiki-words.json ../wiki-words.json
```

The JSON includes SHA-256 hashes for both distinct inputs, every stream, every runnable archive and every restored output. Python and zlib versions can affect the ZIP packaging of decoder source. [Excerpt results](results/wiki-words.json).

## Verification limits

The build's reference conversion, offline coder/decoder, capture of unpacked native images, native emission of the decoder prefix, and extraction of the weights and entire Wikipedia bitstream each have a byte-identity check. The reference compressor and archive can be reconstructed in full from the shipped package. A fresh end-to-end decode of all one billion corpus bytes under v0.0.2 is outstanding. A bounded attempt to start the parent model on the 9.7 GiB release host reached model initialization and was terminated before the first buffered model-output block. Upstream's independent full-run receipt reports a byte comparison against canonical enwik9 and about 24.3 GiB peak RAM. The next direct test of the word codec is the full-corpus three-way comparison implemented in `experiments/wiki-words/full_corpus.py`. [Candidate native checks](results/native-checks.json), [size report](results/size.json), [upstream full-run receipt](upstream/ex2-verification.json).
