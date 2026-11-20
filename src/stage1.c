/* SPDX-License-Identifier: GPL-3.0-only
 * Derived from Marcus Woelk's cmix-neif 2.0 stub_boot.c.
 * DenseWiki changes, 2026-11-19. The freestanding C decoder mixes integer
 * context counts and adapts them with the parameters selected offline.
 * The v0.0.2 layout reuses each history lookup across all eight bit decisions.
 * One loadable ELF segment contains the six-word upstream header at offset
 * 120, the model table, the startup code and the range-coded second stage.
 * The Linux entry code maps the original image and the count table, restores
 * the second stage and passes it the original process stack and header.
 */
#include <stdint.h>
#include <stddef.h>
#include "policy.h"

_Static_assert(BOOT_SHIFT == 64 - BOOT_TB, "BOOT_SHIFT must be 64-BOOT_TB");
_Static_assert(BOOT_NM > 0 && BOOT_NM <= 32, "unsupported context count");
_Static_assert(DW_BANKS >= 1 && DW_BANKS <= 256, "unsupported bank count");

#define STR_(x) #x
#define STR(x) STR_(x)

__attribute__((used, aligned(1), section(".cuthdr")))
volatile struct __attribute__((packed)) {
  uint32_t payload_off, comp_len, decode_len, image_len, bcj_split, dec_clen;   /* bcj_split: historical name of the cut point Nd */
} cut_hdr = { 0, 0, 0, 0, 0, 0 };

/* Each mask is followed in the table by its bank's weights at a fixed offset. */
__attribute__((used, aligned(1), section(".cutmodels")))
const unsigned char cut_models[(1 + DW_BANKS + DW_CLASSES) * BOOT_NM] = {
    BOOT_MASK_LIST, BOOT_WT_LIST
#if DW_CLASSES
    , DW_CLASS_LIST
#endif
};

__asm__(".section .rodata.s2blob,\"a\"\n.globl s2blob\ns2blob:\n.incbin \"" S2CM "\"\n.previous\n");


