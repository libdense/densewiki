// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include "rows.hpp"
#include "titles.hpp"

namespace dw {
constexpr unsigned article_facts = 256, article_links = 512, only_film = 1024, selective_refs = 2048;
constexpr unsigned article_modes = article_facts | article_links;
constexpr char fact_mark = 13, link_mark = 0;
constexpr size_t target_limit = 512;

struct ArticleStats {
    uint64_t boxes = 0, films = 0, facts = 0, film_facts = 0, links = 0;
};

inline View trim_space(View s) {
    while (!s.empty() && (s.front() == ' ' || s.front() == '\t')) s.remove_prefix(1);
    while (!s.empty() && (s.back() == ' ' || s.back() == '\t')) s.remove_suffix(1);
    return s;
}

inline Bytes field_key(View s) {
    Bytes key;
    for (unsigned char c : s) {
        if (c == ' ' || c == '_' || c == '\t' || c == '-') continue;
        key += static_cast<char>(c >= 'A' && c <= 'Z' ? c + 32 : c);
    }
    return key;
}

struct WikiTarget {
    View name;
    size_t bytes = 0;
    bool piped = false;
};

// Return just the target and its delimiter. The label after a pipe is literal.
inline WikiTarget wiki_target(View s) {
    if (!s.starts_with("[[")) return {};
    for (size_t i = 2; i < s.size() && i <= target_limit + 2; ++i) {
        const unsigned char c = s[i];
        if (c == '|' || c == ']') {
            if (i == 2 || (c == ']' && !s.substr(i).starts_with("]]"))) return {};
            return {s.substr(2, i - 2), i + (c == '|' ? 1u : 2u), c == '|'};
        }
        if (c < 32 || c == '[') return {};
    }
    return {};
}

inline void escaped(Bytes &out, View s, char marker) {
    for (size_t p; (p = s.find(marker)) != View::npos; s.remove_prefix(p + 1)) {
        out.append(s.substr(0, p + 1));
        out += marker;
    }
    out.append(s);
}

// A slot owns its spelling. Promoting a target moves only its slot number.
class RecentLinks {
    std::array<Bytes, 32> names;
    std::array<unsigned, 32> order{};
    unsigned count = 0;

    unsigned rank(View target) const {
        for (unsigned i = 0; i < count; ++i)
            if (names[order[i]] == target) return i;
        return count;
    }
    void touch(unsigned at, View target) {
        unsigned slot;
        if (at == count) {
            if (count < order.size()) slot = count++;
            else { at = count - 1; slot = order[at]; }
            names[slot] = target;
        } else slot = order[at];
        std::move_backward(order.begin(), order.begin() + at, order.begin() + at + 1);
        order[0] = slot;
    }

public:
    Bytes transform(View data, bool decode, size_t limit, ArticleStats &stats, bool selective) {
        Bytes out;
        out.reserve(data.size());
        bool in_page = false;
        Template numeric;
        for (size_t pos = 0; pos < data.size();) {
            size_t end = data.find('\n', pos);
            if (end == View::npos) end = data.size();
            View line = data.substr(pos, end - pos);
            if (line == "  <page>" || line == "  </page>") {
                in_page = line == "  <page>";
                count = 0;
            }
            std::optional<bool> numeric_line;
            for (size_t i = 0; i < line.size();) {
                if (line[i] == link_mark) {
                    ++i;
                    if (!decode) { out += link_mark; out += link_mark; }
                    else {
                        require(i < line.size(), "truncated link reference");
                        unsigned code = static_cast<unsigned char>(line[i++]);
                        if (!code) out += link_mark;
                        else {
                            require(in_page && code >= 32 && code < 96, "invalid link reference");
                            bool piped = code >= 64;
                            unsigned at = (code - 32) % 32;
                            require(at < count, "unknown link target");
                            const Bytes &target = names[order[at]];
                            out += "[[";
                            out += target;
                            out += piped ? "|" : "]]";
                            touch(at, target);
                        }
                    }
                } else if (in_page && line[i] == '[') {
                    WikiTarget hit = wiki_target(line.substr(i));
                    if (!hit.bytes) { out += line[i++]; continue; }
                    unsigned at = rank(hit.name);
                    bool use = !decode && at < count;
                    if (selective && use) {
                        use = hit.name.size() >= 16;
                        if (use && !numeric_line.has_value()) numeric_line = numeric.derive(line);
                        use = use && !numeric_line.value_or(false);
                    }
                    if (use) {
                        out += link_mark;
                        out += static_cast<char>((hit.piped ? 64 : 32) + at);
                        ++stats.links;
                    } else out.append(line.substr(i, hit.bytes));
                    touch(at, hit.name);
                    i += hit.bytes;
                } else {
                    size_t start = i++;
                    while (i < line.size() && line[i] != link_mark && line[i] != '[') ++i;
                    out.append(line.substr(start, i - start));
                }
                require(out.size() <= limit, "link expansion exceeds frame");
            }
            if (end < data.size()) out += '\n';
            pos = end + 1;
        }
        require(out.size() <= limit, "link expansion exceeds frame");
        return out;
    }
};

class PageFacts {
    static constexpr unsigned capacity = 64;
    std::array<Bytes, capacity> names;
    std::array<bool, 256> initial{};
    unsigned count = 0;
    size_t depth = 0;
    bool in_page = false, film = false, eligible = false, film_only, selective;
    PageTitle title;
    ArticleStats &stats;

