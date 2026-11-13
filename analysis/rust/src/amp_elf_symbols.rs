// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — firmware ELF sections and defined global symbols

//! Read the one symbol table of a firmware ELF image and its defined global
//! and weak symbols, as Python's `amp_elf_symbols` does, with the same
//! refusals in the same order.

use crate::amp_elf::{HEADER_BYTES, MAX_IMAGE_BYTES, double, half, word};
use std::collections::HashSet;

/// Bytes in one section header.
const SECTION_BYTES: usize = 64;
/// Bytes in one symbol record.
const SYMBOL_BYTES: u64 = 24;
/// Section types.
const SYMBOL_TABLE: u32 = 2;
const STRING_TABLE: u32 = 3;
const NO_BITS: u32 = 8;
/// Most sections an image may hold.
const MAX_SECTIONS: u16 = 16384;
/// Symbol bindings that the reader keeps.
const GLOBAL_BINDING: u8 = 1;
const WEAK_BINDING: u8 = 2;
/// The section index of an absolute symbol.
const ABSOLUTE_SECTION: u16 = 0xFFF1;

/// One defined global or weak symbol and its section.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ElfSymbol {
    /// Symbol value.
    pub address: u64,
    /// Symbol byte extent.
    pub size: u64,
    /// ELF symbol type.
    pub kind: u8,
    /// Defining section index, or the absolute marker.
    pub section: u16,
}

/// One section header's type, file offset, size, link and entry size.
#[derive(Clone, Copy)]
struct Section {
    kind: u32,
    offset: u64,
    size: u64,
    link: u32,
    entry_bytes: u64,
}

/// Read the section table and require every section with file bytes to lie inside the image.
fn sections(content: &[u8]) -> Result<Vec<Section>, String> {
    if content.len() < HEADER_BYTES || content.len() > MAX_IMAGE_BYTES {
        return Err("firmware symbol image size is outside bounds".to_owned());
    }
    let (table, entry_bytes, count) = (double(content, 40), half(content, 58), half(content, 60));
    if usize::from(entry_bytes) != SECTION_BYTES
        || !(1..=MAX_SECTIONS).contains(&count)
        || table < HEADER_BYTES as u64
        || u128::from(table) + u128::from(count) * u128::from(entry_bytes) > content.len() as u128
    {
        return Err("firmware original section table geometry is invalid".to_owned());
    }
    let found: Vec<Section> = (0..usize::from(count))
        .map(|index| {
            let start = table as usize + index * SECTION_BYTES;
            Section {
                kind: word(content, start + 4),
                offset: double(content, start + 24),
                size: double(content, start + 32),
                link: word(content, start + 40),
                entry_bytes: double(content, start + 56),
            }
        })
        .collect();
    if found.iter().any(|section| {
        section.kind != NO_BITS
            && u128::from(section.offset) + u128::from(section.size) > content.len() as u128
    }) {
        return Err("firmware original section file extent is truncated".to_owned());
    }
    Ok(found)
}

/// Find the one symbol table and its linked string table, with a whole number of 24-byte records.
fn symbol_table(sections: &[Section]) -> Result<(Section, Section), String> {
    let tables: Vec<&Section> = sections
        .iter()
        .filter(|section| section.kind == SYMBOL_TABLE)
        .collect();
    let [table] = tables.as_slice() else {
        return Err("firmware requires one original symbol table".to_owned());
    };
    let strings = usize::try_from(table.link)
        .ok()
        .and_then(|link| sections.get(link))
        .filter(|strings| strings.kind == STRING_TABLE);
    let Some(strings) = strings.filter(|_| {
        table.entry_bytes == SYMBOL_BYTES
            && table.size != 0
            && table.size.is_multiple_of(SYMBOL_BYTES)
    }) else {
        return Err("firmware original symbol table geometry or string link is invalid".to_owned());
    };
    Ok((**table, *strings))
}

/// Read one symbol record: skip local symbols and check a global's name and section.
fn symbol(
    content: &[u8],
    start: usize,
    names: &[u8],
    sections: usize,
) -> Result<Option<(String, ElfSymbol)>, String> {
    let (name, info, section) = (
        word(content, start) as usize,
        content[start + 4],
        half(content, start + 6),
    );
    if !matches!(info >> 4, GLOBAL_BINDING | WEAK_BINDING) {
        return Ok(None);
    }
    let Some(length) = names
        .get(name..)
        .and_then(|rest| rest.iter().position(|&byte| byte == 0))
    else {
        return Err("firmware symbol name is outside the original string table".to_owned());
    };
    let text = &names[name..name + length];
    if !text.is_ascii() {
        return Err("firmware original symbol name is not ASCII".to_owned());
    }
    if text.is_empty()
        || section == 0
        || (section != ABSOLUTE_SECTION && usize::from(section) >= sections)
    {
        return Err("firmware symbol is empty, undefined or has an invalid section".to_owned());
    }
    let symbol = ElfSymbol {
        address: double(content, start + 8),
        size: double(content, start + 16),
        kind: info & 15,
        section,
    };
    Ok(Some((
        text.iter().map(|&byte| char::from(byte)).collect(),
        symbol,
    )))
}

/// Read the one symbol table's defined global and weak symbols, in table order.
///
/// # Errors
///
/// Returns Python's refusal text when the section table, the symbol table, its
/// string link, a name, a definition or a global identity is invalid.
pub fn read_symbols(content: &[u8]) -> Result<Vec<(String, ElfSymbol)>, String> {
    let sections = sections(content)?;
    let (table, strings) = symbol_table(&sections)?;
    let names = &content[strings.offset as usize..(strings.offset + strings.size) as usize];
    let mut result: Vec<(String, ElfSymbol)> = Vec::new();
    let mut seen: HashSet<String> = HashSet::new();
    for start in (table.offset..table.offset + table.size).step_by(SYMBOL_BYTES as usize) {
        let Some((name, found)) = symbol(content, start as usize, names, sections.len())? else {
            continue;
        };
        if !seen.insert(name.clone()) {
            return Err("firmware global symbol name is ambiguous".to_owned());
        }
        result.push((name, found));
    }
    Ok(result)
}
