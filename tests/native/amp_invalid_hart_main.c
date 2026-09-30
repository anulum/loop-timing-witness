// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — post-entry invalid platform-hart diagnostic

#include "runtime/bare_metal/amp_contract.h"

void __real_witness_amp_main(void);
void __wrap_witness_amp_main(void);

/** Change the admitted owner only after assembly selected the actual running hart. */
void __wrap_witness_amp_main(void) {
    volatile uint32_t *const hart = (volatile uint32_t *)(uintptr_t)&witness_amp_platform;
    *hart = 0;
    __real_witness_amp_main();
}
