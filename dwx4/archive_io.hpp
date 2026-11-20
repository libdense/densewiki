// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include "transform.hpp"
#include <sys/stat.h>
#include <unistd.h>
#if __has_include(<archive.h>) && __has_include(<archive_entry.h>)
#include <archive.h>
#include <archive_entry.h>
#else
// Public libarchive 3 ABI, for Linux installations with only the runtime package.
extern "C" {
struct archive; struct archive_entry;
archive *archive_write_new(), *archive_read_new();
archive_entry *archive_entry_new();
void archive_entry_set_pathname(archive_entry*,const char*), archive_entry_set_size(archive_entry*,int64_t),
     archive_entry_set_filetype(archive_entry*,unsigned), archive_entry_set_perm(archive_entry*,unsigned),
     archive_entry_free(archive_entry*);
const char *archive_entry_pathname(archive_entry*), *archive_error_string(archive*), *archive_version_string();
int64_t archive_entry_size(archive_entry*);
int archive_write_set_format_7zip(archive*), archive_write_set_options(archive*,const char*),
    archive_write_set_bytes_per_block(archive*,int),archive_write_open_fd(archive*,int),
    archive_write_header(archive*,archive_entry*),archive_write_close(archive*),archive_write_free(archive*),
    archive_read_support_format_7zip(archive*),archive_read_set_seek_callback(archive*,int64_t(*)(archive*,void*,int64_t,int)),
    archive_read_open2(archive*,void*,int(*)(archive*,void*),ssize_t(*)(archive*,void*,const void**),
                      int64_t(*)(archive*,void*,int64_t),int(*)(archive*,void*)),
    archive_read_next_header(archive*,archive_entry**),archive_read_close(archive*),archive_read_free(archive*);
ssize_t archive_write_data(archive*,const void*,size_t),archive_read_data(archive*,void*,size_t);
}
#endif
#include <memory>
#include <cstdlib>

