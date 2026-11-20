// SPDX-License-Identifier: GPL-3.0-only
static int DenseStreamTest(int argc, char** argv) {
  if (argc != 5) return 64;
  bool enc = strcmp(argv[1], "encode-stream") == 0;
  char* end;
  unsigned long long n = strtoull(argv[2], &end, 10);
  if (*end || n > 1000000000ULL) return 64;
  FILE* in = fopen(argv[3], "rb");
  FILE* out = fopen(argv[4], "wbx");
  if (!in || !out) return 65;
  std::vector<bool> vocab(256);
  vocab_frozen::FillVocab(&vocab);
  srand(SEED);
  mallopt(M_MMAP_THRESHOLD, 1 << 20);
  console_progress::Begin();
  Predictor p(vocab);
  unsigned long long packed = 0;
  if (enc) Compress(n, in, out, &packed, &p);
  else Decompress(n, in, out, &p);
  fprintf(stderr, "\nDENSE_OBSERVATIONS %llu %llu\n", p.DenseInsertions(), p.DensePositions());
  const bool io_error = ferror(in) || ferror(out);
  const int in_status = fclose(in);
  const int out_status = fclose(out);
  return io_error || in_status || out_status;
}
