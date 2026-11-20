/* SPDX-License-Identifier: GPL-3.0-only */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { STAGE = 12311, SLOTS = 32768 };
typedef struct {
    uint64_t key;
    unsigned id;
} Entry;

/* One independent feature per output slice, in numeric mask order. */
int main(int argc, char **argv) {
    if (argc != 7 && argc != 9) return 2;
    unsigned byte_class = argc == 9 ? atoi(argv[7]) : 255;
    unsigned limit = argc == 9 ? atoi(argv[8]) : 256;
    if (!byte_class || byte_class > 255 || !limit || limit > 256) return 2;
    unsigned cap = atoi(argv[3]), boost = atoi(argv[4]);
    unsigned decay = atoi(argv[5]), keep = atoi(argv[6]);
    if (!cap || cap > 255 || !boost || boost > 32 || !decay || decay > 4 || keep > 1) return 2;
    FILE *input = fopen(argv[1], "rb"), *output = fopen(argv[2], "wb");
    unsigned char raw[STAGE];
    if (!input || !output || fread(raw, 1, STAGE, input) != STAGE || fgetc(input) != EOF) return 1;
    Entry *entries = calloc(SLOTS, sizeof(*entries));
    unsigned char (*counts)[256][2] = calloc(STAGE + 1, sizeof(*counts));
    if (!entries || !counts) return 1;
    for (unsigned mask = 0; mask < limit; ++mask) {
        memset(entries, 0, SLOTS * sizeof(*entries));
        memset(counts, 0, (STAGE + 1) * sizeof(*counts));
        unsigned issued = 0;
        uint64_t history = 0;
        for (unsigned i = 0; i < STAGE; ++i) {
            uint64_t key = 0, data = history;
            for (unsigned selected = mask; selected; selected >>= 1, data >>= 8)
                if (selected & 1) key = (key << 8) | (data & byte_class);
            unsigned slot = (unsigned)((key * UINT64_C(0x9e3779b97f4a7c15)) >> 49);
            while (entries[slot].id && entries[slot].key != key) slot = (slot + 1) & (SLOTS - 1);
            if (!entries[slot].id) entries[slot] = (Entry){key, ++issued};
            unsigned char (*tree)[2] = counts[entries[slot].id];
            unsigned prefix = 1;
            unsigned char trace[32];
            for (unsigned b = 0; b < 8; ++b) {
                unsigned bit = (raw[i] >> (7 - b)) & 1;
                unsigned char *pair = tree[prefix];
                unsigned a = pair[0] * (pair[1] ? 1 : boost);
                unsigned v = pair[1] * (pair[0] ? 1 : boost);
                trace[4*b] = a; trace[4*b+1] = a >> 8;
                trace[4*b+2] = v; trace[4*b+3] = v >> 8;
                if (pair[bit] < cap) ++pair[bit];
                if (pair[!bit] > keep) pair[!bit] = (pair[!bit] >> decay) + keep;
                prefix = 2 * prefix + bit;
            }
            if (fwrite(trace, 1, sizeof(trace), output) != sizeof(trace)) return 1;
            history = (history << 8) | raw[i];
        }
    }
    free(entries);
    free(counts);
    fclose(input);
    return fclose(output) != 0;
}
