// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <limits>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <unordered_map>
#include <utility>
#include <vector>

namespace dw {
using Bytes = std::string;
using View = std::string_view;
constexpr size_t block_size = 1u << 20;
constexpr unsigned max_vocab = 32768, max_word = 48;
constexpr unsigned escape = 27, title = 28, upper = 29;
inline bool letter(unsigned c) { return (c | 32u) >= 97 && (c | 32u) <= 122; }
inline bool digit(unsigned c) { return c >= 48 && c <= 57; }
inline void require(bool ok, const char *why) { if (!ok) throw std::runtime_error(why); }
inline void put_var(Bytes &s, uint64_t v) {
    while (v >= 128) { s.push_back(static_cast<char>((v & 127) | 128)); v >>= 7; }
    s.push_back(static_cast<char>(v));
}
inline unsigned take_var(View s, size_t &i, unsigned limit) {
    uint64_t n = 0;
    for (unsigned shift = 0; shift < 35 && i < s.size(); shift += 7) {
        unsigned b = static_cast<unsigned char>(s[i++]);
        n |= uint64_t(b & 127) << shift;
        if (b < 128) {
            require(n <= limit && (!shift || b), "invalid field length");
            return static_cast<unsigned>(n);
        }
    }
    throw std::runtime_error("invalid variable-length integer");
}

template<class Fn> void words(View s, Fn visit) {
    for (size_t i = 0; i < s.size();) {
        if (!letter(static_cast<unsigned char>(s[i]))) { ++i; continue; }
        size_t begin = i++;
        while (i < s.size() && letter(static_cast<unsigned char>(s[i]))) ++i;
        if (i - begin >= 2 && i - begin <= max_word) visit(begin, i);
    }
}

struct Word {
    std::array<char,max_word> folded{};
    unsigned form = 0;
    View parse(View w) {
        unsigned capitals = 0;
        for (size_t j = 0; j < w.size(); ++j) {
            capitals += w[j] <= 'Z';
            folded[j] = static_cast<char>(w[j] | 32);
        }
        if (!capitals) form = 0;
        else if (capitals == w.size()) form = upper;
        else if (capitals == 1 && w.front() <= 'Z') form = title;
        else return {};
        return View(folded.data(), w.size());
    }
};

struct ViewHash {
    using is_transparent = void;
    size_t operator()(View s) const noexcept { return std::hash<View>{}(s); }
};
using Counts = std::unordered_map<Bytes,uint32_t,ViewHash,std::equal_to<>>;
using Vocabulary = std::vector<Bytes>;
inline Vocabulary learn(FILE *input, unsigned limit) {
    Counts counts;
    const size_t capacity = std::max<size_t>(4096, limit * 2);
    counts.reserve(capacity);
    Bytes buf(block_size, 0);
    Word word;
    size_t n;
    while ((n = std::fread(buf.data(), 1, buf.size(), input))) {
        words(View(buf.data(), n), [&](size_t a, size_t b) {
            View key = word.parse(View(buf.data() + a, b-a));
            if (key.empty()) return;
            auto it = counts.find(key);
            if (it != counts.end()) {
                if (it->second != UINT32_MAX) ++it->second;
            } else if (counts.size() < capacity) {
                counts.emplace(Bytes(key), 1);
            } else {
                for (auto j = counts.begin(); j != counts.end();) {
                    if (--j->second == 0) j = counts.erase(j);
                    else ++j;
                }
            }
        });
    }
    require(!std::ferror(input) && std::fseek(input, 0, SEEK_SET) == 0, "cannot reread input");
    Vocabulary v;
    for (const auto &p : counts) if (p.second >= 3) v.push_back(p.first);
    std::sort(v.begin(), v.end(), [&](const Bytes &a, const Bytes &b) {
        auto ca = counts.at(a), cb = counts.at(b);
        return ca != cb ? ca > cb : a < b;
    });
    if (v.size() > limit) v.resize(limit);
    for (size_t a : {size_t(0), size_t(80), size_t(4176)}) {
        size_t b = a == 0 ? 80 : a == 80 ? 4176 : v.size();
        if (a < v.size()) std::sort(v.begin()+a, v.begin()+std::min(b,v.size()));
    }
    return v;
}
inline void put_ref(Bytes &out, unsigned id) {
    if (id < 80) { out.push_back(static_cast<char>(128 + id)); return; }
    id -= 80;
    if (id < 4096) out.push_back(static_cast<char>(208 + (id >> 7)));
    else {
        id -= 4096;
        out.push_back(static_cast<char>(240 + (id >> 14)));
        out.push_back(static_cast<char>(128 | ((id >> 7) & 127)));
    }
    out.push_back(static_cast<char>(128 | (id & 127)));
}
inline unsigned take_digit(View input, size_t &i) {
    require(i < input.size() && static_cast<unsigned char>(input[i]) >= 128, "bad word reference");
    return static_cast<unsigned char>(input[i++]) - 128;
}
inline unsigned read_ref(unsigned c, View input, size_t &i) {
    if (c < 208) return c-128;
    if (c < 240) return 80 + (c-208)*128 + take_digit(input,i);
    unsigned middle = take_digit(input,i);
    return 4176 + (c-240)*16384 + middle*128 + take_digit(input,i);
}
inline void literals(Bytes &out, View s) {
    for (unsigned char c : s) {
        if (c >= 128 || (c >= escape && c <= upper)) out.push_back(escape);
        out.push_back(static_cast<char>(c));
    }
}
struct Encoder {
    Counts ids;
    explicit Encoder(const Vocabulary &v) {
        ids.reserve(v.size());
        for (unsigned j = 0; j < v.size(); ++j) ids.emplace(v[j],j);
    }
    Bytes encode(View data) const {
        Bytes out;
        out.reserve(data.size());
        size_t cursor = 0;
        Word word;
        words(data,[&](size_t a, size_t b) {
            View key = word.parse(data.substr(a,b-a));
            if (key.empty()) return;
            auto it = ids.find(key);
            if (it == ids.end()) return;
            size_t gap_end = a;
            if (a >= 2 && a > cursor && data[a-1] == ' ' && letter(static_cast<unsigned char>(data[a-2]))) --gap_end;
            literals(out,data.substr(cursor,gap_end-cursor));
            if (word.form) out.push_back(static_cast<char>(word.form));
            put_ref(out,it->second);
            cursor = b;
        });
        literals(out,data.substr(cursor));
        return out;
    }
};
inline Bytes expand_words(View input, const Vocabulary &v, size_t limit) {
    Bytes out;
    for (size_t i=0; i<input.size();) {
        unsigned c=static_cast<unsigned char>(input[i++]), form=0;
        if (c == escape) {
            require(i < input.size(), "truncated literal");
            c=static_cast<unsigned char>(input[i++]);
            require(c >= 128 || (c >= escape && c <= upper), "invalid escaped literal");
            out.push_back(static_cast<char>(c));
        } else if (c == title || c == upper || c >= 128) {
            if (c < 128) {
                form=c;
                require(i < input.size() && static_cast<unsigned char>(input[i]) >= 128, "truncated case code");
                c=static_cast<unsigned char>(input[i++]);
            }
            unsigned id=read_ref(c,input,i);
            require(id < v.size(), "unknown word");
            if (!out.empty() && letter(static_cast<unsigned char>(out.back()))) out.push_back(' ');
            size_t base=out.size();
            out += v[id];
            if (form) {
                size_t end=form==title?base+1:out.size();
                for (size_t j=base;j<end;++j) out[j]=static_cast<char>(out[j]-32);
            }
        } else out.push_back(static_cast<char>(c));
        require(out.size() <= limit, "word expansion exceeds block");
    }
    return out;
}
}
