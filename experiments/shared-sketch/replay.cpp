// SPDX-License-Identifier: GPL-3.0-only
// Differential storage test. Sketches come from every input block. They are
// diagnostic values, independent of the transformer's projections.
#include "densewiki_sketch.h"
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

using densewiki::BucketSlot;
struct OldSlot { uint32_t e1, hi; uint64_t lo; };
static_assert(sizeof(OldSlot) == 16, "reference slot layout");
#ifndef DENSEWIKI_TEST_WIDTH
#define DENSEWIKI_TEST_WIDTH 63
#endif
constexpr unsigned bucket_width = DENSEWIKI_TEST_WIDTH, ring = 1024;
using Table = densewiki::SketchTable<256, bucket_width, ring>;

static uint64_t permute(uint64_t x) {
    x = (x ^ (x >> 30)) * UINT64_C(0xbf58476d1ce4e5b9);
    x = (x ^ (x >> 27)) * UINT64_C(0x94d049bb133111eb);
    return x ^ (x >> 31);
}
static void check(bool ok) {
    if (!ok) { std::fputs("cache layouts differ\n", stderr); std::exit(1); }
}
int main(int argc, char **argv) {
    if (argc != 2) { std::fputs("usage: replay FILE\n", stderr); return 2; }
    FILE *in = std::fopen(argv[1], "rb");
    if (!in) { std::perror(argv[1]); return 1; }
    std::vector<OldSlot> old(Table::slots);
    auto *compact = static_cast<BucketSlot *>(std::calloc(1, Table::bytes));
    if (!compact) return 1;
    std::array<unsigned char, 4096> block;
    uint64_t bytes = 0, checked = 0, stale = 0, empty = 0, recent = 0, evictions = 0, signature = 0;
    unsigned events = 0;
    while (const size_t count = std::fread(block.data(), 1, block.size(), in)) {
        uint64_t hash = UINT64_C(14695981039346656037);
        for (size_t j = 0; j < count; ++j) hash = (hash ^ block[j]) * UINT64_C(1099511628211);
        const auto id = events++;
        bytes += count;
        const uint64_t lo = permute(hash);
        const uint32_t hi = (uint32_t)permute(~hash);
        Table::store(compact, id & (ring-1), lo, hi);
        for (unsigned t = 0; t < 16; ++t) {
            // Cold buckets, hot buckets and repeated probes force stale IDs, ties and evictions.
            const auto index = t * 16 + ((id % 137 < 120) ? 0u : unsigned(permute(lo + t) & 15));
            const auto offset = index * bucket_width;
            unsigned first = 0;
            for (unsigned u = 1; u < bucket_width; ++u)
                if (old[offset+u].e1 < old[offset+first].e1) first = u;
            check(first == Table::oldest(compact+offset));
            evictions += old[offset+first].e1 != 0;
            old[offset+first] = {id + 1, hi, lo};
            compact[offset+first].e1 = id + 1;
        }
        for (unsigned probe = 0; probe < 3; ++probe) {
            const auto offset = unsigned(permute(hash ^ probe) & 255) * bucket_width;
            for (unsigned u = 0; u < bucket_width; ++u) {
                const OldSlot &s = old[offset+u];
                check(compact[offset+u].e1 == s.e1);
                if (!s.e1) { ++empty; continue; }
                const unsigned entry = s.e1 - 1;
                if (id - entry >= ring) { ++stale; continue; }
                if (id - entry < 3) { ++recent; continue; }
                const unsigned hm = __builtin_popcountll(lo ^ s.lo) + __builtin_popcount(hi ^ s.hi);
                check(Table::distance(compact, entry, lo, hi) == hm);
                signature = (signature ^ (uint64_t(entry) << 8) ^ hm) * UINT64_C(1099511628211);
                ++checked;
            }
        }
    }
    if (std::ferror(in) || std::fclose(in)) return 1;
    std::free(compact);
    std::printf("{\"bytes\":%llu,\"events\":%u,\"distances_checked\":%llu,\"expired\":%llu,"
                "\"empty\":%llu,\"too_recent\":%llu,\"evictions\":%llu,\"output_signature\":\"%016llx\""
                ",\"reference_table_bytes\":%zu,\"candidate_table_bytes\":%zu}\n",
                (unsigned long long)bytes, events, (unsigned long long)checked, (unsigned long long)stale,
                (unsigned long long)empty, (unsigned long long)recent, (unsigned long long)evictions,
                (unsigned long long)signature, Table::slots*sizeof(OldSlot), Table::bytes);
}
