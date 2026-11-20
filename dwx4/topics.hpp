// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include "rows.hpp"
#include <numeric>

namespace dw {
constexpr unsigned window_bytes=128u<<20, window_records=16384, scan_bytes=512u<<10;
constexpr View page_mark="\n  <page>\n";
struct Page {
    uint64_t offset=0, title=0;
    uint32_t length=0, family=0, primary=0;
    std::array<uint32_t,10> labels{};
    unsigned label_count=0;
};
inline unsigned lower(unsigned c) { return c>=65 && c<=90 ? c+32:c; }
inline uint64_t leading_key(View s) {
    uint64_t k=0;
    for(unsigned i=0;i<8;++i) k=(k<<8) | (i<s.size()?lower(static_cast<unsigned char>(s[i])):0);
    return k;
}
inline uint32_t label_hash(View s) {
    uint32_t h=2166136261u;
    for(unsigned char c:s) { if(digit(c)) c='#'; if(c=='_') c=' '; h=(h^lower(c))*16777619u; }
    return h?h:1;
}
inline View between(View s,View a,View b) {
    auto i=s.find(a);if(i==View::npos)return {}; i+=a.size();
    auto j=s.find(b,i);return j==View::npos?View{}:s.substr(i,j-i);
}
inline void collect_labels(View s, View mark, View stops, unsigned budget, Page &p) {
    size_t pos=0;
    while (budget && p.label_count<p.labels.size()) {
        pos=s.find(mark,pos); if(pos==View::npos) break;
        pos+=mark.size();
        View tail=s.substr(pos,80);size_t len=tail.find_first_of(stops);
        if(len<3 || len==View::npos) continue;
        View key=tail.substr(0,len);
        if(key.starts_with("cite ")||key=="main"||key=="Main"||key=="ref"||key=="note"||key=="clear") continue;
        uint32_t id=label_hash(key);
        auto end=p.labels.begin()+p.label_count;
        if (std::find(p.labels.begin(),end,id)!=end) continue;
        p.labels[p.label_count++]=id;--budget;
    }
}
inline Page describe(View s,uint64_t offset) {
    Page p;p.offset=offset;p.length=static_cast<uint32_t>(s.size());
    View name=between(s,"    <title>","</title>");
    p.title=leading_key(name);
    size_t a=s.find(text_open);
    View body=a==View::npos ? s : s.substr(a+text_open.size());
    if(body.starts_with("#REDIRECT")||body.starts_with("#redirect")||body.starts_with("#Redirect")){
        p.family=1;p.title=leading_key(between(body,"[[","]]"));return p;
    }
    if(body.find("median income")!=View::npos && body.find("population density")!=View::npos){
        p.family=2;size_t comma=name.rfind(", ");
        if(comma!=View::npos)p.primary=label_hash(name.substr(comma+2));
        return p;
    }
    if(name.starts_with("Image:")){p.family=3;p.title=leading_key(name.substr(6));return p;}
    p.family=4;
    collect_labels(body,"{{","|}\r\n<",4,p);
    collect_labels(body,"[[Category:","]|\r\n",6,p);
    return p;
}
using Order=std::vector<unsigned>;
inline Order order_pages(std::vector<Page> &pages) {
    std::unordered_map<uint32_t,unsigned> frequency;
    for(auto &p:pages) for(unsigned j=0;j<p.label_count;++j) ++frequency[p.labels[j]];
    for(auto &p:pages) if(p.family==4) {
        unsigned best=1;
        for(unsigned j=0;j<p.label_count;++j) {
            unsigned n=frequency.at(p.labels[j]);
            if(n>best) {best=n;p.primary=p.labels[j];}
        }
        if(!p.primary)p.family=5;
    }
    Order order(pages.size());std::iota(order.begin(),order.end(),0);
    std::stable_sort(order.begin(),order.end(),[&](unsigned i,unsigned j){
        const auto &a=pages[i], &b=pages[j];
        if(a.family!=b.family)return a.family<b.family;
        if(a.primary!=b.primary)return a.primary<b.primary;
        if(a.family==5) return false;
        return a.title<b.title;
    });
    return order;
}
inline Bytes schedule(const std::vector<Page> &pages,const Order &order) {
    Bytes out; put_var(out,pages.size());
    for(auto &p:pages)put_var(out,p.length);
    int last=0;
    for(unsigned id:order) {
        int delta=static_cast<int>(id)-last;
        put_var(out,delta<0?static_cast<unsigned>(-2*delta-1):static_cast<unsigned>(2*delta));
        last=id;
    }
    return out;
}
inline void seek_file(FILE *f,uint64_t off) {
    require(off<=static_cast<uint64_t>(std::numeric_limits<off_t>::max()) &&
            fseeko(f,static_cast<off_t>(off),SEEK_SET)==0,"cannot seek file");
}
inline void write_file(FILE *f,View s){
    require(std::fwrite(s.data(),1,s.size(),f)==s.size(),"file write failed");
}
template<class Plan,class Data,class Finish>
void topic_windows(FILE *scan, FILE *copy, Plan plan,Data consume,Finish finish) {
    std::vector<Page> pages;pages.reserve(window_records);
    unsigned window=0;
    Bytes chunk(scan_bytes,0),record;
    auto flush=[&]{
        if(pages.empty())return;
        auto order=order_pages(pages);plan(schedule(pages,order));
        for(unsigned id:order) {
            const auto &p=pages[id];seek_file(copy,p.offset);record.resize(p.length);
            require(fread(record.data(),1,record.size(),copy)==record.size(),"input changed during page read");
            consume(record);
        }
        finish();window=0;pages.clear();
    };
    uint64_t offset=0;size_t n;
    while((n=fread(chunk.data(),1,chunk.size(),scan))) {
        View slab(chunk.data(),n);
        for(size_t pos=0;pos<n;) {
            auto end=slab.find(page_mark,pos);
            end=end==View::npos?n:end+1;
            View span=slab.substr(pos,end-pos);
            if(pages.size()==window_records || window+span.size()>window_bytes) flush();
            pages.push_back(describe(span,offset+pos));
            window+=span.size();pos=end;
        }
        offset+=n;
    }
    require(!ferror(scan),"input read failed");flush();
}
class Scatter {
    FILE *output;
    std::vector<unsigned> offsets, order;
    uint64_t base=0;
    unsigned index=0,within=0,total=0;
public:
    explicit Scatter(FILE *f):output(f){}
    bool done() const {return index==order.size();}
    void begin(View info) {
        require(done(),"incomplete preceding page window");
        base+=total; total=0;index=0;within=0;
        size_t pos=0;unsigned n=take_var(info,pos,window_records);
        require(n>0,"empty page schedule");
        offsets.assign(n+1,0);
        for(unsigned j=0;j<n;++j) {
            unsigned len=take_var(info,pos,scan_bytes);
            require(len && len<=window_bytes-total,"invalid page span size");
            total+=len;offsets[j+1]=total;
        }
        std::vector<bool> seen(n,false);
        order.resize(n);int last=0;
        for(unsigned &id:order) {
            unsigned z=take_var(info,pos,window_records*2);
            last+=z&1?-static_cast<int>((z+1)/2):static_cast<int>(z/2);
            require(last>=0 && static_cast<unsigned>(last)<n && !seen[last],"invalid page permutation");
            id=static_cast<unsigned>(last);seen[id]=true;
        }
        require(pos==info.size(),"extra page schedule bytes");
    }
    void write(View s) {
        while(!s.empty()) {
            require(!done(),"body exceeds page window");
            unsigned id=order[index],len=offsets[id+1]-offsets[id];
            if(!within)seek_file(output,base+offsets[id]);
            size_t n=std::min<size_t>(len-within,s.size());
            write_file(output,s.substr(0,n)); s.remove_prefix(n);within+=n;
            if(within==len){++index;within=0;}
        }
    }
};
}
