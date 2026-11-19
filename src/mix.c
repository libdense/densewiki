/* SPDX-License-Identifier: GPL-3.0-only
 * DenseWiki 0.0.1, 2026-11-19. Offline trainer, encoder and independent decoder
 * for the bootstrap data in the two named Hutter-format entries.
 * Predictor counts, hash and range-coder convention follow Marcus Woelk's
 * boot_cm.h (cmix-neif 2.0). DenseWiki adds replay traces, linear integer
 * mixture weights and routing by byte region and bit position.
 */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { STAGE_BYTES = 12311, MAX_MODELS = 32, MAX_GROUPS = 256, TABLE_BITS = 22 };
typedef struct {
    unsigned models, region_shift, bit_shift, prior, groups, cap, boost, decay, keep;
    unsigned char mask[MAX_MODELS], weight[MAX_GROUPS][MAX_MODELS];
} Policy;
typedef struct {
    uint32_t low, high, code;
    unsigned char *data;
    size_t pos, len;
} Range;
typedef struct {
    uint16_t n0, n1;
} Counts;

static void fail(const char *message) {
    fprintf(stderr, "mix: %s\n", message);
    exit(EXIT_FAILURE);
}

static unsigned char *load(const char *name, size_t limit, size_t *size) {
    FILE *f = fopen(name, "rb");
    if (!f) { perror(name); exit(EXIT_FAILURE); }
    unsigned char *data = malloc(limit + 1);
    if (!data) fail("allocation failed");
    *size = fread(data, 1, limit + 1, f);
    if (*size > limit || ferror(f) || fclose(f)) fail("input size or read error");
    return data;
}

static void write_bytes(FILE *f, const void *data, size_t n) {
    if (fwrite(data, 1, n, f) != n) fail("write failed");
}

static Policy load_policy(const char *name) {
    size_t n;
    unsigned char *p = load(name, 16 + (MAX_GROUPS + 1) * MAX_MODELS, &n);
    Policy cfg = {0};
    size_t start = n >= 12 && !memcmp(p, "DWM2", 4) ? 12u : 8u;
    if (n < start || (start == 8 && memcmp(p, "DWM1", 4))) fail("invalid policy header");
    cfg.cap = start == 12 ? p[8] : 255;
    cfg.boost = start == 12 ? p[9] : 2;
    cfg.decay = start == 12 ? p[10] : 1;
    cfg.keep = start == 12 ? p[11] : 1;
    if (!cfg.cap || !cfg.boost || cfg.boost > 32 || cfg.decay < 1 || cfg.decay > 4 || cfg.keep > 1)
        fail("invalid counter parameters");
    cfg.models = p[4]; cfg.region_shift = p[5]; cfg.bit_shift = p[6]; cfg.prior = p[7];
    if (!cfg.models || cfg.models > MAX_MODELS || cfg.region_shift > 31 ||
        cfg.bit_shift > 3 || !cfg.prior) fail("policy parameters outside range");
    cfg.groups = (((STAGE_BYTES - 1u) >> cfg.region_shift) + 1) * (8u >> cfg.bit_shift);
    if (cfg.groups > MAX_GROUPS || n != start + cfg.models * (1 + cfg.groups))
        fail("invalid policy length");
    memcpy(cfg.mask, p + start, cfg.models);
    for (unsigned g = 0; g < cfg.groups; ++g)
        memcpy(cfg.weight[g], p + start + cfg.models * (g + 1), cfg.models);
    free(p);
    return cfg;
}

static uint32_t slot(uint64_t history, unsigned prefix, unsigned mask, unsigned index) {
    uint64_t h = prefix;
    while (mask) {
        if (mask & 1u) h = h * UINT64_C(0x100000001b3) + (history & 255u);
        history >>= 8;
        mask >>= 1;
    }
    h = (h + index * UINT64_C(0x9e3779b97f4a7c15)) * UINT64_C(0x2545f4914f6cdd1d);
    return (uint32_t)(h >> (64 - TABLE_BITS)) * 2u;
}

static unsigned read_range(Range *r) {
    if (r->pos >= r->len) fail("truncated range stream");
    return r->data[r->pos++];
}

static void put_range(Range *r, unsigned value) {
    if (r->pos >= r->len) fail("range output capacity exceeded");
    r->data[r->pos++] = (unsigned char)value;
}

static int code_bit(Range *r, int decoding, int bit, unsigned probability) {
    uint32_t split = r->low + (uint32_t)(((uint64_t)(r->high - r->low) * probability) >> 12);
    if (decoding) bit = r->code <= split;
    if (bit) r->high = split;
    else r->low = split + 1;
    while (((r->low ^ r->high) >> 24) == 0) {
        if (decoding) r->code = (r->code << 8) | read_range(r);
        else put_range(r, r->high >> 24);
        r->low <<= 8;
        r->high = (r->high << 8) | 255u;
    }
    return bit;
}

