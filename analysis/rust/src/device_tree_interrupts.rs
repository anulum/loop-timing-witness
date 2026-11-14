// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — dedicated PLIC context and register binding

//! Bind one dedicated U54 hart and device source to a PLIC machine context
//! and derive its register addresses, as Python's `device_tree_interrupts`
//! does, with the same refusals in the same order.

use crate::device_tree_blob::DeviceTree;
use crate::device_tree_properties::{phandle_nodes, single_cell, string_list};
use crate::device_tree_resources::{Region, parent_path, property_cells, register_regions};
use crate::device_tree_structure::Node;
use std::collections::HashMap;

/// The RISC-V machine external interrupt.
const MACHINE_EXTERNAL_IRQ: u32 = 11;
/// The RISC-V supervisor external interrupt.
const SUPERVISOR_EXTERNAL_IRQ: u32 = 9;
/// Highest PLIC device source.
const MAX_SOURCE: u32 = 1023;
/// Highest U54 hart identifier.
const MAX_U54_HART: i128 = 4;
/// Most contexts a PLIC declares.
const MAX_CONTEXTS: usize = 15872;
/// PLIC register layout offsets.
const ENABLE_BASE: u128 = 0x2000;
const ENABLE_STRIDE: u128 = 0x80;
const CONTEXT_BASE: u128 = 0x0020_0000;
const CONTEXT_STRIDE: u128 = 0x1000;
const WORD_BYTES: u128 = 4;
const BITS_PER_WORD: u128 = 32;

/// The concrete PLIC register layout a binding admits.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PlicBinding {
    /// The SiFive `sifive,plic-1.0.0` layout.
    Sifive,
    /// The actual Spike simulator's legacy `riscv,plic0` layout.
    Spike,
    /// Any other recorded layout name, which no platform binds; Python
    /// refuses it only when the binding is checked.
    Unbound,
}

/// The controller path, dedicated U54 hart, device source and concrete layout of one binding.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PlicSelection {
    /// Original PLIC node path.
    pub path: String,
    /// Dedicated U54 hardware identifier, one through four.
    pub hart: i128,
    /// Nonzero original PLIC device interrupt source.
    pub source: i128,
    /// Concrete register layout.
    pub binding: PlicBinding,
}

/// Physical register addresses of one actual machine context.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PlicRegisters {
    /// Context ordinal in the original `interrupts-extended` array, disabled entries included.
    pub context: usize,
    /// The selected source's priority word.
    pub priority: u128,
    /// The selected context's enable word holding the source bit.
    pub enable_word: u128,
    /// The selected context's priority threshold.
    pub threshold: u128,
    /// The selected context's claim and completion register.
    pub claim: u128,
}

/// Resolve a CPU interrupt controller to its CPU's hardware identifier.
fn hart_of(tree: &DeviceTree, controller: &Node) -> Result<u64, String> {
    if !string_list(controller, "compatible")?
        .iter()
        .any(|value| value == "riscv,cpu-intc")
        || single_cell(controller, "#interrupt-cells")? != 1
        || controller.property("interrupt-controller") != Some(&[])
    {
        return Err("PLIC context does not reference a RISC-V CPU interrupt controller".to_owned());
    }
    let cpu = controller
        .path()
        .rfind('/')
        .and_then(|end| tree.node(&controller.path()[..end]))
        .filter(|cpu| cpu.property("device_type") == Some(b"cpu\0"));
    let Some(cpu) = cpu else {
        return Err("PLIC context parent is not an original CPU node".to_owned());
    };
    let parent = tree.existing(parent_path(cpu.path()));
    let count = single_cell(parent, "#address-cells")?;
    let reg = cpu.property("reg").unwrap_or_default();
    let values = property_cells(reg)?;
    if !matches!(count, 1 | 2)
        || single_cell(parent, "#size-cells")? != 0
        || values.len() != count as usize
    {
        return Err("PLIC context CPU identifier has invalid cell geometry".to_owned());
    }
    Ok(reg
        .iter()
        .fold(0, |value, &byte| (value << 8) + u64::from(byte)))
}

