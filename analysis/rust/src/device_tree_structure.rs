// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — device-tree structure block decoded as the Python analysis does

//! Decode one version 17 structure block into nodes with unique paths and
//! ordered properties, as Python's `device_tree_structure` does: the same
//! tokens, names, nesting, ordering, padding and termination rules, refused
//! with the same texts in the same order.

use std::collections::{HashMap, HashSet};

/// Bytes in one structure-block word.
const ALIGNMENT: usize = 4;
/// Bytes in a property's header: its value size and its name offset.
const PROPERTY_HEADER: usize = 8;
/// Deepest node nesting the decoder admits.
const MAX_DEPTH: usize = 64;
/// Most nodes one tree may hold.
const MAX_NODES: usize = 16384;
/// Longest node path, in characters.
const MAX_PATH_CHARACTERS: usize = 4096;
/// Version 17 structure tokens from the Devicetree Specification.
const BEGIN_NODE: u32 = 1;
const END_NODE: u32 = 2;
const PROPERTY: u32 = 3;
const NOP: u32 = 4;
const END: u32 = 9;

/// One decoded node with its uninterpreted property bytes in document order.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Node {
    path: String,
    properties: Vec<(String, Vec<u8>)>,
}

impl Node {
    /// The absolute unique path; the root is `/`.
    #[must_use]
    pub fn path(&self) -> &str {
        &self.path
    }

    /// Every property name and its exact bytes, in document order.
    #[must_use]
    pub fn properties(&self) -> &[(String, Vec<u8>)] {
        &self.properties
    }

    /// One property's exact bytes, when the node declares it.
    #[must_use]
    pub fn property(&self, name: &str) -> Option<&[u8]> {
        self.properties
            .iter()
            .find(|(declared, _)| declared == name)
            .map(|(_, value)| value.as_slice())
    }
}

/// Decoded nodes in document order, with each node's position by path.
#[derive(Default)]
pub(crate) struct Nodes {
    pub(crate) list: Vec<Node>,
    pub(crate) index: HashMap<String, usize>,
}

/// Read one big-endian word that the caller has bounded.
fn word(data: &[u8], offset: usize) -> u32 {
    let mut bytes = [0; ALIGNMENT];
    bytes.copy_from_slice(&data[offset..offset + ALIGNMENT]);
    u32::from_be_bytes(bytes)
}

/// Read one bounded ASCII string and the offset after its terminator.
pub(crate) fn terminated_string(data: &[u8], offset: usize) -> Result<(String, usize), String> {
    if offset >= data.len() {
        return Err("device-tree string offset outside its block".to_owned());
    }
    let Some(length) = data[offset..].iter().position(|&byte| byte == 0) else {
        return Err("unterminated device-tree string".to_owned());
    };
    let text = &data[offset..offset + length];
    if !text.is_ascii() {
        return Err("device-tree name is not ASCII".to_owned());
    }
    Ok((
        text.iter().map(|&byte| char::from(byte)).collect(),
        offset + length + 1,
    ))
}

/// Require zero padding and advance to the next structure word.
///
/// The structure block is a whole number of words and every offset given here
/// lies within it, so the padding never runs past the block; Python still
/// tests that bound, which `get` keeps without a separate branch.
fn aligned_offset(data: &[u8], offset: usize) -> Result<usize, String> {
    let aligned = offset.next_multiple_of(ALIGNMENT);
    match data.get(offset..aligned) {
        Some(padding) if padding.iter().all(|&byte| byte == 0) => Ok(aligned),
        _ => Err("invalid device-tree structure padding".to_owned()),
    }
}

/// Keep one complete, uniquely named property of the current node.
fn property(data: &[u8], strings: &[u8], offset: usize, node: &mut Node) -> Result<usize, String> {
    if offset + PROPERTY_HEADER > data.len() {
        return Err("truncated device-tree property header".to_owned());
    }
    let size = word(data, offset) as usize;
    let name_offset = word(data, offset + ALIGNMENT) as usize;
    let start = offset + PROPERTY_HEADER;
    let (name, _) = terminated_string(strings, name_offset)?;
    if name.is_empty()
        || name.contains('/')
        || node.property(&name).is_some()
        || size > data.len() - start
    {
        return Err("invalid or duplicate device-tree property".to_owned());
    }
    node.properties
        .push((name, data[start..start + size].to_vec()));
    aligned_offset(data, start + size)
}

/// Admit one uniquely named root or child and open its nesting level.
fn begin_node(
    data: &[u8],
    offset: usize,
    nodes: &mut Nodes,
    stack: &mut Vec<usize>,
    parents: &mut HashSet<usize>,
) -> Result<usize, String> {
    if stack.len() >= MAX_DEPTH || nodes.list.len() >= MAX_NODES {
        return Err("device-tree depth or node count exceeds the parser resource limit".to_owned());
    }
    let (name, offset) = terminated_string(data, offset)?;
    let top = stack.last().copied();
    let invalid = match top {
        None => !name.is_empty() || !nodes.list.is_empty(),
        Some(_) => name.is_empty() || name.contains('/'),
    };
    if invalid {
        return Err("invalid device-tree root or child name".to_owned());
    }
    let path = match top {
        Some(parent) => format!("{}/{name}", nodes.list[parent].path.trim_end_matches('/')),
        None => "/".to_owned(),
    };
    if path.len() > MAX_PATH_CHARACTERS {
        return Err("device-tree node path exceeds the parser resource limit".to_owned());
    }
    if nodes.index.contains_key(&path) {
        return Err("duplicate device-tree node path".to_owned());
    }
    let position = nodes.list.len();
    nodes.index.insert(path.clone(), position);
    nodes.list.push(Node {
        path,
        properties: Vec::new(),
    });
    if let Some(parent) = top {
        parents.insert(parent);
    }
    stack.push(position);
    aligned_offset(data, offset)
}

/// Decode one complete tree with unique paths and ordered properties.
pub(crate) fn decode_structure(data: &[u8], strings: &[u8]) -> Result<Nodes, String> {
    let mut nodes = Nodes::default();
    let mut stack = Vec::new();
    let mut parents = HashSet::new();
    let mut offset = 0;
    while offset + ALIGNMENT <= data.len() {
        let token = word(data, offset);
        offset += ALIGNMENT;
        match token {
            NOP => {}
            BEGIN_NODE => offset = begin_node(data, offset, &mut nodes, &mut stack, &mut parents)?,
            PROPERTY => {
                let Some(&top) = stack.last().filter(|top| !parents.contains(top)) else {
                    return Err("device-tree property outside a node or after a child".to_owned());
                };
                offset = property(data, strings, offset, &mut nodes.list[top])?;
            }
            END_NODE => {
                if stack.pop().is_none() {
                    return Err("unmatched device-tree node end".to_owned());
                }
            }
            END => {
                if !stack.is_empty() || nodes.list.is_empty() || offset != data.len() {
                    return Err("device-tree end precedes complete tree termination".to_owned());
                }
                return Ok(nodes);
            }
            _ => return Err("unknown device-tree structure token".to_owned()),
        }
    }
    Err("device-tree structure lacks its final end token".to_owned())
}
