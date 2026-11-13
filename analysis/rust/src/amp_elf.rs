// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — firmware ELF admission inside the reserved RAM

//! Admit an AMP firmware ELF image and read its global symbols.
//!
//! These readers port the Python analysis modules `amp_elf` and
//! `amp_elf_symbols`. Every value, every refusal text and the order in which
//! refusals are reached is Python's. The crate tests hold them to the corpus
//! that `tests/test_amp_elf_corpus.py` builds from two real images and
//! Python's own readers.
//!
//! - [`admit_elf`] admits the load segments of a static little-endian
//!   soft-float RV64 executable inside the firmware reservation.
//! - [`read_symbols`] reads the defined global and weak symbols of the one
//!   symbol table, in table order.
//!
//! Sums of header fields are taken in 128 bits, as Python's integers never
//! overflow.
//!
//! [`admit_elf`]: crate::amp_elf::admit_elf
//! [`read_symbols`]: crate::amp_elf::read_symbols

pub use crate::amp_elf_symbols::{ElfSymbol, read_symbols};
use crate::device_tree_resources::Region;

/// Bytes in the ELF header.
pub(crate) const HEADER_BYTES: usize = 64;
/// Bytes in one program header.
const PROGRAM_BYTES: usize = 56;
/// Largest image the readers admit.
pub(crate) const MAX_IMAGE_BYTES: usize = 16 * 1024 * 1024;
/// Most program headers an image may hold.
const MAX_PROGRAM_HEADERS: u16 = 128;
/// The RISC-V machine number.
const RV64_MACHINE: u16 = 243;
/// An executable file.
const EXECUTABLE_TYPE: u16 = 2;
/// A loadable segment.
const LOAD_TYPE: u32 = 1;
/// A dynamic section or an interpreter request.
const DYNAMIC_TYPE: u32 = 2;
const INTERPRETER_TYPE: u32 = 3;
/// Read and execute permissions.
const READ_EXECUTE: u32 = 5;
/// Read and write permissions.
const READ_WRITE: u32 = 6;
/// The compressed-instruction flag, the only header flag admitted.
const RVC_FLAG: u32 = 1;
/// Smallest load alignment.
const PAGE_BYTES: u64 = 4096;
/// The exclusive end of the RV64 address space.
const ADDRESS_LIMIT: u128 = 1 << 64;
/// The identity bytes of a 64-bit little-endian current-version ELF file.
const IDENTITY: &[u8; 7] = b"\x7fELF\x02\x01\x01";

/// One complete loadable file extent and its identical physical memory extent.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct LoadSegment {
    /// File byte offset.
    pub offset: u64,
    /// Identical virtual and physical load address.
    pub address: u64,
    /// Initialised bytes to load.
    pub file_bytes: u64,
    /// Whole initialised and zero-filled extent.
    pub memory_bytes: u64,
    /// Exact read-execute or read-write permission bits.
    pub flags: u32,
}

/// Read a little-endian field that the caller has bounded.
pub(crate) fn field<const N: usize>(content: &[u8], offset: usize) -> [u8; N] {
    let mut bytes = [0; N];
    bytes.copy_from_slice(&content[offset..offset + N]);
    bytes
}

/// Read a little-endian 16-bit field.
pub(crate) fn half(content: &[u8], offset: usize) -> u16 {
    u16::from_le_bytes(field(content, offset))
}

/// Read a little-endian 32-bit field.
pub(crate) fn word(content: &[u8], offset: usize) -> u32 {
    u32::from_le_bytes(field(content, offset))
}

/// Read a little-endian 64-bit field.
pub(crate) fn double(content: &[u8], offset: usize) -> u64 {
    u64::from_le_bytes(field(content, offset))
}

/// Check the executable identity and return the program table's offset and entry count.
fn geometry(content: &[u8], reservation: Region) -> Result<(u64, u16), String> {
    if content.len() < HEADER_BYTES || content.len() > MAX_IMAGE_BYTES {
        return Err("firmware ELF image size is outside bounds".to_owned());
    }
    if content[..7] != IDENTITY[..]
        || content[7] != 0
        || half(content, 16) != EXECUTABLE_TYPE
        || half(content, 18) != RV64_MACHINE
        || word(content, 20) != 1
        || word(content, 48) & !RVC_FLAG != 0
    {
        return Err(
            "firmware requires a static little-endian soft-float RV64 executable".to_owned(),
        );
    }
    let (entry, table, count) = (double(content, 24), double(content, 32), half(content, 56));
    let entry_bytes = half(content, 54);
    if usize::from(half(content, 52)) != HEADER_BYTES
        || usize::from(entry_bytes) != PROGRAM_BYTES
        || !(1..=MAX_PROGRAM_HEADERS).contains(&count)
        || table < HEADER_BYTES as u64
        || u128::from(table) + u128::from(count) * u128::from(entry_bytes) > content.len() as u128
        || u128::from(entry) != reservation.address
    {
        return Err(
            "firmware ELF header geometry or entry differs from the reservation".to_owned(),
        );
    }
    Ok((table, count))
}

