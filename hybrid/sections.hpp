// SPDX-License-Identifier: GPL-3.0-only
// cmix-neif normally places encoder functions into a special linker section.
// The hybrid uses an ordinary ELF and both directions share one worker.
#ifndef ENC_ONLY_H
#define ENC_ONLY_H
#define ENC_ONLY __attribute__((noinline))
#define DIR_INLINE inline __attribute__((always_inline))
#endif