/// Locate the one machine context of a hart among every declared context.
fn context(tree: &DeviceTree, plic: &Node, hart: i128) -> Result<usize, String> {
    let handles = phandle_nodes(tree)?;
    let cells = property_cells(plic.property("interrupts-extended").unwrap_or_default())?;
    if cells.is_empty() || !cells.len().is_multiple_of(2) || cells.len() / 2 > MAX_CONTEXTS {
        return Err("PLIC context array is empty, incomplete or outside bounds".to_owned());
    }
    let mut candidates = Vec::new();
    let mut cpu_paths: HashMap<u64, &str> = HashMap::new();
    for (ordinal, pair) in cells.as_chunks::<2>().0.iter().enumerate() {
        let Some(controller) = handles.get(&pair[0]) else {
            return Err("PLIC context references an undeclared phandle".to_owned());
        };
        let identifier = hart_of(tree, controller)?;
        let path = &controller.path()[..controller.path().rfind('/').unwrap_or_default()];
        if cpu_paths
            .insert(identifier, path)
            .is_some_and(|known| known != path)
        {
            return Err(
                "PLIC contexts reference multiple CPUs with the same hardware identifier"
                    .to_owned(),
            );
        }
        let interrupt = pair[1];
        if !matches!(
            interrupt,
            SUPERVISOR_EXTERNAL_IRQ | MACHINE_EXTERNAL_IRQ | u32::MAX
        ) {
            return Err("PLIC context specifies an unsupported CPU interrupt".to_owned());
        }
        if i128::from(identifier) == hart && interrupt == MACHINE_EXTERNAL_IRQ {
            candidates.push(ordinal);
        }
    }
    match candidates.as_slice() {
        [context] => Ok(*context),
        _ => Err("dedicated hart lacks one unique PLIC machine context".to_owned()),
    }
}

/// Validate one concrete PLIC binding and derive the dedicated machine register addresses.
///
/// # Errors
///
/// Returns Python's refusal text when the selection, layout, source,
/// controller geometry, aperture or context is invalid, or a register lies
/// outside the declared aperture.
pub fn bind_plic(tree: &DeviceTree, selection: &PlicSelection) -> Result<PlicRegisters, String> {
    let outside = "dedicated PLIC selection is outside the admitted U54/source bounds";
    if !(1..=MAX_U54_HART).contains(&selection.hart)
        || !(1..=i128::from(MAX_SOURCE)).contains(&selection.source)
    {
        return Err(outside.to_owned());
    }
    let Some(plic) = tree.node(&selection.path) else {
        return Err(outside.to_owned());
    };
    let compatible = string_list(plic, "compatible")?;
    let declares = |value: &str| compatible.iter().any(|declared| declared == value);
    let bound = match selection.binding {
        PlicBinding::Sifive => declares("sifive,plic-1.0.0"),
        PlicBinding::Spike => {
            declares("riscv,plic0")
                && tree.existing("/").property("model") == Some(b"ucbbar,spike-bare\0")
        }
        PlicBinding::Unbound => false,
    };
    if !bound {
        return Err(
            "PLIC concrete register layout is not bound by the original platform".to_owned(),
        );
    }
    if plic.property("interrupt-controller") != Some(&[])
        || single_cell(plic, "#interrupt-cells")? != 1
        || {
            let sources = single_cell(plic, "riscv,ndev")?;
            !(selection.source <= i128::from(sources) && sources <= MAX_SOURCE)
        }
    {
        return Err("PLIC source or interrupt-controller geometry is invalid".to_owned());
    }
    let aperture = match register_regions(tree, &selection.path)?.as_slice() {
        [region] if region.address != 0 && region.address.is_multiple_of(WORD_BYTES) => *region,
        _ => {
            return Err(
                "PLIC must declare one aligned nonzero physical register aperture".to_owned(),
            );
        }
    };
    let context = context(tree, plic, selection.hart)?;
    registers(aperture, context, selection.source.unsigned_abs())
}

/// Derive one context's register addresses inside its aperture.
fn registers(aperture: Region, context: usize, source: u128) -> Result<PlicRegisters, String> {
    let ordinal = context as u128;
    let offsets = [
        source * WORD_BYTES,
        ENABLE_BASE + ordinal * ENABLE_STRIDE + source / BITS_PER_WORD * WORD_BYTES,
        CONTEXT_BASE + ordinal * CONTEXT_STRIDE,
        CONTEXT_BASE + ordinal * CONTEXT_STRIDE + WORD_BYTES,
    ];
    if offsets
        .iter()
        .any(|&offset| offset + WORD_BYTES > aperture.size)
    {
        return Err("dedicated PLIC registers exceed the declared aperture".to_owned());
    }
    let [priority, enable_word, threshold, claim] = offsets.map(|offset| aperture.address + offset);
    Ok(PlicRegisters {
        context,
        priority,
        enable_word,
        threshold,
        claim,
    })
}
