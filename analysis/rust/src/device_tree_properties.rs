// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — device-tree scalar, string-list and phandle properties

//! Read single cells, string lists and the phandle map, as Python's
//! `device_tree_properties` does, with the same refusal texts.

use crate::device_tree_blob::DeviceTree;
use crate::device_tree_resources::property_cells;
use crate::device_tree_structure::Node;
use std::collections::BTreeMap;

/// The phandle value the specification reserves.
const INVALID_PHANDLE: u32 = u32::MAX;

/// Require exactly one cell for a named property.
///
/// # Errors
///
/// Returns Python's refusal text, naming the node and property, when the
/// property is absent, not whole cells or not one cell.
pub fn single_cell(node: &Node, name: &str) -> Result<u32, String> {
    let Some(raw) = node.property(name) else {
        return Err(format!(
            "device-tree scalar property is absent: {}:{name}",
            node.path()
        ));
    };
    match property_cells(raw)?.as_slice() {
        [value] => Ok(*value),
        _ => Err(format!(
            "device-tree property is not one scalar: {}:{name}",
            node.path()
        )),
    }
}

/// Require a terminated ASCII string list without empty elements.
///
/// # Errors
///
/// Returns Python's refusal text, naming the node and property, when the
/// property is absent, empty, unterminated, not ASCII or holds an empty element.
pub fn string_list(node: &Node, name: &str) -> Result<Vec<String>, String> {
    let Some(body) = node.property(name).unwrap_or_default().strip_suffix(&[0]) else {
        return Err(format!(
            "device-tree string property is absent or unterminated: {}:{name}",
            node.path()
        ));
    };
    if !body.is_ascii() {
        return Err(format!(
            "device-tree property string is not ASCII: {}:{name}",
            node.path()
        ));
    }
    let values: Vec<String> = body
        .split(|&byte| byte == 0)
        .map(|value| value.iter().map(|&byte| char::from(byte)).collect())
        .collect();
    if values.iter().any(String::is_empty) {
        return Err(format!(
            "device-tree string property contains an empty element: {}:{name}",
            node.path()
        ));
    }
    Ok(values)
}

/// Resolve every node's unique phandle, refusing reserved, conflicting or repeated ones.
///
/// # Errors
///
/// Returns Python's refusal text when a phandle is not one cell, is reserved,
/// disagrees with its legacy `linux,phandle` alias or names two nodes.
pub fn phandle_nodes(tree: &DeviceTree) -> Result<BTreeMap<u32, &Node>, String> {
    let mut result = BTreeMap::new();
    for node in tree.nodes() {
        let aliases = ["phandle", "linux,phandle"]
            .into_iter()
            .filter(|name| node.property(name).is_some())
            .map(|name| single_cell(node, name))
            .collect::<Result<Vec<u32>, String>>()?;
        let Some(&handle) = aliases.first() else {
            continue;
        };
        if handle == 0 || handle == INVALID_PHANDLE || aliases.iter().any(|&value| value != handle)
        {
            return Err(
                "device-tree phandle is reserved or disagrees with its legacy alias".to_owned(),
            );
        }
        if result.insert(handle, node).is_some() {
            return Err("device-tree phandle references multiple nodes".to_owned());
        }
    }
    Ok(result)
}
