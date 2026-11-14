// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — the memory, device and PLIC resources of an AMP platform

//! Bind an AMP platform's resources as the Python modules `amp_platform`,
//! `amp_memory`, `amp_device` and `amp_collisions` do.
//!
//! [`bind_platform`] admits the firmware and telemetry reservations inside
//! one RAM bank each, the enabled Witness AXI device with its one PLIC source
//! and aperture, and a PLIC aperture that meets no RAM bank, reservation or
//! header reservation. Every refusal is Python's text for the same first
//! defect.
//!
//! [`bind_platform`]: crate::amp_platform::bind_platform

pub use crate::amp_device::WitnessDevice;
use crate::amp_device::bind_device;
pub use crate::amp_memory::{MemorySelection, ReservedMemory};
use crate::amp_memory::{bind_memory, intersects};
use crate::device_tree::{DeviceTree, PlicSelection, Region, register_regions};

/// The admitted resources and the dedicated hart and source.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct AmpPlatform {
    /// The firmware and telemetry reservations.
    pub memory: ReservedMemory,
    /// The Witness device aperture and PLIC registers.
    pub device: WitnessDevice,
    /// Dedicated hart.
    pub hart: i128,
    /// PLIC source of the device.
    pub source: i128,
}

/// Admit one complete AMP resource set from a decoded device tree.
///
/// # Errors
///
/// Python's refusal text for the first defect of the memory selection, the
/// reservations, the backing RAM, the device, its interrupt or aperture, the
/// PLIC binding, or a PLIC aperture meeting RAM or a reservation.
pub fn bind_platform(
    tree: &DeviceTree,
    memory: &MemorySelection,
    device_path: &str,
    plic: &PlicSelection,
) -> Result<AmpPlatform, String> {
    let admitted = bind_memory(tree, memory)?;
    let device = bind_device(tree, device_path, plic)?;
    // `bind_device` bound the PLIC, which admits exactly one register region.
    let controller = register_regions(tree, &plic.path)?[0];
    let mut regions = register_regions(tree, &memory.ram_path)?;
    regions.extend([admitted.firmware, admitted.shared]);
    for node in tree.nodes() {
        if node.property("device_type") == Some(b"memory\0") && node.path() != memory.ram_path {
            regions.extend(register_regions(tree, node.path())?);
        }
    }
    let header = tree.reservations().iter().map(|&(address, size)| Region {
        address: u128::from(address),
        size: u128::from(size),
    });
    if regions.iter().any(|region| intersects(controller, *region))
        || header
            .into_iter()
            .any(|region| intersects(controller, region))
    {
        return Err("AMP PLIC aperture intersects original RAM or a memory reservation".into());
    }
    Ok(AmpPlatform {
        memory: admitted,
        device,
        hart: plic.hart,
        source: plic.source,
    })
}

#[cfg(test)]
#[path = "../tests/unit/amp_platform.rs"]
mod tests;
