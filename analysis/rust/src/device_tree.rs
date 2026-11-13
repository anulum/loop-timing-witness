// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — original device-tree decoding and resource readers

//! Decode original device-tree blobs and read the resources an AMP image binds.
//!
//! These readers port the Python analysis modules `device_tree_blob`,
//! `device_tree_structure`, `device_tree_resources`, `device_tree_properties`
//! and `device_tree_interrupts`. Every value, every refusal text and the order
//! in which refusals are reached is Python's. The crate tests hold them to the
//! corpus that `tests/test_device_tree_corpus.py` builds from real `dtc`
//! output and Python's own readers.
//!
//! - [`decode_device_tree`] validates the header, block extents, memory
//!   reservations and structure tokens of a whole blob.
//! - [`register_regions`] translates a node's `reg` extents through every
//!   ancestor `ranges` mapping to root physical addresses.
//! - [`single_cell`], [`string_list`] and [`phandle_nodes`] read scalar,
//!   string-list and phandle properties.
//! - [`bind_plic`] binds one dedicated hart and device source to its PLIC
//!   machine context and derives the context's register addresses.
//!
//! [`decode_device_tree`]: crate::device_tree::decode_device_tree
//! [`register_regions`]: crate::device_tree::register_regions
//! [`single_cell`]: crate::device_tree::single_cell
//! [`string_list`]: crate::device_tree::string_list
//! [`phandle_nodes`]: crate::device_tree::phandle_nodes
//! [`bind_plic`]: crate::device_tree::bind_plic

pub use crate::device_tree_blob::{DeviceTree, decode_device_tree};
pub use crate::device_tree_interrupts::{PlicBinding, PlicRegisters, PlicSelection, bind_plic};
pub use crate::device_tree_properties::{phandle_nodes, single_cell, string_list};
pub use crate::device_tree_resources::{Region, property_cells, register_regions};
pub use crate::device_tree_structure::Node;

#[cfg(test)]
#[path = "../tests/unit/device_tree.rs"]
mod tests;
