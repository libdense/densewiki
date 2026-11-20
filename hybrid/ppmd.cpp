// SPDX-License-Identifier: GPL-3.0-only
// Share DWX4 Wiki's continuous libarchive PPMd member without a DWX4 transform.
#include "topics.hpp"
#include "archive_io.hpp"

int main(int argc, char **argv) {
    if (argc != 4) return 2;
    try {
        auto input = dw::open_file(argv[2], "rb");
        auto output = dw::open_file(argv[3], "wb");
        constexpr uint64_t bytes = 501062281;
        if (dw::View(argv[1]) == "pack") {
            dw::require(dw::length(input.get()) == bytes, "unexpected native stream length");
            dw::archive_pack(input.get(), output.get(), false);
        } else if (dw::View(argv[1]) == "unpack") {
            dw::Unpack tape(input.get(), 0, dw::length(input.get()));
            std::array<char, 65536> buf;
            for (uint64_t remaining = bytes; remaining;) {
                size_t n = std::min<uint64_t>(remaining, buf.size());
                tape.read(buf.data(), n);
                dw::write_file(output.get(), dw::View(buf.data(), n));
                remaining -= n;
            }
            tape.finish();
        } else return 2;
        dw::require(std::fclose(output.release()) == 0, "cannot close output");
        return 0;
    } catch (const std::exception &e) {
        std::fprintf(stderr, "PPMd: %s\n", e.what());
        return 1;
    }
}
