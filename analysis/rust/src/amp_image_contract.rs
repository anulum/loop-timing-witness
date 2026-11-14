// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — compiled contract bytes and stack ownership of an AMP image

//! Admit an AMP image's compiled contract as the Python module
//! `amp_image_contract` does.
//!
//! [`admit_image_contract`] admits the firmware's load segments inside the
//! firmware reservation, the required entry and resource symbols, the three
//! controller entry points in executable file bytes, the platform and run
//! constants as single read-only objects holding exactly the bytes the
//! platform and run give, and the BSS and stack geometry inside writable
//! memory. Every refusal is Python's text for the same first defect.
//!
//! [`admit_image_contract`]: crate::amp_image_contract::admit_image_contract

use crate::amp_elf::{ElfSymbol, LoadSegment, PAGE_BYTES, READ_EXECUTE, READ_WRITE};
use crate::amp_elf::{admit_elf, read_symbols};
use crate::amp_platform::AmpPlatform;
use crate::amp_run_input::AmpRun;
use std::collections::HashMap;

/// The symbol type of a function.
const FUNCTION_KIND: u8 = 2;
/// The symbol type of a data object.
pub(crate) const OBJECT_KIND: u8 = 1;
/// Alignment of the stack's base and size.
const STACK_ALIGNMENT: i128 = 16;
/// Alignment of the BSS bounds.
const BSS_ALIGNMENT: i128 = 8;
/// The controller entry points.
const FUNCTIONS: [&str; 3] = ["witness_amp_main", "witness_amp_trap", "witness_amp_exit"];
/// The symbols every image declares.
const REQUIRED: [&str; 9] = [
    "_start",
    "witness_amp_main",
    "witness_amp_trap",
    "witness_amp_exit",
    "witness_amp_platform",
    "witness_amp_run",
    "__bss_start",
    "__bss_end",
    "__stack_top",
];

/// Tell whether a segment with the given permissions holds `size` bytes at
/// `address` in its file bytes.
pub(crate) fn file_backed(segment: &LoadSegment, flags: u32, address: u64, size: u64) -> bool {
    segment.flags == flags
        && segment.address <= address
        && u128::from(address) + u128::from(size)
            <= u128::from(segment.address) + u128::from(segment.file_bytes)
}

/// The global symbols by name; `read_symbols` refuses a repeated name.
pub(crate) fn symbol_map(content: &[u8]) -> Result<HashMap<String, ElfSymbol>, String> {
    Ok(read_symbols(content)?.into_iter().collect())
}

/// The file bytes a symbol inside `owner`'s file extent names.
pub(crate) fn file_bytes<'a>(
    content: &'a [u8],
    owner: &LoadSegment,
    symbol: &ElfSymbol,
) -> &'a [u8] {
    let start = owner.offset + symbol.address - owner.address;
    &content[start as usize..(start + symbol.size) as usize]
}

/// Python's `_constant`: one read-only object, wholly in one executable
/// segment's file bytes, holding exactly `expected`.
fn constant(
    content: &[u8],
    segments: &[LoadSegment],
    symbol: &ElfSymbol,
    expected: &[u8],
) -> Result<(), String> {
    let owners: Vec<&LoadSegment> = segments
        .iter()
        .filter(|segment| file_backed(segment, READ_EXECUTE, symbol.address, symbol.size))
        .collect();
    let [owner] = owners.as_slice() else {
        return Err("compiled AMP contract is not one complete readonly original object".into());
    };
    if symbol.kind != OBJECT_KIND || symbol.size != expected.len() as u64 {
        return Err("compiled AMP contract is not one complete readonly original object".into());
    }
    if file_bytes(content, owner, symbol) != expected {
        return Err("compiled AMP contract bytes differ from admitted platform/run inputs".into());
    }
    Ok(())
}