namespace dw {
struct FileCloser { void operator()(FILE *f) const { std::fclose(f); } };
using File=std::unique_ptr<FILE,FileCloser>;
inline File checked_file(FILE *f) {require(f!=nullptr,"cannot open file");return File(f);}
inline File open_file(const char *p,const char *m) {return checked_file(std::fopen(p,m));}
inline File open_scratch() {
    const char *dir=std::getenv("TMPDIR");
    Bytes path=Bytes(dir && *dir?dir:"/tmp")+"/dwx4-XXXXXX";
    int fd=mkstemp(path.data());require(fd>=0,"cannot create scratch file");
    if(unlink(path.c_str())){close(fd);throw std::runtime_error("cannot unlink scratch file");}
    FILE *f=fdopen(fd,"w+b");
    if(!f){close(fd);throw std::runtime_error("cannot open scratch file");}
    return checked_file(f);
}
inline uint64_t length(FILE *f) {
    struct stat s{};require(!fstat(fileno(f),&s) && S_ISREG(s.st_mode) && s.st_size>=0,"expected regular file");
    return static_cast<uint64_t>(s.st_size);
}
inline void archive_ok(archive *a,int status) {
    if(status<0) throw std::runtime_error(archive_error_string(a)?archive_error_string(a):"archive operation failed");
}
inline void archive_pack(FILE *tape, FILE *out, bool lean) {
    require(!fflush(tape) && !fflush(out),"file flush failed");
    seek_file(tape,0);
    std::unique_ptr<archive,decltype(&archive_write_free)> a(archive_write_new(),&archive_write_free);
    require(bool(a),"cannot allocate archive writer");
    archive_ok(a.get(),archive_write_set_format_7zip(a.get()));
    archive_ok(a.get(),archive_write_set_options(a.get(),lean?"compression=lzma2,compression-level=1":"compression=ppmd"));
    archive_ok(a.get(),archive_write_set_bytes_per_block(a.get(),0));
    archive_ok(a.get(),archive_write_open_fd(a.get(),fileno(out)));
    std::unique_ptr<archive_entry,decltype(&archive_entry_free)> e(archive_entry_new(),&archive_entry_free);
    require(bool(e),"cannot allocate archive entry");
    archive_entry_set_size(e.get(),static_cast<int64_t>(length(tape)));
    archive_entry_set_pathname(e.get(),"DWX4");archive_entry_set_filetype(e.get(),0100000);archive_entry_set_perm(e.get(),0644);
    archive_ok(a.get(),archive_write_header(a.get(),e.get()));
    std::array<char,65536> buf{};
    while(size_t n=std::fread(buf.data(),1,buf.size(),tape))
        require(archive_write_data(a.get(),buf.data(),n)==static_cast<ssize_t>(n),"compressed archive write failed");
    require(!std::ferror(tape),"temporary file read failed");
    archive_ok(a.get(),archive_write_close(a.get()));
}
struct Slice {
    FILE *file;int64_t base,bytes,pos=0;std::array<char,65536> buf{};
    static int64_t seek(archive*,void *cookie,int64_t off,int whence) {
        auto &s=*static_cast<Slice*>(cookie);
        int64_t from=whence==SEEK_SET?0:whence==SEEK_CUR?s.pos:whence==SEEK_END?s.bytes:-1;
        if(from<0 || off < -from || off>s.bytes-from || fseeko(s.file,s.base+from+off,SEEK_SET)) return -1;
        return s.pos=from+off;
    }
    static ssize_t read(archive*,void *cookie,const void **out){
        auto &s=*static_cast<Slice*>(cookie);*out=s.buf.data();
        size_t want=std::min<uint64_t>(s.buf.size(),s.bytes-s.pos);
        size_t n=std::fread(s.buf.data(),1,want,s.file);
        if(n!=want)return -1;
        s.pos+=n;return static_cast<ssize_t>(n);
    }
    static int64_t skip(archive *a,void *cookie,int64_t req) {
        auto &s=*static_cast<Slice*>(cookie);
        int64_t n=std::min(req,s.bytes-s.pos);
        return n<=0?0:seek(a,cookie,n,SEEK_CUR)<0?-1:n;
    }
};
class Unpack {
    Slice slice;
    std::unique_ptr<archive,decltype(&archive_read_free)> a;
    Bytes buffer;
    size_t pos=0,available=0;
    size_t refill() {
        auto n=archive_read_data(a.get(),buffer.data(),buffer.size());
        require(n>=0,"PPMd data or checksum error");
        pos=0;available=static_cast<size_t>(n);return available;
    }
public:
    Unpack(FILE *f,uint64_t base,uint64_t bytes):slice{f,static_cast<int64_t>(base),static_cast<int64_t>(bytes)},
        a(archive_read_new(),&archive_read_free),buffer(65536,0){
        require(bool(a),"cannot allocate archive reader");
        seek_file(f,base);
        std::array<unsigned char,32> header{};
        require(bytes>=header.size() && fread(header.data(),1,header.size(),f)==header.size(),
                "truncated 7z header");
        constexpr unsigned char signature[]={0x37,0x7a,0xbc,0xaf,0x27,0x1c};
        auto number=[&](size_t offset) {
            uint64_t value=0;
            for(int j=7;j>=0;--j)value=value*256+header[offset+j];
            return value;
        };
        uint64_t offset=number(12),size=number(20);
        require(!std::memcmp(header.data(),signature,sizeof(signature)) && offset<=bytes-32 &&
                size==bytes-32-offset,"incorrect 7z extent");
        seek_file(f,base);
        archive_ok(a.get(),archive_read_support_format_7zip(a.get()));
        archive_ok(a.get(),archive_read_set_seek_callback(a.get(),Slice::seek));
        archive_ok(a.get(),archive_read_open2(a.get(),&slice,nullptr,Slice::read,Slice::skip,nullptr));
        archive_entry *e=nullptr;
        require(archive_read_next_header(a.get(),&e)==0 && archive_entry_pathname(e) &&
                !std::strcmp(archive_entry_pathname(e),"DWX4"),"missing DWX4 member");
    }
    void read(char *dst,size_t n) {
        while(n) {
            if(pos==available)require(refill()!=0,"truncated DWX4 member");
            auto k=std::min(n,available-pos);std::memcpy(dst,buffer.data()+pos,k);n-=k;pos+=k;dst+=k;
        }
    }
    Bytes get(size_t n) { Bytes s(n,0);read(s.data(),n);return s; }
    unsigned byte(){char c;read(&c,1);return static_cast<unsigned char>(c);}
    unsigned var(unsigned max) {
        uint64_t n=0;
        for(unsigned shift=0;shift<35;shift+=7) {
            auto b=byte();n|=uint64_t(b&127)<<shift;
            if(b<128) {require(n<=max && (!shift || b),"invalid archive integer");return static_cast<unsigned>(n);}
        }
        throw std::runtime_error("oversized archive integer");
    }
    void finish() {
        require(pos==available && !refill(),"extra bytes in DWX4 member");
        archive_entry *e=nullptr;require(archive_read_next_header(a.get(),&e)==1,"extra archive member");
        archive_ok(a.get(),archive_read_close(a.get()));
    }
};
}
