// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — native runtime identity, crate-internal controls

//! The FIFO capacity check compares as Python's `records == 1 << bits` does,
//! including for receipts that claim 64 or more address bits.

use super::capacity_matches;

#[test]
fn the_fifo_capacity_matches_its_address_bits_without_a_fixed_width_shift() {
    assert!(capacity_matches(1024, 10));
    assert!(capacity_matches(1, 0));
    assert!(!capacity_matches(1024, 11));
    assert!(!capacity_matches(u32::MAX, 32));
    for bits in [63, 64, 65, 65535, u64::MAX] {
        assert!(!capacity_matches(u32::MAX, bits), "{bits}");
    }
}
