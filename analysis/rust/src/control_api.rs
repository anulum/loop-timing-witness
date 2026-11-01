// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — public CONTROL and COMPUTE run loading

//! Load CONTROL and COMPUTE runs and decode their events, as the Python analysis does.
//!
//! [`load_control_run`] validates a run manifest, its hash-bound measurement
//! domain and every referenced input, and keeps the verified bytes.
//! [`decode_control_events`] decodes the run's event records. Each refusal is
//! the same text the Python `load_run` and `decode_events` give for the same
//! files. [`control_events_summary`] builds the report's `events` block, as
//! the Python `events_block` does.

use crate::control_analysis::events_block;
use crate::control_events::{Names, decode};
use crate::control_manifest::{ControlRun, load};
use crate::control_number::Num;
use serde_json::{Map, Value};
use std::collections::BTreeMap;
use std::path::Path;

/// A validated run and its hash-bound input bytes.
#[derive(Debug)]
pub struct ControlInputs(ControlRun);

impl ControlInputs {
    /// The schema-valid run manifest.
    pub fn manifest(&self) -> &Map<String, Value> {
        &self.0.manifest
    }

    /// The valid measurement-domain contract bound by the run.
    pub fn domain(&self) -> &Value {
        &self.0.domain
    }

    /// Complete verified input bytes by name: `events`, `tracking`, `power` and any
    /// declared receipt; an input declared `null` has no entry.
    pub fn files(&self) -> &BTreeMap<String, Vec<u8>> {
        &self.0.files
    }

    /// The resolved directory that holds the manifest.
    pub fn directory(&self) -> &Path {
        &self.0.directory
    }
}

/// One timestamp captured by the fabric witness.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ControlEvent {
    /// Event name from the measurement domain.
    pub name: String,
    /// Zero-based control or compute cycle.
    pub cycle: u32,
    /// Free-running fabric counter value, in clock ticks.
    pub ticks: u64,
}

/// Load and validate one run, reading its manifest from the path.
///
/// # Errors
///
/// Returns the Python analysis's refusal text when the manifest, the
/// measurement domain or any input cannot be read or does not validate.
pub fn load_control_run(path: &Path) -> Result<ControlInputs, String> {
    load(path, None).map(ControlInputs)
}

/// Load and validate one run from manifest bytes already read for its path.
///
/// Relative inputs still resolve against the path's directory.
///
/// # Errors
///
/// Returns the Python analysis's refusal text, as [`load_control_run`].
pub fn load_control_run_bytes(path: &Path, root: &[u8]) -> Result<ControlInputs, String> {
    load(path, Some(root)).map(ControlInputs)
}

/// Decode the run's complete event file for its declared profile and cycle count.
///
/// # Errors
///
/// Returns the Python analysis's refusal text for a partial or empty file,
/// nonzero reserved bits, a code outside the profile, a cycle outside the run,
/// a non-monotonic order or a repeated event kind in one cycle.
pub fn decode_control_events(inputs: &ControlInputs) -> Result<Vec<ControlEvent>, String> {
    let contracts = &inputs.domain()["design_contracts"];
    let manifest = inputs.manifest();
    let profile = manifest["profile"]
        .as_str()
        .expect("schema-checked profile");
    let events = decode(
        &inputs.files()["events"],
        contracts,
        profile,
        Num::of(&manifest["cycle_count"]),
    )?;
    let names = Names::of(contracts);
    Ok(events
        .into_iter()
        .map(|event| ControlEvent {
            name: names.get(event.code).unwrap_or_default().to_owned(),
            cycle: event.cycle,
            ticks: event.ticks,
        })
        .collect())
}

/// One same-cycle interval observation of an analysed cycle.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct IntervalRow {
    /// Analysed cycle.
    pub cycle: u32,
    /// Interval name from the measurement domain.
    pub interval: String,
    /// Interval length in clock ticks.
    pub ticks: u64,
}

/// Build the report's `events` block and the per-cycle interval rows.
///
/// The block holds the analysed event and cycle counts, the observation span,
/// the Type-7 interval distributions, the deadline and fault counts of a
/// CONTROL run and the adjacent-cycle jitter, as the Python `events_block`
/// builds them, including Python's integer or float type of counts derived
/// from the declared cycles.
///
/// # Errors
///
/// Returns the Python analysis's refusal text for an event file that does not
/// decode, a fault schedule that disagrees with the captured injections, or an
/// event order that contradicts the interval and fault rules.
pub fn control_events_summary(inputs: &ControlInputs) -> Result<(Value, Vec<IntervalRow>), String> {
    let contracts = &inputs.domain()["design_contracts"];
    let manifest = inputs.manifest();
    let profile = manifest["profile"]
        .as_str()
        .expect("schema-checked profile");
    let events = decode(
        &inputs.files()["events"],
        contracts,
        profile,
        Num::of(&manifest["cycle_count"]),
    )?;
    let (block, rows) = events_block(manifest, contracts, &events)?;
    let rows = rows
        .into_iter()
        .map(|row| IntervalRow {
            cycle: row.cycle,
            interval: row.interval,
            ticks: row.ticks,
        })
        .collect();
    Ok((block, rows))
}
