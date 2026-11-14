// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — target-produced ISA completion channel of an AMP image

//! Admit an ISA image's completion channel as the Python module
//! `amp_exit_channel` does for ISA images.
//!
//! The analysis admits only ISA images, whose firmware reports completion
//! through two HTIF words; Python's other mode, the parked board exit, is
//! decided when a board image is prepared and has no counterpart here.

use crate::amp_elf::{LoadSegment, READ_WRITE};
use crate::amp_image_contract::{OBJECT_KIND, file_backed, file_bytes, symbol_map};

/// Bytes of one HTIF word.
const CHANNEL_BYTES: u64 = 8;
/// Alignment of each HTIF word.
const CHANNEL_ALIGNMENT: u64 = 64;

/// Require two distinct, aligned, initially zero writable HTIF words.
///
/// `segments` are the image's admitted load segments.
///
/// # Errors
///
/// Python's refusal text when the symbols are invalid, a channel symbol is
/// missing, a channel is not one aligned word in one writable segment's file
/// bytes, a channel is preloaded, or both channels share an address.
pub fn admit_exit_channel(content: &[u8], segments: &[LoadSegment]) -> Result<(), String> {
    let symbols = symbol_map(content)?;
    let names = ["tohost", "fromhost"];
    if names.iter().any(|name| !symbols.contains_key(*name)) {
        return Err("ISA firmware requires both original HTIF completion channel symbols".into());
    }
    let mut addresses = Vec::with_capacity(names.len());
    for name in names {
        let symbol = symbols[name];
        let owners: Vec<&LoadSegment> = segments
            .iter()
            .filter(|segment| file_backed(segment, READ_WRITE, symbol.address, symbol.size))
            .collect();
        let [owner] = owners.as_slice() else {
            return Err("ISA completion channel must be one aligned writable original word".into());
        };
        if symbol.kind != OBJECT_KIND
            || symbol.size != CHANNEL_BYTES
            || symbol.address % CHANNEL_ALIGNMENT != 0
        {
            return Err("ISA completion channel must be one aligned writable original word".into());
        }
        if file_bytes(content, owner, &symbol)
            .iter()
            .any(|byte| *byte != 0)
        {
            return Err(
                "ISA completion channel cannot be preloaded before target execution".into(),
            );
        }
        addresses.push(symbol.address);
    }
    if addresses[0] == addresses[1] {
        return Err("ISA completion channels must have distinct original addresses".into());
    }
    Ok(())
}
