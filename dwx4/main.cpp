// SPDX-License-Identifier: GPL-3.0-only
#define _FILE_OFFSET_BITS 64
#include "topics.hpp"
#include "titles.hpp"
#include "markup.hpp"
#include "archive_io.hpp"
#include <cerrno>
#include <cstdlib>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

namespace dw {
constexpr unsigned use_words=8, use_topics=16, small_memory=32, shared_titles=64, fold_markup=128;
constexpr std::pair<View,unsigned> profiles[]={{"raw",0},{"words",8},{"fields",9},{"templates",11},{"topics",27},{"titles",91},{"wiki",219},{"lean",251}};
constexpr View trailer="DWX4-SFX";
inline unsigned profile(View name) {
    for(auto &p:profiles) if(name==p.first)return p.second;
    throw std::runtime_error("unknown profile");
}
inline Bytes le(uint64_t v,unsigned n){
    Bytes s;
    for(unsigned j=0;j<n;++j){s+=static_cast<char>(v&255);v>>=8;}return s;
}
inline uint64_t from_le(View s) {
    uint64_t v=0;for(auto j=s.rbegin();j!=s.rend();++j)v=v*256+static_cast<unsigned char>(*j);return v;
}
inline uint32_t checksum(View s) {
    static const auto table=[]{
        std::array<uint32_t,256> values{};
        for(unsigned i=0;i<256;++i){uint32_t n=i;for(int b=0;b<8;++b)n=(n>>1)^((0u-(n&1))&0xedb88320u);values[i]=n;}
        return values;
    }();
    uint32_t crc=UINT32_MAX;for(unsigned char c:s)crc=(crc>>8)^table[(crc^c)&255];return ~crc;
}
struct Output {
    Bytes name, part;File file{};
    explicit Output(const char *path):name(path),part(name+".part-XXXXXX"){
        int fd=mkstemp(part.data());require(fd>=0,"cannot create output temporary file");
        FILE *f=fdopen(fd,"w+b");
        if(!f){close(fd);unlink(part.c_str());throw std::runtime_error("cannot open output temporary file");}
        file.reset(f);
    }
    void commit(bool executable=false) {
        if(executable)require(!fchmod(fileno(file.get()),0755),"cannot mark archive executable");
        require(!std::fclose(file.release()),"output close failed");
        require(::link(part.c_str(),name.c_str())==0,"cannot publish output (destination must be new)");
    }
    ~Output(){unlink(part.c_str());}
};
struct Envelope {uint64_t base,bytes;bool executable;};
inline Envelope envelope(FILE *f){
    uint64_t n=length(f);char tail[16];
    if(n>=16){
        seek_file(f,n-16);
        require(std::fread(tail,1,16,f)==16,"archive read failed");
        if(View(tail+8,8)==trailer){
            uint64_t base=from_le(View(tail,8));require(base>0 && base<n-16,"invalid executable archive size");
            return {base,n-16-base,true};
        }
    }
    return {0,n,false};
}
inline void append(FILE *in,FILE *out,uint64_t bytes) {
    seek_file(in,0);std::array<char,65536> buf{};
    while(bytes){size_t k=std::min<uint64_t>(buf.size(),bytes);require(std::fread(buf.data(),1,k,in)==k,"short file");write_file(out,View(buf.data(),k));bytes-=k;}
}
void encode(const char *name,FILE *tape,unsigned mode){
    auto f=open_file(name,"rb");uint64_t raw_length=length(f.get());
    size_t frame_size=(mode&small_memory)?block_size/4:block_size;
    Vocabulary v=(mode&use_words)?learn(f.get(),(mode&small_memory)?8192:max_vocab):Vocabulary{};
    Encoder words(v);Cache cache;Markup markup;uint64_t hits=0,matched=0,seen=0,title_refs=0;
    Bytes h="DWX4";h+=static_cast<char>(mode);h+=le(raw_length,8);put_var(h,v.size());
    for(auto &word:v){h+=static_cast<char>(word.size());h+=word;}
    write_file(tape,h);
    Bytes buf;buf.reserve(frame_size);
    auto block=[&]{
        if(buf.empty())return;
        Bytes titles=(mode&shared_titles)?PageTitle{}.encode(buf,title_refs):Bytes{};
        View rows=(mode&shared_titles)?View(titles):View(buf);
        Bytes grouped=(mode&1)?route(rows,mode,cache,hits,matched):Bytes{};
        View body=(mode&1)?View(grouped):rows;
        Bytes compact=(mode&fold_markup)?markup.encode(body):Bytes{};
        if(mode&fold_markup)body=compact;
        Bytes coded=(mode&use_words)?words.encode(body):Bytes{};
        View payload=(mode&use_words)?View(coded):body;
        Bytes hdr="B";put_var(hdr,buf.size());if(mode&shared_titles)put_var(hdr,rows.size());put_var(hdr,payload.size());hdr+=le(checksum(buf),4);
        write_file(tape,hdr);write_file(tape,payload);seen+=buf.size();buf.clear();
    };
    auto consume=[&](View s){
        while(!s.empty()){size_t k=std::min(frame_size-buf.size(),s.size());buf.append(s.substr(0,k));s.remove_prefix(k);if(buf.size()==frame_size)block();}
    };
    if(mode&use_topics){
        auto second=open_file(name,"rb");
        topic_windows(f.get(),second.get(),[&](const Bytes &info){Bytes hdr="P";put_var(hdr,info.size());write_file(tape,hdr);write_file(tape,info);},consume,block);
    }else{
        std::array<char,65536> piece{};
        while(size_t n=std::fread(piece.data(),1,piece.size(),f.get()))consume(View(piece.data(),n));
        require(!std::ferror(f.get()),"raw input read failed");block();
    }
    require(seen==raw_length,"input size changed during encoding");write_file(tape,"E");
    std::fprintf(stderr,"vocabulary=%zu template_hits=%llu matched_source_bytes=%llu title_refs=%llu\n",v.size(),
                 static_cast<unsigned long long>(hits),static_cast<unsigned long long>(matched),static_cast<unsigned long long>(title_refs));
}
void decode(FILE *input,FILE *out) {
    auto env=envelope(input);Unpack tape(input,env.base,env.bytes);
    require(tape.get(4)=="DWX4","invalid DWX4 magic");unsigned mode=tape.byte();
    require(std::any_of(std::begin(profiles),std::end(profiles),[mode](auto p){return p.second==mode;}),"unsupported DWX4 profile");
    uint64_t expected=from_le(tape.get(8)),seen=0;
    unsigned n=tape.var(max_vocab);require(!n || (mode&use_words),"unexpected vocabulary");
    Vocabulary v;v.reserve(n);
    for(unsigned j=0;j<n;++j){
        unsigned len=tape.byte();require(len>=2 && len<=max_word,"invalid dictionary word length");
        Bytes w=tape.get(len);for(unsigned char c:w)require(c>='a' && c<='z',"invalid word spelling");v.push_back(std::move(w));
    }
    Cache cache;Markup markup;Scatter scatter(out);
    for(;;){
        unsigned op=tape.byte();
        if(op=='E')break;
        if(op=='P'){require(mode&use_topics,"unexpected page plan");scatter.begin(tape.get(tape.var(window_records*8+8)));continue;}
        require(op=='B',"invalid frame tag");
        unsigned raw=tape.var(block_size);
        unsigned row_size=(mode&shared_titles)?tape.var(2*block_size):raw;
        unsigned packed=tape.var(8*block_size+8192);require(raw && raw<=expected-seen,"invalid frame size");
        uint32_t crc=static_cast<uint32_t>(from_le(tape.get(4)));Bytes b=tape.get(packed);
        if(mode&use_words)b=expand_words(b,v,8*block_size+8192);
        if(mode&fold_markup)b=markup.decode(b,4*block_size+2048);
        if(mode&1)b=unroute(b,row_size,mode,cache);
        if(mode&shared_titles)b=PageTitle{}.decode(b,raw);
        require(b.size()==raw && checksum(b)==crc,"restored block checksum mismatch");
        if(mode&use_topics)scatter.write(b);else write_file(out,b);seen+=b.size();
    }
    require(seen==expected && scatter.done(),"incomplete DWX4 output");tape.finish();
}
void package(FILE *data,FILE *out) {
    auto self=open_file("/proc/self/exe","rb");auto image=envelope(self.get());
    uint64_t n=image.executable?image.base:length(self.get());
    append(self.get(),out,n);append(data,out,length(data));write_file(out,le(n,8));write_file(out,trailer);
}
}
int main(int argc,char **argv){
    using namespace dw;
    try {
        if(argc==2){
            auto self=open_file("/proc/self/exe","rb");require(envelope(self.get()).executable,"usage: dwx4 encode INPUT OUTPUT [PROFILE] | decode INPUT OUTPUT | pack STREAM RUN");
            Output out(argv[1]);decode(self.get(),out.file.get());out.commit();return 0;
        }
        require(argc==4 || argc==5,"usage: dwx4 encode INPUT OUTPUT [wiki|lean|titles|topics|templates|fields|words|raw] | decode INPUT OUTPUT | pack STREAM RUN");
        View cmd=argv[1];Output target(argv[3]);
        if(cmd=="encode"){
            unsigned mode=profile(argc==5?argv[4]:"wiki");
            auto tmp=open_scratch();encode(argv[2],tmp.get(),mode);
            archive_pack(tmp.get(),target.file.get(),mode&small_memory);
        }else if(cmd=="decode" && argc==4){auto f=open_file(argv[2],"rb");decode(f.get(),target.file.get());}
        else if(cmd=="pack" && argc==4){auto f=open_file(argv[2],"rb");Unpack check(f.get(),0,length(f.get()));require(check.get(4)=="DWX4","invalid DWX4 stream");package(f.get(),target.file.get());}
        else throw std::runtime_error("unknown operation or argument count");
        target.commit(cmd=="pack");return 0;
    } catch(const std::exception &e){std::fprintf(stderr,"dwx4: %s\n",e.what());return 1;}
}