    void reset() {
        count = 0;
        initial.fill(false);
        depth = 0;
        eligible = film = false;
    }

    static bool selected(View key) {
        static constexpr View fields[] = {
            "name","director","directors","starring","cast","writer","screenplay","producer",
            "music","cinematography","editing","distributor","released","release","releasedate",
            "country","location","place","birthplace","birthdate","dateofbirth","placeofbirth",
            "deathplace","deathdate","dateofdeath","placeofdeath","capital","city","state",
            "region","county","founded","spouse","artist","author","binomial","genus","species",
            "familia","phylum","ordo","classis","regnum"
        };
        return std::find(std::begin(fields), std::end(fields), key) != std::end(fields);
    }
    void add(View value) {
        value = trim_space(value);
        while (value.starts_with("''") && value.ends_with("''") && value.size() >= 4)
            value = value.substr(2, value.size() - 4);
        if (count == capacity || value.size() < 4 || value.size() > 96) return;
        if (selective && (value.size() < 8 || title.would_replace(value))) return;
        bool has_word = false;
        for (unsigned char c : value) {
            if (c < 32 || c == '[' || c == ']' || c == '{' || c == '}' ||
                c == '|' || c == '<' || c == '>' || c == '&') return;
            has_word |= letter(c) || digit(c) || c >= 128;
        }
        if (!has_word || std::find(names.begin(), names.begin() + count, value) != names.begin() + count) return;
        initial[static_cast<unsigned char>(value.front())] = true;
        names[count++] = value;
    }
    void field(View part) {
        size_t eq = part.find('=');
        if (eq == View::npos || eq > 56 || !selected(field_key(part.substr(0, eq)))) return;
        View value = trim_space(part.substr(eq + 1));
        add(value);
        for (size_t i = 0; (i = value.find("[[", i)) != View::npos;) {
            WikiTarget target = wiki_target(value.substr(i));
            if (!target.bytes) { i += 2; continue; }
            add(target.name);
            i += target.bytes;
            if (target.piped) {
                size_t end = value.find("]]", i);
                if (end != View::npos && end - i <= 96) {
                    add(value.substr(i, end - i));
                    i = end + 2;
                }
            }
        }
    }
    void observe(View line) {
        if (selective) title.observe(line);
        if (line == "  <page>" || line == "  </page>") {
            reset();
            in_page = line == "  <page>";
            return;
        }
        if (!in_page) return;
        size_t pos = 0;
        if (!depth) {
            for (;;) {
                pos = line.find("{{", pos);
                if (pos == View::npos) return;
                pos += 2;
                View tail = line.substr(pos);
                size_t end = tail.find_first_of("|}");
                View title = trim_space(tail.substr(0, end));
                if (title.size() > 96) continue;
                Bytes key = field_key(title);
                if (!key.starts_with("infobox") && !key.starts_with("taxobox")) continue;
                if (film_only && key != "infoboxfilm") continue;
                reset();
                film = key == "infoboxfilm";
                ++stats.boxes;
                stats.films += film;
                depth = 1;
                if (end == View::npos) return;
                pos += end;
                break;
            }
        }
        size_t start = pos;
        bool in_link = false;
        for (; pos < line.size(); ++pos) {
            View tail = line.substr(pos);
            if (tail.starts_with("[[")) { in_link = true; ++pos; }
            else if (tail.starts_with("]]")) { in_link = false; ++pos; }
            else if (!in_link && tail.starts_with("{{")) { ++depth; ++pos; }
            else if (!in_link && tail.starts_with("}}")) {
                if (--depth == 0) {
                    field(line.substr(start, pos - start));
                    eligible = count != 0;
                    return;
                }
                ++pos;
            } else if (!in_link && depth == 1 && line[pos] == '|') {
                field(line.substr(start, pos - start));
                start = pos + 1;
            }
        }
        if (depth == 1) field(line.substr(start));
    }