/// The platform constant's ABI bytes, Python's `PLATFORM_BYTES.pack`.
fn platform_bytes(platform: &AmpPlatform) -> Vec<u8> {
    let word = |value: i128| u32::try_from(value).expect("an admitted hart or source");
    let double = |value: u128| u64::try_from(value).expect("an admitted RV64 address");
    let plic = platform.device.plic;
    let mut bytes = Vec::with_capacity(56);
    bytes.extend(word(platform.hart).to_le_bytes());
    bytes.extend(word(platform.source).to_le_bytes());
    for address in [
        platform.device.aperture.address,
        plic.priority,
        plic.enable_word,
        plic.threshold,
        plic.claim,
        platform.memory.shared.address,
    ] {
        bytes.extend(double(address).to_le_bytes());
    }
    bytes
}

/// The run constant's ABI bytes, Python's `RUN_BYTES.pack`.
fn run_bytes(run: &AmpRun) -> Vec<u8> {
    let mut bytes = Vec::with_capacity(60);
    for field in [
        run.cycles,
        run.period_ticks,
        u32::from(run.lqr),
        run.overload_iterations,
    ] {
        bytes.extend(field.to_le_bytes());
    }
    for coefficient in run.coefficients {
        bytes.extend(coefficient.to_le_bytes());
    }
    bytes
}

/// Python's stack check: an aligned stack of at least a page directly above
/// the aligned BSS end, BSS and stack inside one writable segment.
fn check_stack(
    symbols: &HashMap<String, ElfSymbol>,
    segments: &[LoadSegment],
    stack_bytes: i128,
) -> Result<(), String> {
    let [start, end, top] =
        ["__bss_start", "__bss_end", "__stack_top"].map(|name| i128::from(symbols[name].address));
    let base = (end + STACK_ALIGNMENT - 1) / STACK_ALIGNMENT * STACK_ALIGNMENT;
    if stack_bytes < i128::from(PAGE_BYTES)
        || stack_bytes % STACK_ALIGNMENT != 0
        || start % BSS_ALIGNMENT != 0
        || end % BSS_ALIGNMENT != 0
        || end < start
        || base.checked_add(stack_bytes) != Some(top)
        || !segments.iter().any(|segment| {
            segment.flags == READ_WRITE
                && i128::from(segment.address) <= start
                && top <= i128::from(segment.address) + i128::from(segment.memory_bytes)
        })
    {
        return Err(
            "firmware original BSS and integer stack geometry differs from the reservation".into(),
        );
    }
    Ok(())
}

/// Admit an image's compiled constants, controller entry points and stack geometry.
///
/// `stack_bytes` is the stack size the image was linked with. The native
/// stack size is an integer by type, so Python's check that it is an `int`
/// always holds here.
///
/// # Errors
///
/// Python's refusal text for the first defect of the ELF admission, the
/// symbols, the entry and resource symbols, the controller entry points, the
/// platform constant, the run constant, or the BSS and stack geometry.
///
/// # Panics
///
/// When the platform's hart or source exceeds 32 bits or one of its addresses
/// exceeds 64 bits, which a platform from `bind_platform` never does.
pub fn admit_image_contract(
    content: &[u8],
    platform: &AmpPlatform,
    run: &AmpRun,
    stack_bytes: i128,
) -> Result<Vec<LoadSegment>, String> {
    let segments = admit_elf(content, platform.memory.firmware)?;
    let symbols = symbol_map(content)?;
    if REQUIRED.iter().any(|name| !symbols.contains_key(*name))
        || u128::from(symbols["_start"].address) != platform.memory.firmware.address
    {
        return Err(
            "firmware original required entry/resource symbols are absent or misplaced".into(),
        );
    }
    for name in FUNCTIONS {
        let symbol = symbols[name];
        if symbol.kind != FUNCTION_KIND
            || symbol.size == 0
            || !segments
                .iter()
                .any(|segment| file_backed(segment, READ_EXECUTE, symbol.address, symbol.size))
        {
            return Err("firmware controller entry point lacks original executable bytes".into());
        }
    }
    let platform_constant = platform_bytes(platform);
    let run_constant = run_bytes(run);
    constant(
        content,
        &segments,
        &symbols["witness_amp_platform"],
        &platform_constant,
    )?;
    constant(
        content,
        &segments,
        &symbols["witness_amp_run"],
        &run_constant,
    )?;
    check_stack(&symbols, &segments, stack_bytes)?;
    Ok(segments)
}

#[cfg(test)]
#[path = "../tests/unit/amp_image_contract.rs"]
mod tests;
