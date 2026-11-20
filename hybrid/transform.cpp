// SPDX-License-Identifier: GPL-3.0-only
// The file stages of Marcus Woelk's cmix-neif 2.0 runner, in upstream order.
// Called from the public launcher in a fresh, private working directory.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <string>
#include <vector>

#include "preprocess/preprocessor.h"
#include "preprocess/dict_derive.h"
#include "readalike_prepr/article_reorder.h"
#include "readalike_prepr/phda9_preprocess.h"
#include "readalike_prepr/misc.h"
#include "readalike_prepr/komm_transform.h"
#include "metablock.h"
#include "census_block.h"
#include "ip_pack.h"
#include "isbn_check.h"
#include "metablock_form.h"
#include "text_start_pack.h"
#include "rule_stages_file.h"

// As in upstream glibc_compat.cpp, the preprocessor's decimal conversions
// can use the classic strtol ABI on both Debian 12 and newer build hosts.
extern "C" long classic_strtol(const char *, char **, int) __asm__("strtol");
extern "C" __attribute__((visibility("hidden")))
long __isoc23_strtol(const char *text, char **end, int base) {
    return classic_strtol(text, end, base);
}

// The native model's PPMd page pool is absent during these file stages.
namespace ppmd_page { void dyn_tick() {} }

namespace {
void check(bool ok, const char *stage) {
    if (!ok) {
        std::fprintf(stderr, "cmix-neif stage failed: %s\n", stage);
        std::exit(1);
    }
}

FILE *open_file(const char *name, const char *mode) {
    FILE *file = std::fopen(name, mode);
    check(file != nullptr, name);
    return file;
}

void close_file(FILE *file) {
    check(!std::ferror(file) && std::fclose(file) == 0, "file I/O");
}

void forward(const char *source, const char *tape) {
    check(dict_derive::BuildDictFromInput(source, ".hints", ".dict"), "word dictionary");
    check(census_file_enc(source, ".census_prepr"), "census");
    split4Comp(".census_prepr");
    std::remove(".census_prepr");
    check(cmtidx_inplace_enc(".main", ".cmtidx_main"), "comment index");
    reorder();
    std::remove(".main");
    check(comment_form::Kodiere(".main_reordered"), "comment text");
    check(census_block::Zerlege(".main_reordered", ".censblock"), "census records");
    phda9_prepr();
    std::remove(".main_reordered");
    const char *const parts[] = {".main_phda9prepr", ".intro", ".coda", nullptr};
    check(cat(".ready4cmix", parts), "join Wikipedia sections");
    std::remove(".main_phda9prepr");
    isbn_check::Pack();
    FILE *dict = open_file(".dict", "rb");
    FILE *input = open_file(".ready4cmix", "rb");
    FILE *output = open_file(tape, "wb");
    preprocessor::Encode(input, output, std::filesystem::file_size(".ready4cmix"), dict);
    close_file(input);
    close_file(output);
    std::remove(".ready4cmix");
    check(census_block::Einfuegen(tape, ".censblock", dict), "insert census block");
    close_file(dict);
    check(metablock_form::Pack(tape), "metadata");
    check(ip_pack::Pack(tape), "IP addresses");
    check(dict_article::SlotDatei(), "dictionary article");
    check(rule_stages::DateiEnc(tape), "text rules");
    check(text_start::Pack(tape, true, false), "text start");
}

void inverse(const char *tape, const char *destination) {
    check(text_start::Unpack(tape, true), "restore text start");
    check(dict_article::DateiAusSlot(), "recover dictionary from archive");
    check(rule_stages::DateiDec(tape), "restore text rules");
    check(ip_pack::Unpack(tape), "restore IP addresses");
    check(metablock_form::Unpack(tape), "restore metadata");
    FILE *dict = open_file(".dict", "rb");
    check(census_block::Entnehmen(tape, ".censblock", dict), "extract census block");
    FILE *input = open_file(tape, "rb");
    FILE *output = open_file(".input_decomp", "wb");
    isbn_check::after_at.an = true;
    preprocessor::Decode(input, output, dict);
    isbn_check::after_at.Put(-1, output);
    close_file(input);
    close_file(output);
    close_file(dict);
    std::remove(tape);
    split4Decomp();
    std::remove(".input_decomp");
    phda9_resto();
    std::remove(".main_decomp");
    check(census_block::Setze(".main_decomp_restored", ".censblock"), "restore census pages");
    check(comment_form::Dekodiere(".main_decomp_restored"), "restore comment text");
    ::sort();
    std::remove(".main_decomp_restored");
    check(cmtidx_inplace<0>(".main_decomp_restored_sorted", ".cmtidx_resto"), "restore comment index");
    const char *const parts[] = {".intro_decomp", ".main_decomp_restored_sorted", ".coda_decomp", nullptr};
    check(cat(".census_resto", parts), "join original sections");
    std::remove(".main_decomp_restored_sorted");
    check(census_file<0>(".census_resto", destination), "restore original census text");
}
}

int main(int argc, char **argv) {
    if (argc != 4) return 2;
    if (std::strcmp(argv[1], "forward") == 0) forward(argv[2], argv[3]);
    else if (std::strcmp(argv[1], "inverse") == 0) inverse(argv[2], argv[3]);
    else return 2;
    return 0;
}
