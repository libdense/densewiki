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

## Article profiles in v0.0.5

The article profiles use the same solid 7z member and executable footer. The member begins with `DWX5`, the Wiki base byte 219 and one additional flag byte before the original length. The default `wiki` encoder continues to write `DWX4`.

| Profile | Additional flag byte | Article-local operation |
|---|---:|---|
| film | 5 | Infobox Film facts |
| facts | 1 | Infobox and taxobox facts |
| links | 2 | Recent link targets |
| article | 3 | Facts, then recent link targets |
| facts-select | 9 | Long facts after excluding existing title substitutions |
| links-select | 10 | Long repeated targets outside numeric-template candidate lines |
| article-select | 11 | Both selective operations |

An active article frame extends the ordinary header after its raw length. It stores the number of internal cuts, the transformed byte length before each successive cut and the total article-transformed length. The length after title substitution follows. Cuts separate fragments joined by the topic scheduler when the next page opener is absent or the previous line is incomplete. At a cut, frame boundary or visible page boundary the appropriate local tables start empty. Article rules operate before title, row, markup and word coding. Each decoder reverses that order.

The regular profiles use frame type `B` for the extended header. Selective profiles use `A` for extended frames and the original `B` header for frames with no substitutions. Only references on lines after an article opener can use the recent-link table. A valid plain or piped link contributes its exact target of up to 512 bytes. A hit is NUL followed by 32 plus rank for a complete plain link, or 64 plus rank for a link up to its first pipe. Ranks start at zero. Every recognized target moves to the front of the 32 slots, even on a literal emission. Literal NUL bytes double.

A recognized box can establish up to 64 unique exact spellings of 4 to 96 bytes. Field names select the kinds of facts to learn. Both linked targets and plain display names can supply spellings. Unlinked scalars can also supply phrases such as places and dates. The scanner tracks nested templates before closing the outer box. Later text can substitute a stored spelling with byte 13 and 32 plus its insertion index. The encoder chooses the longest exact match at the current position. Literal byte 13 doubles. Surrounding bytes, including XML escaping, case, spacing, link labels and punctuation, travel through the reversible pipeline.

The selective fact rule requires at least eight bytes and rejects values the current title coder would replace. The selective link rule requires at least 16 bytes and leaves the existing numeric-template candidate lines intact. The code always learns the literal link when a reference is declined.

The reader checks the 7z extent, page permutation, frame lengths, frame CRCs and final byte count. A bounded streaming read is the normal path. If libarchive reports a truncated 7z data stream, the reader retries the same physical extent through a read-only file mapping and runs the same checks again. A dirty or incomplete destination is never published. The mapping can increase resident memory on this retry.
