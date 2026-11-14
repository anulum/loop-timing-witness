// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — the Witness AXI device and its PLIC interrupt source

//! Bind the declared Witness AXI device to one PLIC interrupt source as the
//! Python module `amp_device` does.

use crate::amp_collisions::check_collisions;
use crate::amp_memory::{enabled, intersects, parent_path};
use crate::device_tree::{
    DeviceTree, Node, PlicRegisters, PlicSelection, Region, bind_plic, phandle_nodes,
    property_cells, register_regions, single_cell, string_list,
};

/// The versioned compatible string of the Witness AXI device.
const COMPATIBLE: &str = "anulum,loop-timing-witness-axi-v1";
/// Bytes of the device's register aperture.
const APERTURE_BYTES: u128 = 256;

/// The admitted device aperture and its PLIC registers.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct WitnessDevice {
    /// The 256-byte AXI register aperture.
    pub aperture: Region,
    /// The dedicated hart's PLIC registers for the device's source.
    pub plic: PlicRegisters,
}

/// The controller a device's nearest `interrupt-parent` names.
fn interrupt_parent<'a>(tree: &'a DeviceTree, node: &'a Node) -> Result<&'a Node, String> {
    let handles = phandle_nodes(tree)?;
    let mut current = node;
    loop {
        if current.property("interrupt-parent").is_some() {
            let controller = handles.get(&single_cell(current, "interrupt-parent")?);
            return controller
                .copied()
                .ok_or_else(|| "interrupt-parent references an undeclared controller".into());
        }
        if current.path() == "/" {
            return Err("device lacks an original interrupt-parent".into());
        }
        current = tree
            .node(parent_path(current.path()))
            .expect("a decoded parent");
    }
}

/// The device's interrupt controller and source, from either declaration form.
fn interrupt<'a>(tree: &'a DeviceTree, node: &'a Node) -> Result<(Option<&'a Node>, i128), String> {
    let Some(extended) = node.property("interrupts-extended") else {
        let parent = interrupt_parent(tree, node)?;
        return Ok((Some(parent), i128::from(single_cell(node, "interrupts")?)));
    };
    if node.property("interrupts").is_some() || node.property("interrupt-parent").is_some() {
        return Err("Witness interrupt declaration is ambiguous".into());
    }
    let [handle, source] = property_cells(extended)?[..] else {
        return Err("Witness requires exactly one original PLIC interrupt".into());
    };
    Ok((
        phandle_nodes(tree)?.get(&handle).copied(),
        i128::from(source),
    ))
}

/// Admit the enabled versioned device, its one PLIC source and its aperture.
pub(crate) fn bind_device(
    tree: &DeviceTree,
    path: &str,
    selection: &PlicSelection,
) -> Result<WitnessDevice, String> {
    let declared = match tree.node(path) {
        Some(node) if enabled(node.property("status")) => Some(node),
        _ => None,
    };
    let Some(node) = declared else {
        return Err("Witness requires an enabled original versioned AXI device node".into());
    };
    if !string_list(node, "compatible")?
        .iter()
        .any(|name| name == COMPATIBLE)
    {
        return Err("Witness requires an enabled original versioned AXI device node".into());
    }
    let (parent, source) = interrupt(tree, node)?;
    if parent.is_none_or(|parent| parent.path() != selection.path) || source != selection.source {
        return Err("Witness interrupt does not match the selected PLIC and source".into());
    }
    let plic = bind_plic(tree, selection)?;
    let aperture = match register_regions(tree, path)?.as_slice() {
        [region]
            if region.address != 0
                && region.address % APERTURE_BYTES == 0
                && region.size == APERTURE_BYTES =>
        {
            *region
        }
        _ => return Err("Witness requires one aligned complete 256-byte AXI aperture".into()),
    };
    // `bind_plic` admitted exactly one PLIC register region.
    let controller = register_regions(tree, &selection.path)?[0];
    if intersects(aperture, controller) {
        return Err("Witness AXI aperture overlaps the PLIC".into());
    }
    check_collisions(tree, path, aperture, &selection.path, selection.source)?;
    Ok(WitnessDevice { aperture, plic })
}