static void run(const Policy *cfg, int decoding, int trace, unsigned char *raw,
                Range *r, FILE *out) {
    unsigned char *table = calloc((size_t)2 << TABLE_BITS, 1);
    if (!table) fail("counter allocation failed");
    uint64_t history = 0;
    if (decoding)
        for (int i = 0; i < 4; ++i) r->code = (r->code << 8) | read_range(r);
    for (unsigned i = 0; i < STAGE_BYTES; ++i) {
        unsigned prefix = 1;
        for (unsigned b = 0; b < 8; ++b) {
            uint32_t slots[MAX_MODELS];
            unsigned a0 = cfg->prior, a1 = cfg->prior;
            unsigned g = (i >> cfg->region_shift) * (8u >> cfg->bit_shift) + (b >> cfg->bit_shift);
            Counts counts[MAX_MODELS];
            for (unsigned m = 0; m < cfg->models; ++m) {
                uint32_t s = slots[m] = slot(history, prefix, cfg->mask[m], m);
                unsigned n0 = table[s], n1 = table[s + 1];
                if (!n0) n1 *= cfg->boost;
                if (!n1) n0 *= cfg->boost;
                counts[m] = (Counts){(uint16_t)n0, (uint16_t)n1};
                a0 += n0 * cfg->weight[g][m];
                a1 += n1 * cfg->weight[g][m];
            }
            int bit = (raw[i] >> (7u - b)) & 1u;
            if (trace) {
                /* trace is little-endian u16 pairs, independent of host byte order */
                unsigned char record[4 * MAX_MODELS];
                for (unsigned m = 0; m < cfg->models; ++m) {
                    record[4*m] = (unsigned char)counts[m].n0;
                    record[4*m+1] = (unsigned char)(counts[m].n0 >> 8);
                    record[4*m+2] = (unsigned char)counts[m].n1;
                    record[4*m+3] = (unsigned char)(counts[m].n1 >> 8);
                }
                write_bytes(out, record, 4 * cfg->models);
            } else {
                unsigned p = (unsigned)(((uint64_t)a1 << 12) / (a0 + a1));
                if (p == 0) p = 1;
                if (p > 4095) p = 4095;
                bit = code_bit(r, decoding, bit, p);
            }
            for (unsigned m = 0; m < cfg->models; ++m) {
                unsigned char *hit = &table[slots[m] + (unsigned)bit];
                unsigned char *other = &table[slots[m] + 1u - (unsigned)bit];
                if (*hit < cfg->cap) ++*hit;
                if (*other > cfg->keep) *other = (unsigned char)((*other >> cfg->decay) + cfg->keep);
            }
            prefix = (prefix << 1) | (unsigned)bit;
        }
        raw[i] = (unsigned char)prefix;
        history = (history << 8) | raw[i];
    }
    if (decoding) {
        if (r->pos != r->len) fail("extra bytes in range stream");
        write_bytes(out, raw, STAGE_BYTES);
    } else if (!trace) {
        for (int shift = 24; shift >= 0; shift -= 8) put_range(r, r->low >> shift);
        write_bytes(out, r->data, r->pos);
    }
    free(table);
}

int main(int argc, char **argv) {
    if (argc != 5) fail("usage: mix encode|decode|trace POLICY INPUT NEW_OUTPUT");
    int decoding = !strcmp(argv[1], "decode"), trace = !strcmp(argv[1], "trace");
    if (!decoding && !trace && strcmp(argv[1], "encode")) fail("unknown operation");
    Policy cfg = load_policy(argv[2]);
    size_t n;
    unsigned char *src = load(argv[3], decoding ? STAGE_BYTES * 4 : STAGE_BYTES, &n);
    if (!decoding && n != STAGE_BYTES) fail("unexpected bootstrap data length");
    unsigned char raw[STAGE_BYTES] = {0};
    unsigned char encoded[4 * STAGE_BYTES];
    if (!decoding) memcpy(raw, src, n);
    Range range = {0, UINT32_MAX, 0, decoding ? src : encoded, 0,
                   decoding ? n : sizeof(encoded)};
    FILE *out = fopen(argv[4], "wbx");
    if (!out) { perror(argv[4]); return EXIT_FAILURE; }
    run(&cfg, decoding, trace, raw, &range, out);
    free(src);
    if (fclose(out)) fail("close failed");
    return 0;
}
