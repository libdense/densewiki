// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include "transform.hpp"

namespace dw {
struct Field { View head, tail; };
inline constexpr Field fields[] = {
    {"    <title>","</title>"}, {"    <id>","</id>"}, {"      <id>","</id>"},
    {"        <id>","</id>"}, {"      <timestamp>","</timestamp>"},
    {"        <username>","</username>"}, {"        <ip>","</ip>"},
    {"      <comment>","</comment>"}
};
inline constexpr View fixed[] = {"", "  <page>", "  </page>", "    <revision>",
    "    </revision>", "      <contributor>", "      </contributor>", "      <minor />"};
inline constexpr View text_open = "      <text xml:space=\"preserve\">", text_close = "</text>";
enum : unsigned {
    prose, list, table, markup, heading, redirect, category, link, language0,
    field0=language0+8, fixed0=field0+std::size(fields), repeat=fixed0+std::size(fixed),
    values=repeat+1, lanes=values+1, text_head=64, text_tail=128
};
static_assert(lanes < text_head);
inline uint32_t hash_text(View s) {
    uint32_t h=2166136261u;
    for (unsigned char c:s) h=(h^c)*16777619u;
    return h;
}
struct Template {
    Bytes pattern, numbers;
    bool derive(View line) {
        pattern.clear(); numbers.clear();
        if (line.size()<20 || line.size()>2048 || line.find_first_of("0123456789")==View::npos ||
            line.find(char(0))!=View::npos) return false;
        unsigned slots=0;
        size_t copy=0, i=0;
        while (i<line.size()) {
            if (!digit(static_cast<unsigned char>(line[i]))) { ++i; continue; }
            size_t a=i++;
            while (i<line.size()) {
                if (digit(static_cast<unsigned char>(line[i]))) { ++i; continue; }
                if ((line[i]=='.' || line[i]==',') && i+1<line.size() &&
                    digit(static_cast<unsigned char>(line[i+1]))) { i+=2; continue; }
                break;
            }
            pattern.append(line.substr(copy,a-copy)); pattern.push_back(0);
            numbers.append(line.substr(a,i-a)); numbers.push_back(' ');
            copy=i; ++slots;
        }
        if (slots<2) return false;
        pattern.append(line.substr(copy));
        return true;
    }
};
struct Cache {
    static constexpr unsigned slots=2048;
    std::array<Bytes,slots> templates;
    Template current;
    std::optional<unsigned> observe(View s) {
        if (!current.derive(s)) return {};
        unsigned id=hash_text(current.pattern) & (slots-1);
        if (templates[id] == current.pattern) return id;
        templates[id]=current.pattern;
        return {};
    }
};

inline unsigned classify(View &s, bool detail) {
    if (s.empty() || s.front()==' ') {
        for (size_t j=0;j<std::size(fixed);++j) if (s==fixed[j]) return fixed0+j;
        for (size_t j=0;j<std::size(fields);++j) {
            auto [head,tail]=fields[j];
            if (s.size()>=head.size()+tail.size() && s.starts_with(head) && s.ends_with(tail)) {
                s.remove_prefix(head.size()); s.remove_suffix(tail.size()); return field0+j;
            }
        }
    }
    if (s.starts_with("#REDIRECT")||s.starts_with("#redirect")||s.starts_with("#Redirect")) return redirect;
    if (s.starts_with("[[Category:")||s.starts_with("[[category:")) return category;
    if (s.starts_with("[[") && s.size()>5) {
        size_t i=2;
        while(i<s.size() && i<12 && (letter(static_cast<unsigned char>(s[i])) || s[i]=='-')) ++i;
        if (i>2 && i<s.size() && s[i]==':') return language0+(hash_text(s.substr(2,i-2)) & 7);
        if (detail) return link;
    }
    if (!detail || s.empty()) return prose;
    switch(s.front()){
    case '*': case '#': case ';': case ':':return list;
    case '|': case '!':return table;
    case '{': case '}':return markup;
    case '=':return heading;
    default:return prose;
    }
}
struct RowData {
    Bytes layout;
    std::array<Bytes,lanes> data;
    uint64_t hits=0, matched_bytes=0;
};
inline Bytes route(View input, unsigned mode, Cache &cache, uint64_t &hits, uint64_t &matched) {
    RowData g;
    for (size_t pos=0;pos<input.size();) {
        size_t end=input.find('\n',pos);
        if(end==View::npos) end=input.size();
        View line=input.substr(pos,end-pos);
        pos=end+1;
        unsigned flags=0;
        if (line.starts_with(text_open)) {flags|=text_head;line.remove_prefix(text_open.size());}
        if (line.ends_with(text_close)) {flags|=text_tail;line.remove_suffix(text_close.size());}
        if (mode&2) {
            if (auto id=cache.observe(line)) {
                g.layout.push_back(static_cast<char>(repeat|flags));
                put_var(g.data[repeat],*id);g.data[values]+=cache.current.numbers;
                ++g.hits;g.matched_bytes+=line.size();
                continue;
            }
        }
        unsigned op=classify(line,mode&4);
        g.layout.push_back(static_cast<char>(op|flags));
        if (op<fixed0) { g.data[op].append(line); g.data[op].push_back('\n'); }
    }
    Bytes tape;
    put_var(tape,g.layout.size());tape+=g.layout;
    for (unsigned j=0;j<lanes;++j) {
        if(j>=fixed0 && j<repeat) continue;
        put_var(tape,g.data[j].size());tape+=g.data[j];
    }
    hits+=g.hits;matched+=g.matched_bytes;
    return tape;
}

inline Bytes unroute(View tape,size_t raw_size,unsigned mode,Cache &cache) {
    size_t p=0;
    auto field=[&](unsigned limit) {
        unsigned n=take_var(tape,p,limit);
        require(n<=tape.size()-p,"truncated row table");
        auto slice=tape.substr(p,n);p+=n;return slice;
    };
    View layout=field(raw_size);
    std::array<View,lanes> data{};
    for(unsigned j=0;j<lanes;++j) if(j<fixed0 || j>=repeat) data[j]=field(4*block_size+1024);
    require(p==tape.size(),"extra row table bytes");
    std::array<size_t,lanes> cursor{};
    Bytes raw;
    raw.reserve(raw_size+1);
    for(unsigned char code:layout) {
        unsigned op=code&63;
        require(op<=repeat,"invalid row type");
        if(code&text_head) raw+=text_open;
        std::size_t line_start=raw.size();
        if(op==repeat) {
            require(mode&2,"disabled template reference");
            unsigned id=take_var(data[repeat],cursor[repeat],Cache::slots-1);
            const auto &pattern=cache.templates[id];
            require(!pattern.empty(),"unknown numeric template");
            for(char c:pattern) {
                if(c) raw+=c;
                else {
                    View v=data[values];size_t &q=cursor[values];
                    size_t end=v.find(' ',q);
                    require(end!=View::npos && end>q && end-q<=2048,"invalid numeric exception");
                    require(raw.size()+end-q<=raw_size,"template exceeds block");
                    raw.append(v.substr(q,end-q));q=end+1;
                }
            }
        } else {
            if(op>=fixed0) raw+=fixed[op-fixed0];
            else {
                View v=data[op];size_t &q=cursor[op];
                size_t end=v.find('\n',q);
                require(end!=View::npos,"unterminated row");
                if(op>=field0) raw+=fields[op-field0].head;
                raw.append(v.substr(q,end-q)); q=end+1;
                if(op>=field0) raw+=fields[op-field0].tail;
            }
            if(mode&2) cache.observe(View(raw).substr(line_start));
        }
        if(code&text_tail) raw+=text_close;
        require(raw.size()<=raw_size,"row expansion exceeds block");
        raw+='\n';
    }
    if(raw.size()==raw_size+1) raw.pop_back();
    require(raw.size()==raw_size,"wrong restored size");
    for(unsigned j=0;j<lanes;++j) require(cursor[j]==data[j].size(),"unused row bytes");
    return raw;
}
}
