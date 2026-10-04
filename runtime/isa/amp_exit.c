// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — target-produced ISA host completion after real logger acknowledgement

#include "../bare_metal/amp_contract.h"

/** Spike's documented target/host exit channel, present only in the ISA test image. */
__attribute__((section(".tohost"), aligned(64))) volatile uint64_t tohost;
/** The paired inbound HTIF word is required by the actual ELF loader. */
__attribute__((section(".tohost"), aligned(64))) volatile uint64_t fromhost;

void witness_amp_exit(void) {
    __asm__ volatile("fence rw,rw" ::: "memory");
    tohost = 1;
    for (;;)
        __asm__ volatile("wfi" ::: "memory");
}
