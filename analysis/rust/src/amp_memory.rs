// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — reserved firmware and telemetry memory of an AMP platform

//! Admit the firmware and telemetry reservations of an AMP platform as the
//! Python module `amp_memory` does.

use crate::device_tree::{DeviceTree, Region, register_regions, single_cell};

/// Page size every reservation is aligned to.
const PAGE_BYTES: u128 = 4096;
/// Alignment of the requested firmware stack.
const STACK_ALIGNMENT: i128 = 16;
/// The parent of every reservation.
const RESERVED_ROOT: &str = "/reserved-memory";

/// The memory nodes and sizes an image requests.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MemorySelection {
    /// Backing RAM node path.
    pub ram_path: String,
    /// Firmware reservation node path.
    pub firmware_path: String,
    /// Telemetry reservation node path.
    pub shared_path: String,
    /// Bytes of the telemetry mailbox.
    pub mailbox_bytes: i128,
    /// Bytes of the firmware stack.
    pub stack_bytes: i128,
}

/// The admitted firmware and telemetry extents.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ReservedMemory {
    /// Firmware reservation.
    pub firmware: Region,
    /// Telemetry reservation.
    pub shared: Region,
}

/// Tell whether two extents share a byte, as Python's half-open comparisons do.
pub(crate) fn intersects(first: Region, second: Region) -> bool {
    first.address < second.address + second.size && second.address < first.address + first.size
}

/// The path of a node's parent, as Python's `path.rpartition("/")[0] or "/"`.
pub(crate) fn parent_path(path: &str) -> &str {
    path.rsplit_once('/')
        .map(|(parent, _)| parent)
        .filter(|parent| !parent.is_empty())
        .unwrap_or("/")
}

/// Tell whether a node is enabled, as a missing `status` is.
pub(crate) fn enabled(status: Option<&[u8]>) -> bool {
    matches!(status, None | Some(b"okay\0" | b"ok\0"))
}

/// Require the reserved-memory parent's empty `ranges` and the root's cell geometry.
fn check_parent(tree: &DeviceTree) -> Result<(), String> {
    let Some(parent) = tree
        .node(RESERVED_ROOT)
        .filter(|node| node.property("ranges") == Some(b""))
    else {
        return Err("reserved-memory parent requires an explicit empty ranges property".into());
    };
    let root = tree.node("/").expect("a decoded root");
    for (name, default) in [("#address-cells", 2), ("#size-cells", 1)] {
        let expected = if root.property(name).is_some() {
            single_cell(root, name)?
        } else {
            default
        };
        if single_cell(parent, name)? != expected {
            return Err("reserved-memory cell geometry differs from the original root".into());
        }
    }
    Ok(())
}

/// Admit one direct, enabled, unmapped, non-reusable, page-aligned reservation.
fn reservation(tree: &DeviceTree, path: &str) -> Result<Region, String> {
    let Some(node) = tree
        .node(path)
        .filter(|_| path.rsplit_once('/').map(|(parent, _)| parent) == Some(RESERVED_ROOT))
    else {
        return Err("AMP reservation must be an original direct reserved-memory child".into());
    };
    if node.property("no-map") != Some(b"")
        || node.property("reusable").is_some()
        || !enabled(node.property("status"))
    {
        return Err("AMP reservation must be enabled, unmapped and non-reusable".into());
    }
    match register_regions(tree, path)?.as_slice() {
        [region]
            if region.address != 0
                && region.size != 0
                && region.address % PAGE_BYTES == 0
                && region.size % PAGE_BYTES == 0 =>
        {
            Ok(*region)
        }
        _ => Err("AMP reservation must declare one nonzero page-aligned extent".into()),
    }
}

/// Refuse another reservation or an unmatched header reservation meeting the owners.
fn check_collisions(
    tree: &DeviceTree,
    memory: ReservedMemory,
    paths: [&str; 2],
) -> Result<(), String> {
    let owners = [memory.firmware, memory.shared];
    for node in tree.nodes() {
        if paths.contains(&node.path()) || parent_path(node.path()) != RESERVED_ROOT {
            continue;
        }
        for other in register_regions(tree, node.path())? {
            if owners.iter().any(|owner| intersects(*owner, other)) {
                return Err("AMP memory intersects another reserved-memory node".into());
            }
        }
    }
    for &(address, size) in tree.reservations() {
        let other = Region {
            address: u128::from(address),
            size: u128::from(size),
        };
        if !owners.contains(&other) && owners.iter().any(|owner| intersects(*owner, other)) {
            return Err("AMP memory intersects an unmatched original header reservation".into());
        }
    }
    Ok(())
}

/// Refuse another memory node whose banks meet a reservation.
fn reject_other_ram_alias(
    tree: &DeviceTree,
    memory: ReservedMemory,
    selected: &str,
) -> Result<(), String> {
    for node in tree.nodes() {
        if node.path() == selected || node.property("device_type") != Some(b"memory\0") {
            continue;
        }
        for other in register_regions(tree, node.path())? {
            if [memory.firmware, memory.shared]
                .iter()
                .any(|owner| intersects(*owner, other))
            {
                return Err(format!(
                    "AMP reservation has ambiguous original RAM ownership: {}",
                    node.path()
                ));
            }
        }
    }
    Ok(())
}

/// Admit the selected firmware and telemetry reservations inside one RAM bank each.
///
/// The native selection holds integers by type, so Python's check that the
/// two sizes are `int` always holds here.
pub(crate) fn bind_memory(
    tree: &DeviceTree,
    selection: &MemorySelection,
) -> Result<ReservedMemory, String> {
    if selection.firmware_path == selection.shared_path
        || selection.mailbox_bytes <= 0
        || selection.stack_bytes < signed(PAGE_BYTES)
        || selection.stack_bytes % STACK_ALIGNMENT != 0
    {
        return Err("AMP memory selection or requested ABI/stack bounds are invalid".into());
    }
    check_parent(tree)?;
    let memory = ReservedMemory {
        firmware: reservation(tree, &selection.firmware_path)?,
        shared: reservation(tree, &selection.shared_path)?,
    };
    if intersects(memory.firmware, memory.shared) {
        return Err("entire firmware and telemetry reservations overlap".into());
    }
    if selection.mailbox_bytes > signed(memory.shared.size)
        || selection.stack_bytes > signed(memory.firmware.size)
    {
        return Err("requested telemetry ABI or stack exceeds its original reservation".into());
    }
    let Some(_) = tree.node(&selection.ram_path).filter(|ram| {
        ram.property("device_type") == Some(b"memory\0") && enabled(ram.property("status"))
    }) else {
        return Err("AMP backing RAM must be an enabled original memory node".into());
    };
    let banks = register_regions(tree, &selection.ram_path)?;
    for owner in [memory.firmware, memory.shared] {
        let covering = banks
            .iter()
            .filter(|bank| {
                bank.address <= owner.address
                    && owner.address + owner.size <= bank.address + bank.size
            })
            .count();
        if covering != 1 {
            return Err("AMP reservation lacks one complete unambiguous original RAM bank".into());
        }
    }
    reject_other_ram_alias(tree, memory, &selection.ram_path)?;
    check_collisions(
        tree,
        memory,
        [&selection.firmware_path, &selection.shared_path],
    )?;
    Ok(memory)
}

/// An extent size as a signed integer; sizes stay within the 65-bit range.
fn signed(size: u128) -> i128 {
    i128::try_from(size).expect("a device-tree size within 2^65")
}
