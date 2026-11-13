// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — device-tree register extents translated to root addresses

//! Decode a node's `reg` cells and translate them through every ancestor
//! `ranges` mapping to root physical addresses, as Python's
//! `device_tree_resources` does, with the same refusals in the same order.

use crate::device_tree_blob::{ADDRESS_LIMIT, DeviceTree};
use crate::device_tree_structure::Node;

/// Bytes in one cell.
const CELL_BYTES: usize = 4;
/// Most cells an address or size may span.
const MAX_ADDRESS_CELLS: u32 = 2;

/// One physical or intermediate bus extent, with an exclusive upper bound.
///
/// Values are wider than 64 bits because, as in Python, a translated
/// zero-size extent may start exactly at the end of the RV64 address space.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Region {
    /// Unsigned start address.
    pub address: u128,
    /// Declared extent in bytes; CPU identifier registers can have zero size.
    pub size: u128,
}

/// Decode complete big-endian cells without inventing missing words.
///
/// # Errors
///
/// Returns Python's refusal text when the bytes are not a whole number of cells.
pub fn property_cells(content: &[u8]) -> Result<Vec<u32>, String> {
    if !content.len().is_multiple_of(CELL_BYTES) {
        return Err("device-tree property is not a whole number of cells".to_owned());
    }
    Ok(content
        .as_chunks::<CELL_BYTES>()
        .0
        .iter()
        .map(|&cell| u32::from_be_bytes(cell))
        .collect())
}

/// The path of a node's parent; the root's children have the root as parent.
pub(crate) fn parent_path(path: &str) -> &str {
    match path.rfind('/') {
        Some(0) | None => "/",
        Some(end) => &path[..end],
    }
}

/// Read an explicit cell count, or the standard default when it is absent.
fn count(node: &Node, name: &str, default: u32) -> Result<u32, String> {
    let value = match node.property(name) {
        Some(raw) => property_cells(raw)?,
        None => vec![default],
    };
    match value.as_slice() {
        [cells] if *cells <= MAX_ADDRESS_CELLS => Ok(*cells),
        _ => Err("device-tree bus cell count is unsupported or malformed".to_owned()),
    }
}

/// Join consecutive address or size cells into one unsigned value.
fn number(cells: &[u32]) -> u128 {
    cells
        .iter()
        .fold(0, |value, &cell| (value << 32) + u128::from(cell))
}

/// Translate one extent through every ancestor mapping to the root.
fn translate(tree: &DeviceTree, bus_path: &str, mut region: Region) -> Result<Region, String> {
    let mut bus_path = bus_path;
    while bus_path != "/" {
        let bus = tree.existing(bus_path);
        let parent = parent_path(bus_path);
        let Some(raw) = bus.property("ranges") else {
            return Err("device-tree bus lacks an address translation".to_owned());
        };
        let ranges = property_cells(raw)?;
        let child_cells = count(bus, "#address-cells", 2)?;
        let parent_cells = count(tree.existing(parent), "#address-cells", 2)?;
        let size_cells = count(bus, "#size-cells", 1)?;
        let width = (child_cells + parent_cells + size_cells) as usize;
        // Python also refuses zero child cells here. The first bus is the
        // register's parent, whose zero address cells `register_regions`
        // refused already, and every later bus is the previous parent, whose
        // zero cells this test refused, so that case never arrives.
        if parent_cells == 0 || size_cells == 0 || !ranges.len().is_multiple_of(width) {
            return Err("device-tree bus ranges have invalid cell geometry".to_owned());
        }
        if !ranges.is_empty() {
            let (child_end, host_end) =
                (child_cells as usize, (child_cells + parent_cells) as usize);
            let mut candidates = ranges.chunks_exact(width).filter_map(|entry| {
                let child = number(&entry[..child_end]);
                let host = number(&entry[child_end..host_end]);
                let size = number(&entry[host_end..]);
                (child <= region.address && region.address + region.size <= child + size)
                    .then(|| host + region.address - child)
            });
            let (Some(address), None) = (candidates.next(), candidates.next()) else {
                return Err(
                    "device-tree register extent lacks a unique complete bus mapping".to_owned(),
                );
            };
            region.address = address;
        }
        if region.address + region.size > 1 << (32 * parent_cells) {
            return Err(
                "translated device-tree register exceeds the parent address space".to_owned(),
            );
        }
        bus_path = parent;
    }
    Ok(region)
}

/// Decode a node's complete `reg` property and translate it to root addresses.
///
/// # Errors
///
/// Returns Python's refusal text when the node, property, cell geometry,
/// bounds or an ancestor translation is invalid.
pub fn register_regions(tree: &DeviceTree, path: &str) -> Result<Vec<Region>, String> {
    let Some(raw) = tree
        .node(path)
        .filter(|_| path != "/")
        .and_then(|node| node.property("reg"))
    else {
        return Err("device-tree register node or property is absent".to_owned());
    };
    let parent_path = parent_path(path);
    let parent = tree.existing(parent_path);
    let address_cells = count(parent, "#address-cells", 2)?;
    let size_cells = count(parent, "#size-cells", 1)?;
    let values = property_cells(raw)?;
    let width = (address_cells + size_cells) as usize;
    if address_cells == 0 || values.is_empty() || !values.len().is_multiple_of(width) {
        return Err("device-tree register property has invalid cell geometry".to_owned());
    }
    let space = ADDRESS_LIMIT.min(1 << (32 * address_cells));
    values
        .chunks_exact(width)
        .map(|entry| {
            let (address, size) = entry.split_at(address_cells as usize);
            let region = Region {
                address: number(address),
                size: number(size),
            };
            if region.address + region.size > space {
                return Err(
                    "device-tree register extent exceeds RV64 or declared bus address space"
                        .to_owned(),
                );
            }
            translate(tree, parent_path, region)
        })
        .collect()
}
