# DWX4

DWX4 uses a single solid 7z member named `DWX4`. The wiki profile uses libarchive PPMd. The lean profile uses LZMA2 at level 1. Both use the same reconstruction rules. The member starts with the four ASCII bytes DWX4, a profile byte, the original byte count as little-endian uint64, and a vocabulary count. Each vocabulary entry starts with a one-byte length followed by lowercase ASCII letters. Unsigned variable-length integers elsewhere use least-significant seven-bit groups first and the high bit as a continuation flag.

| Profile | Wire byte | Transform |
|---|---:|---|
| raw | 0 | Original bytes in checked frames |
| words | 8 | One vocabulary for the file, exact capitalization and recoverable spaces |
| fields | 9 | Words plus structural row groups |
| templates | 11 | Fields plus a bounded cache of numeric sentence patterns |
| topics | 27 | Templates plus page reordering |
| titles | 91 | Topics plus page-title references |
| wiki | 219 | Titles plus common wiki punctuation and XML entity spellings |
| lean | 251 | All wiki transforms, 8,192 vocabulary entries, 256 KiB frames and LZMA2 |

A `P` frame carries a length-prefixed schedule. The schedule records the number of spans, each span's length in original order, and the permutation as zigzag-coded index deltas. The decoder checks the permutation for completeness and duplicates. A window holds at most 128 MiB of original positions and 16,384 spans. The encoder scans 512 KiB slabs, keeps descriptors in memory and rereads the spans from the input file. The decoder seeks in its output to restore order. Fragmentary pages, arbitrary binary input and the truncated final page of enwik9 use the same representation.

A `B` frame starts with the original size. Profiles that share titles then store the size after title substitution. The remaining header is the coded byte count and the CRC-32 of the original block, using the standard reflected IEEE polynomial. A lone `E` closes the member. DWX4 checks the completed input byte count and the 7z member and extent. The CLI publishes the output from a sibling temporary file after successful decoding.

The encoder applies these transformations in order.

1. It learns a bounded shared vocabulary from the input. The decoder gets the selected entries in its header. Stored word ranks handle lowercase, title case and uppercase. The encoder can omit a single space where the adjacent word reference lets the reader restore it.
2. It groups pages with shared template or category labels. Redirects, census pages and image pages have separate groups. The encoder stores the exact order schedule. Hashes can change the grouping decision, while stored lengths and the permutation determine all output positions.
3. Inside a frame, a title line establishes the exact title. Six possible references cover the full title, a version without a parenthetical or comma qualifier, a version without a namespace, and their initial-lowercase variants. Explicit escapes preserve literal control bytes. A new page or frame resets the title state.
4. It stores each line's route. Repeated XML wrappers and fixed lines have dedicated codes. Other lanes carry the original spelling of article text, metadata, redirects, categories and interlanguage links. An incomplete line at a frame boundary is recoverable from its length.
5. Lines with multiple numbers can reuse a previous line pattern in a 2,048-slot cache. A hit requires equality of the complete pattern. Number strings preserve commas, decimal points and leading zeroes. The layout records which cache slot supplies the fixed text. On a miss, the complete line passes through. Both directions build the same cache in the original within-frame row order.
6. Short codes represent common markup spellings. The lexical coder then applies the shared vocabulary to the grouped tape. The final entropy coder sees one continuous stream across frame boundaries.

The runnable Linux archive consists of the DWX4 CLI, the complete 7z stream, the executable prefix length in eight little-endian bytes, and the eight-byte trailer `DWX4-SFX`. The CLI can read an ordinary DWX4 stream or unpack the payload of a runnable archive built on another supported Linux system.
