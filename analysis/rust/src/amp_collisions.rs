// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — register aliases and shared interrupt sources of the Witness device

//! Refuse physical register aliases and other consumers of the Witness PLIC
//! source as the Python module `amp_collisions` does.

use crate::amp_memory::{intersects, parent_path};
use crate::device_tree::{
    DeviceTree, Node, Region, phandle_nodes, property_cells, register_regions, single_cell,
};

/// Widest interrupt specifier a direct controller may declare.
const MAX_INTERRUPT_CELLS: u32 = 4;

/// One interrupt a node consumes: its controller's path and specifier cells.
type Source = (String, Vec<u32>);

/// The controller a node's nearest `interrupt-parent` names.
fn controller<'a>(tree: &'a DeviceTree, node: &'a Node) -> Result<&'a Node, String> {
    let handles = phandle_nodes(tree)?;
    let mut current = node;
    while current.property("interrupt-parent").is_none() {
        if current.path() == "/" {
            return Err("interrupt consumer lacks an original parent".into());
        }
        current = tree
            .node(parent_path(current.path()))
            .expect("a decoded parent");
    }
    handles
        .get(&single_cell(current, "interrupt-parent")?)
        .copied()
        .ok_or_else(|| "interrupt consumer references an undeclared parent".to_owned())
}

/// A direct controller's bounded specifier width.
fn width(controller: &Node) -> Result<usize, String> {
    let width = single_cell(controller, "#interrupt-cells")?;
    if controller.property("interrupt-controller") != Some(b"")
        || !(1..=MAX_INTERRUPT_CELLS).contains(&width)
    {
        return Err("interrupt consumer requires a bounded direct controller".into());
    }
    Ok(usize::try_from(width).expect("a bounded width"))
}

/// The interrupts one node consumes, from either declaration form.
fn sources(tree: &DeviceTree, node: &Node) -> Result<Vec<Source>, String> {
    let mut result = Vec::new();
    if let Some(extended) = node.property("interrupts-extended") {
        if node.property("interrupts").is_some() {
            return Err("interrupt consumer has ambiguous original forms".into());
        }
        let cells = property_cells(extended)?;
        let handles = phandle_nodes(tree)?;
        let mut offset = 0;
        while offset < cells.len() {
            let Some(controller) = handles.get(&cells[offset]) else {
                return Err("extended interrupt references an undeclared controller".into());
            };
            let end = offset + 1 + width(controller)?;
            if end > cells.len() {
                return Err("extended interrupt specifier is truncated".into());
            }
            result.push((
                controller.path().to_owned(),
                cells[offset + 1..end].to_vec(),
            ));
            offset = end;
        }
    } else if let Some(plain) = node.property("interrupts") {
        let controller = controller(tree, node)?;
        let width = width(controller)?;
        let cells = property_cells(plain)?;
        if cells.is_empty() || cells.len() % width != 0 {
            return Err("interrupt consumer specifier geometry is invalid".into());
        }
        result.extend(
            cells
                .chunks(width)
                .map(|chunk| (controller.path().to_owned(), chunk.to_vec())),
        );
    }
    Ok(result)
}

/// Refuse another consumer of the source, another root-level register extent
/// meeting the aperture, and a header reservation meeting it, in document order.
pub(crate) fn check_collisions(
    tree: &DeviceTree,
    device_path: &str,
    aperture: Region,
    plic_path: &str,
    source: i128,
) -> Result<(), String> {
    for node in tree.nodes() {
        if node.path() == device_path {
            continue;
        }
        let consumed = sources(tree, node)?;
        if consumed.iter().any(|(parent, specifier)| {
            parent == plic_path
                && matches!(specifier.as_slice(), [cell] if i128::from(*cell) == source)
        }) {
            return Err("Witness PLIC source has another original consumer".into());
        }
        if node.property("reg").is_none() {
            continue;
        }
        let mut parent = parent_path(node.path());
        while parent != "/"
            && tree
                .node(parent)
                .expect("a decoded parent")
                .property("ranges")
                .is_some()
        {
            parent = parent_path(parent);
        }
        if parent != "/" {
            continue;
        }
        if register_regions(tree, node.path())?
            .into_iter()
            .any(|region| intersects(aperture, region))
        {
            return Err("Witness AXI aperture overlaps another original physical resource".into());
        }
    }
    let header = tree.reservations().iter().map(|&(address, size)| Region {
        address: u128::from(address),
        size: u128::from(size),
    });
    if header
        .into_iter()
        .any(|region| intersects(aperture, region))
    {
        return Err("Witness AXI aperture overlaps an original header reservation".into());
    }
    Ok(())
}
