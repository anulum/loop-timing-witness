// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — host-only public entry for a genuine Rust panic

/** Enter the test-owned Rust panic producer from a real C executable. */
_Noreturn void witness_profile_trigger_panic(void);

/** Return only if the required Rust panic fails to terminate the host process. */
int main(void) { witness_profile_trigger_panic(); }
