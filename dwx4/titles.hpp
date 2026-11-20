// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include "transform.hpp"

namespace dw {
class PageTitle {
    static constexpr unsigned first=16, escape_title=22;
    static constexpr View tag="    <title>", close="</title>";
    std::array<Bytes,6> names;
    bool title_line(View s) const {
        return s.size()>=tag.size()+close.size() && s.starts_with(tag) && s.ends_with(close);
    }
    void update(View line) {
        if(line=="  <page>" || line=="  </page>") {for(auto &s:names)s.clear();return;}
        if(!title_line(line))return;
        for(auto &s:names)s.clear();
        View value=line.substr(tag.size(),line.size()-tag.size()-close.size());
        if(value.size()<4 || value.size()>512)return;
        names[0]=value;
        auto cut=std::min(value.find(" ("),value.find(", "));
        if(cut!=View::npos && cut>=4)names[2]=value.substr(0,cut);
        auto ns=value.find(':');
        if(ns!=View::npos && value.size()-ns-1>=4)names[4]=value.substr(ns+1);
        for(unsigned j=0;j<names.size();j+=2) {
            if(!names[j].empty() && names[j][0]>='A' && names[j][0]<='Z') {
                names[j+1]=names[j];names[j+1][0]=static_cast<char>(names[j+1][0]+32);
            }
        }
    }
    static void literal(Bytes &out,View s) {
        size_t start=0;
        for(size_t i=0;i<s.size();++i) {
            unsigned c=static_cast<unsigned char>(s[i]);
            if(c>=first && c<=escape_title) {
                out.append(s.substr(start,i-start));out+=static_cast<char>(escape_title);start=i;
            }
        }
        out.append(s.substr(start));
    }
    void encode_line(Bytes &out,View line,uint64_t &refs) {
        if(title_line(line) || names[0].empty()) literal(out,line);
        else {
            size_t start=0;
            while(start<line.size()) {
                size_t best=View::npos;unsigned variant=0;
                for(unsigned j=0;j<names.size();++j) if(!names[j].empty()) {
                    size_t p=line.find(names[j],start);
                    if(p<best || (p!=View::npos && p==best && names[j].size()>names[variant].size())) {
                        best=p;variant=j;
                    }
                }
                if(best==View::npos){literal(out,line.substr(start));break;}
                literal(out,line.substr(start,best-start));out+=static_cast<char>(first+variant);
                start=best+names[variant].size();++refs;
            }
        }
        update(line);
    }
public:
    void observe(View line) { update(line); }
    bool would_replace(View value) const {
        for (const auto &name : names)
            if (!name.empty() && value.find(name) != View::npos) return true;
        return false;
    }
    Bytes encode(View data,uint64_t &refs) {
        Bytes out;out.reserve(data.size());
        for(size_t i=0;i<data.size();) {
            size_t end=data.find('\n',i);
            if(end==View::npos)end=data.size();
            encode_line(out,data.substr(i,end-i),refs);
            if(end<data.size())out+='\n';
            i=end+1;
        }
        return out;
    }
    Bytes decode(View data,size_t limit) {
        Bytes out;out.reserve(limit);size_t start=0;
        for(size_t i=0;i<data.size();) {
            unsigned c=static_cast<unsigned char>(data[i++]);
            if(c>=first && c<escape_title) {
                const auto &s=names[c-first];
                require(!s.empty() && s.size()<=limit-out.size(),"invalid title reference");
                out+=s;
            } else {
                if(c==escape_title) {
                    require(i<data.size(),"truncated title escape");c=static_cast<unsigned char>(data[i++]);
                    require(c>=first && c<=escape_title,"invalid title escape");
                }
                require(out.size()<limit,"title expansion exceeds block");
                if(c=='\n') {update(View(out).substr(start));start=out.size()+1;}
                out+=static_cast<char>(c);
            }
        }
        if(start<out.size())update(View(out).substr(start));
        require(out.size()==limit,"incorrect title expansion length");
        return out;
    }
};
}