/* Decode the fixed image. Each observed bit updates the selected contexts. */
extern const unsigned char s2blob[];
__attribute__((used, noinline))
static void decode_startup(void) {
#if DW_TREE_BITS
    uint8_t *const counts = (uint8_t *)((uintptr_t)S2BASE + S2MEM);
#if DW_SPARSE
    uint32_t *const directory = (uint32_t *)counts;
    uint8_t *const slabs = counts + (4u << DW_TREE_BITS);
    uint32_t used = 0;
#endif
    uint8_t *rows[BOOT_NM];
#elif DW_EXACT
    typedef struct { uint64_t key; uint32_t row; } Entry;
    _Static_assert(sizeof(Entry) == 16, "directory layout");
    Entry *const directory = (Entry *)((uintptr_t)S2BASE + S2MEM);
    uint8_t *const counts = (uint8_t *)(directory + BOOT_NM * 32768u);
    uint32_t used = 0;
    uint64_t masks[BOOT_NM];
    uint8_t *rows[BOOT_NM];
    for (unsigned m = 0; m < BOOT_NM; ++m) {
        uint64_t mask = 0;
        for (unsigned j = 0; j < 8; ++j)
            if ((cut_models[m] >> j) & 1u) mask |= UINT64_C(255) << (8 * j);
        masks[m] = mask;
    }
#else
    uint8_t *const counts = (uint8_t *)((uintptr_t)S2BASE + S2MEM);
#endif
    uint8_t *const output = (uint8_t *)(uintptr_t)S2BASE;
    const uint8_t *stream = s2blob;
    uint32_t lo = 0, hi = UINT32_MAX, code = 0;
    uint64_t history = 0;
    for (unsigned i = 0; i < 4; ++i) code = (code << 8) | *stream++;
    for (unsigned pos = 0; pos < S2LEN; ++pos) {
#if DW_TREE_BITS
        for (unsigned m = 0; m < BOOT_NM; ++m) {
            uint64_t key = m + 1u, bytes = history;
#if DW_CLASSES
            const unsigned keep = cut_models[(1 + DW_BANKS) * BOOT_NM + m];
#else
            const unsigned keep = 255;
#endif
            for (unsigned mask = cut_models[m]; mask; mask >>= 1, bytes >>= 8) {
                if (mask & 1) {
#if DW_SHORT_KEYS
                    key = (key << 8) | (bytes & keep);
#else
                    key = ((key << 8) | (key >> 56)) ^ (bytes & keep);
#endif
                }
            }
            key ^= key >> 29;
            key *= UINT64_C(0x9e3779b97f4a7c15);
            const unsigned index = (unsigned)(key >> (64 - DW_TREE_BITS));
#if DW_SPARSE
            if (!directory[index]) directory[index] = ++used;
            rows[m] = slabs + ((size_t)directory[index] << 9);
#else
            rows[m] = counts + ((size_t)index << 9);
#endif
        }
#elif DW_EXACT
        for (unsigned m = 0; m < BOOT_NM; ++m) {
            uint64_t key = history & masks[m];
            Entry *bank = directory + m * 32768u;
            unsigned i = (unsigned)((key * UINT64_C(0x9e3779b97f4a7c15)) >> 49);
            while (bank[i].row && bank[i].key != key) i = (i + 1) & 32767u;
            if (!bank[i].row) {
                bank[i].key = key;
                bank[i].row = ++used;
            }
            rows[m] = counts + bank[i].row * 512u;
        }
#endif
        unsigned prefix = 1;
        for (unsigned b = 0; b < 8; ++b) {
            const unsigned group = ((pos >> DW_REGION_SHIFT) * DW_BIT_GROUPS) + (b >> DW_BIT_SHIFT);
            const uint8_t *weight = cut_models + (1 + group) * BOOT_NM;
#if !DW_TREE_BITS
            uint8_t *slots[BOOT_NM];
#endif
            unsigned n0 = BOOT_EPS, n1 = BOOT_EPS;
            for (unsigned m = 0; m < BOOT_NM; ++m) {
#if DW_TREE_BITS
                uint8_t *pair = rows[m] + 2 * prefix;
#elif DW_EXACT
                uint8_t *pair = slots[m] = rows[m] + 2 * prefix;
#else
                uint64_t key = prefix, bytes = history;
                for (unsigned mask = cut_models[m]; mask; mask >>= 1) {
                    if (mask & 1) key = key * UINT64_C(0x100000001b3) + (bytes & 255);
                    bytes >>= 8;
                }
                key = (key + m * UINT64_C(0x9e3779b97f4a7c15)) * UINT64_C(0x2545f4914f6cdd1d);
                uint8_t *pair = slots[m] = counts + 2 * (key >> BOOT_SHIFT);
#endif
                unsigned a = pair[0], b1 = pair[1];
                if (!a) b1 *= DW_BOOST;
                if (!b1) a *= DW_BOOST;
                n0 += a * weight[m];
                n1 += b1 * weight[m];
            }
#if DW_NARROW
            unsigned prob = (n1 << 12) / (n0 + n1);
#else
            unsigned prob = (unsigned)(((uint64_t)n1 << 12) / (n0 + n1));
#endif
            if (!prob) prob = 1;
#if !DW_TREE_BITS
            if (prob > 4095) prob = 4095;
#endif
            const uint32_t boundary = lo + (uint32_t)(((uint64_t)(hi-lo) * prob) >> 12);
            const unsigned bit = code <= boundary;
            if (bit) hi = boundary;
            else lo = boundary + 1;
            while ((lo ^ hi) < (UINT32_C(1) << 24)) {
                code = (code << 8) | *stream++;
                lo <<= 8;
                hi = (hi << 8) | 255;
            }
            for (unsigned m = 0; m < BOOT_NM; ++m) {
#if DW_TREE_BITS
                uint8_t *pair = rows[m] + 2 * prefix;
#else
                uint8_t *pair = slots[m];
#endif
                if (pair[bit] != BOOT_CAP) ++pair[bit];
                if (pair[bit ^ 1] > DW_KEEP) pair[bit ^ 1] = (pair[bit ^ 1] >> DW_DECAY) + DW_KEEP;
            }
            prefix = 2 * prefix + bit;
        }
        output[pos] = (uint8_t)prefix;
        history = (history << 8) | (uint8_t)prefix;
    }
#if DW_RELATIVE27
    /* Equal targets have one representation throughout the flat startup image. */
    for (unsigned i = 0; i + 4 < S2LEN;) {
        unsigned op = output[i++];
        if ((op & 254u) != 232u) {
            if (i + 4 >= S2LEN || !(op & 1u) || (output[i] & 199u) != 5u) continue;
            ++i;
        }
        uint32_t value;
        __builtin_memcpy(&value, output + i, sizeof(value));
        if (value + (1u << 26) >= (1u << 27)) continue;
        unsigned end = i + 4;
        value = ((value - end + (1u << 26)) & ((1u << 27) - 1u)) - (1u << 26);
        __builtin_memcpy(output + i, &value, sizeof(value));
        i = end;
    }
#elif DW_BRANCHES
    for (unsigned i = 0; i + 4u < S2LEN; ++i) {
        if ((unsigned)(output[i] - 232u) <= 1u) {
            uint32_t target;
            __builtin_memcpy(&target, output + i + 1, 4);
            target -= i + 5u;
            __builtin_memcpy(output + i + 1, &target, 4);
            i += 4;
        }
    }
#endif
}

__asm__(
  ".text\n"
  ".globl _start\n"
  "_start:\n"
  "  mov %rsp,%rbp\n"                   /* original sp (passed to stage 2) */
#if !DW_TREE_BITS
  "  sub $384,%rsp\n"
#endif
  #if !DW_ELF_ARENA
  /* mmap(S2BASE, S2MEM + table, RWX, PRIVATE|ANON|FIXED, -1, 0) */
  "  push $9\n  pop %rax\n"
  "  mov $" STR(S2BASE) ",%edi\n"
  "  mov $(" STR(S2MEM) "+" STR(BOOT_TSZ) "),%esi\n"
  "  push $7\n  pop %rdx\n"
  "  push $0x32\n  pop %r10\n"
  "  or $-1,%r8\n"
  "  xor %r9d,%r9d\n"
  "  syscall\n"
  "  cmp %rdi,%rax\n"
  "  je 1f\n"
  "  push $110\n  pop %rdi\n  mov $231,%eax\n  syscall\n"
  "1:\n"
  #endif
  "  call decode_startup\n"
#if DW_ELF_ARENA
  /* The loader supplies zeroed pages. Drop the counts before the next model starts. */
  "  mov $(" STR(S2BASE) "+" STR(S2MEM) "),%edi\n"
  "  mov $" STR(BOOT_TSZ) ",%esi\n"
  "  push $11\n  pop %rax\n  syscall\n"
#endif
  /* stage 2: s2_main(original_sp, header); does not return */
  "  mov %rbp,%rdi\n"
  "  mov $cut_hdr,%esi\n"
  "  call " STR(S2BASE) "\n"
);
