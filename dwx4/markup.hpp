// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include "transform.hpp"

namespace dw {
struct Spelling { View text; unsigned code; };
inline constexpr Spelling spellings[] = {
    {"[[",1},{"]]",2},{"{{",3},{"}}",4},{"&quot;",5},{"&lt;",6},{"&gt;",7},{"&amp;nbsp;",8},
    {"&amp;",11},{"'''",12},{"''",14},{"==",15},{"http://",23},{"https://",24},
    {"&lt;ref",25},{"&lt;/ref&gt;",26},{"&amp;ndash;",30},{"&amp;mdash;",31}
};
constexpr unsigned markup_escape=127;
struct Markup {
    std::array<View,128> meanings{};
    std::array<std::vector<Spelling>,128> initial;
    Markup() {
        for(auto item:spellings){
            meanings[item.code]=item.text;
            initial[static_cast<unsigned char>(item.text.front())].push_back(item);
        }
        for(auto &items:initial)std::sort(items.begin(),items.end(),[](auto a,auto b){return a.text.size()>b.text.size();});
    }
    Bytes encode(View in) const {
        Bytes out;out.reserve(in.size());
        for(size_t i=0;i<in.size();) {
            auto c=static_cast<unsigned char>(in[i]);
            if(c<128) {
                bool matched=false;
                for(const auto &item:initial[c]) if(in.substr(i).starts_with(item.text)){
                    out+=static_cast<char>(item.code);i+=item.text.size();matched=true;break;
                }
                if(matched)continue;
                if(c==markup_escape || !meanings[c].empty())out+=static_cast<char>(markup_escape);
            }
            out+=in[i++];
        }
        return out;
    }
    Bytes decode(View in,size_t limit) const {
        Bytes out;out.reserve(in.size());
        for(size_t i=0;i<in.size();){
            unsigned c=static_cast<unsigned char>(in[i++]);
            if(c==markup_escape){
                require(i<in.size(),"truncated markup escape");
                c=static_cast<unsigned char>(in[i++]);
                require(c<128 && (c==markup_escape || !meanings[c].empty()),"invalid markup escape");
                out+=static_cast<char>(c);
            }else if(c<128 && !meanings[c].empty())out+=meanings[c];
            else out+=static_cast<char>(c);
            require(out.size()<=limit,"markup expansion exceeds block");
        }
        return out;
    }
};
}
