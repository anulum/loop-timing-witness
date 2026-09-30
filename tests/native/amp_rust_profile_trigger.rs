// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — host-only genuine panic producer for Rust coverage

//! Trigger a real no-std panic that links to the production adapter's unchanged panic handler.
#![no_std]

/// Produce a genuine Rust panic for the host-only C ABI coverage process.
#[unsafe(no_mangle)]
pub extern "C" fn witness_profile_trigger_panic() -> ! {
    panic!("profiled Rust panic")
}
