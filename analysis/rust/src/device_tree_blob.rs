// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — device-tree blob headers, blocks and reservations

//! Validate a device-tree blob's header, block extents and memory
//! reservations, then decode its structure block, as Python's
//! `device_tree_blob` does, with the same refusals in the same order.

use crate::device_tree_structure::{Node, decode_structure};
use std::collections::HashMap;
use std::ops::Range;

/// The blob magic number.
const MAGIC: u64 = 0xD00D_FEED;
/// Bytes in the header.
const HEADER_SIZE: u64 = 40;
/// Bytes in one structure-block word.
const WORD_BYTES: u64 = 4;
/// Bytes in one reservation entry.
const RESERVATION_SIZE: usize = 16;
/// Alignment of the reservation map.
const RESERVATION_ALIGNMENT: u64 = 8;
/// The blob version the decoder reads.
const VERSION: u64 = 17;
/// Largest blob the decoder admits.
const MAX_BLOB_BYTES: usize = 16 * 1024 * 1024;
/// The exclusive end of the RV64 physical address space.
pub(crate) const ADDRESS_LIMIT: u128 = 1 << 64;

/// A decoded tree with its header reservations, without ownership claims.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DeviceTree {
    nodes: Vec<Node>,
    index: HashMap<String, usize>,
    reservations: Vec<(u64, u64)>,
    boot_cpu: u32,
}

impl DeviceTree {
    /// Every node in document order.
    #[must_use]
    pub fn nodes(&self) -> &[Node] {
        &self.nodes
    }

    /// The node at an absolute path, when the tree holds it.
    #[must_use]
    pub fn node(&self, path: &str) -> Option<&Node> {
        self.index.get(path).map(|&position| &self.nodes[position])
    }

    /// Nonoverlapping physical address and size pairs of the reservation map, in map order.
    #[must_use]
    pub fn reservations(&self) -> &[(u64, u64)] {
        &self.reservations
    }

    /// The physical CPU identifier the header declares.
    #[must_use]
    pub fn boot_cpu(&self) -> u32 {
        self.boot_cpu
    }

    /// The node at a path the decoder built, such as an ancestor of a decoded node.
    pub(crate) fn existing(&self, path: &str) -> &Node {
        self.node(path)
            .expect("every ancestor of a decoded node is decoded")
    }
}

/// Read one big-endian word of the header.
fn header_word(content: &[u8], index: usize) -> u32 {
    let mut bytes = [0; 4];
    bytes.copy_from_slice(&content[index * 4..index * 4 + 4]);
    u32::from_be_bytes(bytes)
}

/// Read one big-endian 64-bit reservation field that the caller has bounded.
fn reservation_field(data: &[u8], offset: usize) -> u64 {
    let mut bytes = [0; 8];
    bytes.copy_from_slice(&data[offset..offset + 8]);
    u64::from_be_bytes(bytes)
}

/// Read the bounded reservation map and refuse overlapping physical extents.
fn reservations(data: &[u8], mut offset: usize, limit: usize) -> Result<Vec<(u64, u64)>, String> {
    let mut entries: Vec<(u64, u64)> = Vec::new();
    while offset + RESERVATION_SIZE <= limit {
        let address = reservation_field(data, offset);
        let size = reservation_field(data, offset + 8);
        offset += RESERVATION_SIZE;
        if address == 0 && size == 0 {
            let mut ordered = entries.clone();
            ordered.sort_unstable();
            if ordered
                .windows(2)
                .any(|pair| u128::from(pair[0].0) + u128::from(pair[0].1) > u128::from(pair[1].0))
            {
                return Err("overlapping device-tree memory reservations".to_owned());
            }
            return Ok(entries);
        }
        if size == 0 || u128::from(address) + u128::from(size) > ADDRESS_LIMIT {
            return Err("device-tree memory reservation outside RV64 address space".to_owned());
        }
        entries.push((address, size));
    }
    Err("device-tree memory reservation map lacks its terminator".to_owned())
}

/// A blob's validated layout: where the reservation map starts and must end, and its two blocks.
struct Layout {
    reserved: usize,
    limit: usize,
    structure: Range<usize>,
    strings: Range<usize>,
}

/// Check the header's size, magic and versions, and the blocks' alignment, bounds and separation.
fn layout(content: &[u8]) -> Result<Layout, String> {
    if content.len() < HEADER_SIZE as usize || content.len() > MAX_BLOB_BYTES {
        return Err("device-tree blob size outside admitted bounds".to_owned());
    }
    let word = |index| u64::from(header_word(content, index));
    let (magic, total, version, compatible) = (word(0), word(1), word(5), word(6));
    // Python also refuses a compatible version above the version itself. With
    // the version at least 17 and the compatible version at most 17 already
    // required, that can never hold, so it is not tested again here.
    if magic != MAGIC || total != content.len() as u64 || version < VERSION || compatible > VERSION
    {
        return Err("invalid device-tree magic, total size or compatible version".to_owned());
    }
    let (structure, strings, reserved) = (word(2), word(3), word(4));
    let blocks = [
        (structure, structure + word(9)),
        (strings, strings + word(8)),
    ];
    if !structure.is_multiple_of(WORD_BYTES)
        || !word(9).is_multiple_of(WORD_BYTES)
        || word(9) == 0
        || !reserved.is_multiple_of(RESERVATION_ALIGNMENT)
        || reserved < HEADER_SIZE
        || reserved >= total
        || blocks
            .iter()
            .any(|&(start, end)| start < HEADER_SIZE || end > total)
        || (blocks[0].0 < blocks[1].1 && blocks[1].0 < blocks[0].1)
        || blocks
            .iter()
            .any(|&(start, end)| start <= reserved && reserved < end)
    {
        return Err("invalid device-tree block alignment, bounds or overlap".to_owned());
    }
    let limit = blocks
        .iter()
        .map(|&(start, _)| start)
        .filter(|&start| start > reserved)
        .fold(total, u64::min);
    let range = |(start, end): (u64, u64)| start as usize..end as usize;
    Ok(Layout {
        reserved: reserved as usize,
        limit: limit as usize,
        structure: range(blocks[0]),
        strings: range(blocks[1]),
    })
}

/// Validate a blob's header, block extents, reservations and structure, and decode its tree.
///
/// # Errors
///
/// Returns Python's refusal text when the size, magic, version, alignment,
/// block separation, reservations or structure are invalid.
pub fn decode_device_tree(content: &[u8]) -> Result<DeviceTree, String> {
    let layout = layout(content)?;
    let reservations = reservations(content, layout.reserved, layout.limit)?;
    let nodes = decode_structure(&content[layout.structure], &content[layout.strings])?;
    Ok(DeviceTree {
        nodes: nodes.list,
        index: nodes.index,
        reservations,
        boot_cpu: header_word(content, 7),
    })
}
