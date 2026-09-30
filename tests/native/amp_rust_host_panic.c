// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — standalone host Rust panic termination

#include <stdlib.h>

/** Abort the standalone host process when its actual Rust panic handler is entered. */
_Noreturn void witness_amp_rust_panic(void);
_Noreturn void witness_amp_rust_panic(void) { abort(); }