/// Tell whether a load segment's memory or initialised file extent meets an earlier one's.
fn overlaps(segment: &LoadSegment, prior: &LoadSegment) -> bool {
    let end = |start: u64, bytes: u64| u128::from(start) + u128::from(bytes);
    (u128::from(segment.address) < end(prior.address, prior.memory_bytes)
        && u128::from(prior.address) < end(segment.address, segment.memory_bytes))
        || (segment.file_bytes != 0
            && prior.file_bytes != 0
            && u128::from(segment.offset) < end(prior.offset, prior.file_bytes)
            && u128::from(prior.offset) < end(segment.offset, segment.file_bytes))
}

/// Read one program header: refuse loader requests and truncated extents, skip other kinds,
/// and check a load segment's permissions, geometry and place in reserved RAM.
fn load_segment(
    content: &[u8],
    start: usize,
    reservation: Region,
) -> Result<Option<LoadSegment>, String> {
    let kind = word(content, start);
    let (offset, file_bytes) = (double(content, start + 8), double(content, start + 32));
    if matches!(kind, DYNAMIC_TYPE | INTERPRETER_TYPE) {
        return Err("firmware ELF cannot require a dynamic loader or interpreter".to_owned());
    }
    if u128::from(offset) + u128::from(file_bytes) > content.len() as u128 {
        return Err("firmware ELF program file extent is truncated".to_owned());
    }
    if kind != LOAD_TYPE {
        return Ok(None);
    }
    let permissions = word(content, start + 4);
    let (virtual_address, physical) = (double(content, start + 16), double(content, start + 24));
    let (memory_bytes, alignment) = (double(content, start + 40), double(content, start + 48));
    let memory_end = u128::from(physical) + u128::from(memory_bytes);
    if !matches!(permissions, READ_EXECUTE | READ_WRITE)
        || memory_bytes == 0
        || file_bytes > memory_bytes
        || virtual_address != physical
        || alignment < PAGE_BYTES
        || !alignment.is_power_of_two()
        || offset % alignment != physical % alignment
        || memory_end > ADDRESS_LIMIT
        || u128::from(physical) < reservation.address
        || memory_end > reservation.address + reservation.size
    {
        return Err(
            "firmware ELF load segment violates permissions, geometry or reserved RAM".to_owned(),
        );
    }
    Ok(Some(LoadSegment {
        offset,
        address: physical,
        file_bytes,
        memory_bytes,
        flags: permissions,
    }))
}

/// Admit the load segments of a static little-endian soft-float RV64 executable inside reserved RAM.
///
/// # Errors
///
/// Returns Python's refusal text when the identity, header geometry, entry,
/// loader requests, permissions, extents or overlaps are invalid, or when no
/// read-execute segment's file bytes hold the entry.
pub fn admit_elf(content: &[u8], reservation: Region) -> Result<Vec<LoadSegment>, String> {
    let (table, count) = geometry(content, reservation)?;
    let mut segments: Vec<LoadSegment> = Vec::new();
    for index in 0..usize::from(count) {
        let start = table as usize + index * PROGRAM_BYTES;
        let Some(segment) = load_segment(content, start, reservation)? else {
            continue;
        };
        if segments.iter().any(|prior| overlaps(&segment, prior)) {
            return Err("firmware ELF load segments overlap in memory or file".to_owned());
        }
        segments.push(segment);
    }
    let entry = reservation.address;
    if !segments.iter().any(|segment| {
        segment.flags == READ_EXECUTE
            && u128::from(segment.address) <= entry
            && entry < u128::from(segment.address) + u128::from(segment.file_bytes)
    }) {
        return Err("firmware ELF entry lacks original executable file bytes".to_owned());
    }
    Ok(segments)
}

#[cfg(test)]
#[path = "../tests/unit/amp_elf.rs"]
mod tests;
