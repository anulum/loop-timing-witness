// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — host-only Rust coverage runtime and genuine panic sink

#include <stdlib.h>

extern void __llvm_profile_initialize_file(void);
extern int __llvm_profile_write_file(void);

/** Initialise the profiler in a C executable linked to a no-std Rust static library. */
__attribute__((constructor)) static void initialize_profile(void) {
    __llvm_profile_initialize_file();
}

/** Flush normal C client observations after its public entry points return. */
__attribute__((destructor)) static void flush_profile(void) {
    if (__llvm_profile_write_file() != 0) _Exit(43);
}

/** Flush the unchanged Rust panic handler's observations before stopping the host process. */
_Noreturn void witness_amp_rust_panic(void);
_Noreturn void witness_amp_rust_panic(void) {
    if (__llvm_profile_write_file() != 0) _Exit(43);
    _Exit(42);
}
