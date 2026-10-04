// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — actual target instruction delay before original initialization

#include <stdint.h>

/** Retain the complete original firmware initialization and interrupt lifecycle. */
void __real_witness_amp_main(void);
/** Execute real RV64 instructions before the original producer publishes its ABI. */
void __wrap_witness_amp_main(void);

void __wrap_witness_amp_main(void) {
    volatile uint32_t progress = 0;
    for (uint32_t index = 0; index < 5000; ++index)
        progress = progress + 1;
    __real_witness_amp_main();
}
