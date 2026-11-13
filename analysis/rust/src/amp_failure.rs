// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — read errors and refusals of AMP inputs

//! Tell a read error from a refusal, as the Python AMP readers raise them.
//!
//! The Python readers raise `OSError` when a file cannot be opened or read
//! and `ValueError` when what they read is refused. The native readers keep
//! that distinction and Python's text for both.

/// Why an AMP input cannot be read or admitted, as Python's readers raise it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AmpFailure {
    /// Python's `OSError`, with its text: a file cannot be opened or read.
    Os(String),
    /// Python's `ValueError`, with its text: what was read is refused.
    Refused(String),
}
