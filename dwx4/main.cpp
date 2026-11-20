// SPDX-License-Identifier: GPL-3.0-only
#define _FILE_OFFSET_BITS 64
#include "topics.hpp"
#include "titles.hpp"
#include "articles.hpp"
#include "markup.hpp"
#include "archive_io.hpp"
#include <cerrno>
#include <cstdlib>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

namespace dw {
constexpr unsigned use_words=8, use_topics=16, small_memory=32, shared_titles=64, fold_markup=128;
constexpr std::pair<View,unsigned> profiles[]={{"raw",0},{"words",8},{"fields",9},{"templates",11},{"topics",27},{"titles",91},{"wiki",219},{"lean",251},
    {"film",219|article_facts|only_film},{"facts",219|article_facts},
    {"links",219|article_links},{"article",219|article_modes},
    {"facts-select",219|article_facts|selective_refs},{"links-select",219|article_links|selective_refs},
    {"article-select",219|article_modes|selective_refs}};
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
    const bool local = mode & article_modes;
    ArticleStats stats;
    Bytes h = local ? "DWX5" : "DWX4";
    h += static_cast<char>(mode & 255);
    if (local) h += static_cast<char>(mode >> 8);
    h+=le(raw_length,8);put_var(h,v.size());
    for(auto &word:v){h+=static_cast<char>(word.size());h+=word;}
    write_file(tape,h);
    Bytes buf;buf.reserve(frame_size);
    std::vector<unsigned> cuts;
    auto block=[&]{
        if(buf.empty())return;
        Bytes article, segment_sizes;
        View input = buf;
        bool local_frame = local;
        if (local) {
            uint64_t before = stats.links + stats.facts;
            put_var(segment_sizes, cuts.size());
            size_t start = 0;
            for (size_t j = 0; j <= cuts.size(); ++j) {
                size_t end = j == cuts.size() ? buf.size() : cuts[j];
                auto part = article_segment(input.substr(start, end - start), mode, false, 2 * block_size, stats);
                if (j < cuts.size()) put_var(segment_sizes, part.size());
                article += part;
                start = end;
            }
            put_var(segment_sizes, article.size());
            local_frame = !(mode & selective_refs) || stats.links + stats.facts != before;
            if (local_frame) input = article;
            cuts.clear();
        }
        Bytes titles=(mode&shared_titles)?PageTitle{}.encode(input,title_refs):Bytes{};
        View rows=(mode&shared_titles)?View(titles):input;
        Bytes grouped=(mode&1)?route(rows,mode,cache,hits,matched):Bytes{};
        View body=(mode&1)?View(grouped):rows;
        Bytes compact=(mode&fold_markup)?markup.encode(body):Bytes{};
        if(mode&fold_markup)body=compact;
        Bytes coded=(mode&use_words)?words.encode(body):Bytes{};
        View payload=(mode&use_words)?View(coded):body;
        Bytes hdr = local_frame && (mode & selective_refs) ? "A" : "B";
        put_var(hdr,buf.size());if (local_frame) hdr+=segment_sizes;if(mode&shared_titles)put_var(hdr,rows.size());put_var(hdr,payload.size());hdr+=le(checksum(buf),4);
        write_file(tape,hdr);write_file(tape,payload);seen+=buf.size();buf.clear();
    };
    auto consume=[&](View s){
        // The topic scheduler can splice a partial page to an unrelated fragment.
        // A visible page opener resets both tables. Other joins get an explicit cut.
        if (local && !buf.empty() && (buf.back() != '\n' || !s.starts_with("  <page>\n")))
            cuts.push_back(static_cast<unsigned>(buf.size()));
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
    if (local) std::fprintf(stderr, "boxes=%llu film_boxes=%llu fact_refs=%llu film_fact_refs=%llu link_refs=%llu\n",
        static_cast<unsigned long long>(stats.boxes), static_cast<unsigned long long>(stats.films),
        static_cast<unsigned long long>(stats.facts), static_cast<unsigned long long>(stats.film_facts),
        static_cast<unsigned long long>(stats.links));
}
void decode_tape(Unpack &tape, FILE *out) {
    Bytes magic=tape.get(4);
    const bool local = magic == "DWX5";
    require(local || magic == "DWX4","invalid DWX magic");
    unsigned mode=tape.byte();
    if (local) {
        mode |= tape.byte() << 8;
        require(mode & article_modes, "missing article transform");
    }
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
        const bool sparse = mode & selective_refs;
        require(op=='B' || (sparse && op=='A'),"invalid frame tag");
        const bool local_frame = local && (!sparse || op=='A');
        unsigned raw=tape.var(block_size);
        std::vector<unsigned> parts;
        unsigned article_size = raw;
        if (local_frame) {
            unsigned n = tape.var(std::min<unsigned>(raw, window_records));
            size_t total = 0;
            for (unsigned j = 0; j < n; ++j) {
                unsigned size = tape.var(2 * block_size);
                require(size && size <= 2 * block_size - total, "invalid article segment size");
                parts.push_back(size);
                total += size;
            }
            article_size = tape.var(2 * raw);
            require(total < article_size, "invalid final article segment");
            parts.push_back(static_cast<unsigned>(article_size - total));
        }
        unsigned row_size=(mode&shared_titles)?tape.var(2*block_size):raw;
        unsigned packed=tape.var(8*block_size+8192);require(raw && raw<=expected-seen,"invalid frame size");
        uint32_t crc=static_cast<uint32_t>(from_le(tape.get(4)));Bytes b=tape.get(packed);
        if(mode&use_words)b=expand_words(b,v,8*block_size+8192);
        if(mode&fold_markup)b=markup.decode(b,4*block_size+2048);
        if(mode&1)b=unroute(b,row_size,mode,cache);
        if(mode&shared_titles)b=PageTitle{}.decode(b,article_size);
        if (local_frame) {
            size_t pos = 0;
            Bytes restored;
            restored.reserve(raw);
            ArticleStats unused;
            for (unsigned len : parts) {
                auto part = article_segment(View(b).substr(pos, len), mode, true, raw - restored.size(), unused);
                restored += part;
                pos += len;
            }
            b = std::move(restored);
        }
        require(b.size()==raw && checksum(b)==crc,"restored block checksum mismatch");
        if(mode&use_topics)scatter.write(b);else write_file(out,b);seen+=b.size();
    }
    require(seen==expected && scatter.done(),"incomplete DWX4 output");tape.finish();
}
void decode(FILE *input, FILE *out) {
    auto env = envelope(input);
    struct Mapping {
        void *address = MAP_FAILED;
        size_t size = 0;
        ~Mapping() { if (address != MAP_FAILED) munmap(address, size); }
    } mapping;
    Unpack tape(input, env.base, env.bytes);
    try {
        decode_tape(tape, out);
        return;
    } catch (const std::runtime_error &) {
        if (!tape.reported_truncation()) throw;
    }

    // Some valid PPMd members report truncation with libarchive's chunked input.
    // Retry from the same checked 7z extent, keeping all integrity checks active.
    uint64_t file_bytes = length(input);
    require(file_bytes <= SIZE_MAX, "archive too large to map");
    mapping.size = static_cast<size_t>(file_bytes);
    mapping.address = mmap(nullptr, mapping.size, PROT_READ, MAP_PRIVATE, fileno(input), 0);
    require(mapping.address != MAP_FAILED, "cannot map archive for contiguous read");
    madvise(mapping.address, mapping.size, MADV_SEQUENTIAL);
    tape.reopen_contiguous(static_cast<const char *>(mapping.address) + env.base, env.bytes);
    require(std::fflush(out) == 0 && ftruncate(fileno(out), 0) == 0, "cannot reset output");
    seek_file(out, 0);
    decode_tape(tape, out);
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
        require(argc==4 || argc==5,"usage: dwx4 encode INPUT OUTPUT [wiki|lean|film|facts|links|article|facts-select|links-select|article-select|titles|topics|templates|fields|words|raw] | decode INPUT OUTPUT | pack STREAM RUN");
        View cmd=argv[1];Output target(argv[3]);
        if(cmd=="encode"){
            unsigned mode=profile(argc==5?argv[4]:"wiki");
            auto tmp=open_scratch();encode(argv[2],tmp.get(),mode);
            archive_pack(tmp.get(),target.file.get(),mode&small_memory);
        }else if(cmd=="decode" && argc==4){auto f=open_file(argv[2],"rb");decode(f.get(),target.file.get());}
        else if(cmd=="pack" && argc==4){auto f=open_file(argv[2],"rb");Unpack check(f.get(),0,length(f.get()));Bytes magic=check.get(4);require(magic=="DWX4" || magic=="DWX5","invalid DWX stream");package(f.get(),target.file.get());}
        else throw std::runtime_error("unknown operation or argument count");
        target.commit(cmd=="pack");return 0;
    } catch(const std::exception &e){std::fprintf(stderr,"dwx4: %s\n",e.what());return 1;}
}