    void encode_line(Bytes &out, View line) {
        if (!eligible) { escaped(out, line, fact_mark); return; }
        size_t literal = 0;
        for (size_t i = 0; i < line.size();) {
            if (!initial[static_cast<unsigned char>(line[i])]) { ++i; continue; }
            unsigned best = count;
            size_t longest = 0;
            for (unsigned j = 0; j < count; ++j) {
                if (names[j].size() > longest && line.substr(i).starts_with(names[j])) {
                    best = j;
                    longest = names[j].size();
                }
            }
            if (best == count) { ++i; continue; }
            escaped(out, line.substr(literal, i - literal), fact_mark);
            out += fact_mark;
            out += static_cast<char>(32 + best);
            i += longest;
            literal = i;
            ++stats.facts;
            stats.film_facts += film;
        }
        escaped(out, line.substr(literal), fact_mark);
    }

public:
    PageFacts(unsigned mode, ArticleStats &observations)
        : film_only(mode & only_film), selective(mode & selective_refs), stats(observations) {}
    Bytes transform(View data, bool decode, size_t limit) {
        Bytes out;
        out.reserve(data.size());
        for (size_t pos = 0; pos < data.size();) {
            size_t end = data.find('\n', pos);
            if (end == View::npos) end = data.size();
            View line = data.substr(pos, end - pos);
            if (!decode) {
                // Page tags always travel literally so the next article starts empty.
                if (line == "  <page>" || line == "  </page>") out.append(line);
                else encode_line(out, line);
                observe(line);
            } else {
                size_t start = out.size();
                for (size_t p; (p = line.find(fact_mark)) != View::npos;) {
                    out.append(line.substr(0, p));
                    require(p + 1 < line.size(), "truncated fact reference");
                    unsigned code = static_cast<unsigned char>(line[p + 1]);
                    if (code == static_cast<unsigned char>(fact_mark)) out += fact_mark;
                    else {
                        require(eligible && code >= 32 && code - 32 < count, "unknown article fact");
                        out += names[code - 32];
                    }
                    require(out.size() <= limit, "fact expansion exceeds frame");
                    line.remove_prefix(p + 2);
                }
                out.append(line);
                observe(View(out).substr(start));
            }
            if (end < data.size()) out += '\n';
            require(out.size() <= limit, "article expansion exceeds frame");
            pos = end + 1;
        }
        return out;
    }
};

inline Bytes article_segment(View input, unsigned mode, bool decode, size_t limit, ArticleStats &stats) {
    Bytes first;
    if (decode && (mode & article_links)) {
        first = RecentLinks{}.transform(input, true, 2 * block_size, stats, mode & selective_refs);
        input = first;
    }
    if (mode & article_facts) {
        Bytes facts = PageFacts(mode, stats).transform(input, decode, decode ? limit : 2 * block_size);
        if (decode || !(mode & article_links)) return facts;
        first = std::move(facts);
        input = first;
    }
    if (!decode && (mode & article_links))
        return RecentLinks{}.transform(input, false, 2 * block_size, stats, mode & selective_refs);
    require(first.size() <= limit, "local output exceeds frame");
    return first;
}
}
