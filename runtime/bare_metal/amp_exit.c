// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — finished board controller remains parked on its dedicated hart

#include "amp_contract.h"

void witness_amp_exit(void) {
    __asm__ volatile("csrw mie,zero" ::: "memory");
    for (;;) __asm__ volatile("wfi" ::: "memory");
}
