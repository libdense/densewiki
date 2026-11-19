// SPDX-License-Identifier: GPL-3.0-only
// DenseWiki, 2026-11-19. The 96-bit sketch is identical in every bucket that
// indexes an insertion. Bucket order and insertion IDs remain observable.
#ifndef DENSEWIKI_SKETCH_H
#define DENSEWIKI_SKETCH_H

#include <cstddef>
#include <cstdint>

namespace densewiki {
struct BucketSlot {
    std::uint32_t e1;
};
static_assert(sizeof(BucketSlot) == 4, "bucket ID must be 4 bytes");

template <std::size_t Buckets, unsigned Width, unsigned Ring>
struct SketchTable {
    static_assert(Buckets > 0 && Width > 0 && Ring > 0, "empty geometry");
    static_assert((Ring & (Ring - 1)) == 0, "ring size must be a power of two");
    static constexpr std::size_t slots = Buckets * Width;
    static constexpr std::size_t index_bytes = slots * sizeof(BucketSlot);
    static_assert(index_bytes % alignof(std::uint64_t) == 0, "align the 64-bit plane");
    static constexpr std::size_t bytes = index_bytes + std::size_t(Ring) * 12;

    static std::uint64_t *low(BucketSlot *p) {
        return reinterpret_cast<std::uint64_t *>(p + slots);
    }
    static std::uint32_t *high(BucketSlot *p) {
        return reinterpret_cast<std::uint32_t *>(low(p) + Ring);
    }
    static void store(BucketSlot *p, std::uint32_t ring_index, std::uint64_t lo, std::uint32_t hi) {
        low(p)[ring_index] = lo;
        high(p)[ring_index] = hi;
    }
    // The caller applies the original live-entry and minimum-distance checks first.
    static unsigned distance(BucketSlot *p, std::uint32_t id, std::uint64_t lo, std::uint32_t hi) {
        const std::uint32_t i = id & (Ring - 1);
        return __builtin_popcountll(lo ^ low(p)[i]) + __builtin_popcount(hi ^ high(p)[i]);
    }
    static unsigned oldest(const BucketSlot *bucket) {
        unsigned first = 0;
        for (unsigned i = 1; i < Width; ++i) {
            if (bucket[i].e1 < bucket[first].e1) first = i;
        }
        return first;
    }
};
}
#endif
