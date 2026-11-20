CXX ?= c++
CPPFLAGS ?= -D_GLIBCXX_USE_CXX11_ABI=0
CXXFLAGS ?= -O3 -std=c++20 -Wall -Wextra -Wpedantic
LDLIBS ?= -l:libarchive.so.13

dwx4: main.cpp articles.hpp archive_io.hpp markup.hpp rows.hpp titles.hpp topics.hpp transform.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(LDFLAGS) -Wl,--build-id=none -s main.cpp $(LDLIBS) -o $@

.PHONY: test
test: dwx4
	python3 test.py ./dwx4
