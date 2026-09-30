// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — actual zero-claim trap before original initialization

#include "runtime/bare_metal/amp_contract.h"

/** Retain the complete original firmware initialization and interrupt lifecycle. */
void __real_witness_amp_main(void);
/** Exercise a real empty PLIC claim before the original producer initializes. */
void __wrap_witness_amp_main(void);

void __wrap_witness_amp_main(void) {
    witness_amp_trap(UINT64_C(1) << 63 | UINT64_C(11), 0);
    __real_witness_amp_main();
}
