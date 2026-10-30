// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — complete neural acquisition verification

//! Full native manifest loading; no Python prevalidation or substitute envelope.

use crate::capture::{self, Channel, CounterReceipt};
use crate::files::{FileRef, decode, digest, read_bound};
use crate::manifest::Manifest;
use crate::receipts::{ResetTool, Tool};
const JSON_LIMIT: usize = 65536;
const SOURCE_LIMIT: usize = 1048576;
use std::collections::BTreeMap;
use std::path::Path;

/// All original bytes and full actual decoded capture inputs.
pub(crate) struct BoundRun {
    /// Actual directory for finite native artifact/log binding.
    pub root: std::path::PathBuf,
    /// Complete admitted original root.
    pub manifest: Manifest,
    /// Original source bodies indexed by original name.
    pub sources: BTreeMap<String, Vec<u8>>,
    /// Complete original bytes by semantic role.
    pub files: BTreeMap<String, Vec<u8>>,
    /// Original decoded channel records.
    pub channels: Vec<Channel>,
    /// Actual source counter receipt.
    pub counts: CounterReceipt,
}

/// Bind one original role without rereading it during later native analysis.
pub(crate) fn role(
    files: &mut BTreeMap<String, Vec<u8>>,
    root: &Path,
    name: &str,
    reference: &FileRef,
    limit: usize,
) -> Result<(), String> {
    files.insert(name.into(), read_bound(root, reference, limit)?);
    Ok(())
}

/// Load every actual original normal-tool reference under its declared finite bound.
pub(crate) fn tool_files(
    files: &mut BTreeMap<String, Vec<u8>>,
    root: &Path,
    tool: Tool,
) -> Result<(), String> {
    let _original_scope = tool.scope;
    for (name, reference) in [
        (
            "compiler_simulator_runtime",
            tool.compiler_simulator_runtime,
        ),
        (
            "source_owned_public_model_checker",
            tool.source_owned_public_model_checker,
        ),
        ("counter_receipt", tool.counter_receipt),
        ("raw_spike_trace", tool.raw_spike_trace),
        ("original_stimulus", tool.original_stimulus),
        ("actual_completion", tool.actual_completion),
        ("existing_trial_analysis", tool.existing_trial_analysis),
        ("declared_clock_schedule", tool.declared_clock_schedule),
    ] {
        let limit = if name == "existing_trial_analysis" {
            SOURCE_LIMIT
        } else if name == "counter_receipt" {
            4096
        } else {
            JSON_LIMIT
        };
        role(files, root, name, &reference, limit)?;
    }
    Ok(())
}

/// Bind original epoch1 reset/prefix references and reuse the common actual role fields.
pub(crate) fn reset_files(
    files: &mut BTreeMap<String, Vec<u8>>,
    root: &Path,
    tool: ResetTool,
) -> Result<(), String> {
    role(
        files,
        root,
        "reset_epoch_receipt",
        &tool.reset_epoch_receipt,
        JSON_LIMIT,
    )?;
    for (name, reference) in [
        ("abandoned_input_trace", tool.abandoned_prefix_traces.input),
        (
            "abandoned_numerical_trace",
            tool.abandoned_prefix_traces.numerical,
        ),
        (
            "abandoned_raw_spike_trace",
            tool.abandoned_prefix_traces.raw_spike,
        ),
        (
            "abandoned_service_trace",
            tool.abandoned_prefix_traces.service,
        ),
    ] {
        role(files, root, name, &reference, JSON_LIMIT)?;
    }
    tool_files(
        files,
        root,
        Tool {
            scope: tool.scope,
            compiler_simulator_runtime: tool.compiler_simulator_runtime,
            source_owned_public_model_checker: tool.source_owned_public_model_checker,
            counter_receipt: tool.counter_receipt,
            raw_spike_trace: tool.raw_spike_trace,
            original_stimulus: tool.original_stimulus,
            actual_completion: tool.actual_completion,
            existing_trial_analysis: tool.existing_trial_analysis,
            declared_clock_schedule: tool.declared_clock_schedule,
        },
    )
}

/// Bind complete fixture and capture bytes after the caller's closed source admission.
pub(crate) fn finish(
    root: &Path,
    manifest: Manifest,
    sources: BTreeMap<String, Vec<u8>>,
    mut files: BTreeMap<String, Vec<u8>>,
) -> Result<BoundRun, String> {
    for (name, expected) in [
        (
            "original_stimulus",
            "8f0e0a2ced3e5170c78c5ee058eb90faea1ceb77cece2f940568851fe9ed64f8",
        ),
        (
            "reference_projection",
            "c405de711cdbf8fae3a0c668ecfa643e7a6e460bad60c05b5bd0bfca208a3dd2",
        ),
    ] {
        if digest(&files[name]) != expected {
            return Err("Public neural fixture differs from the selected source contract.".into());
        }
    }
    if sources.get("stimuli.txt") != files.get("original_stimulus") {
        return Err(
            "Public neural source stimulus differs from its identified input binding.".into(),
        );
    }
    let counts: CounterReceipt = decode(&files["counter_receipt"], "actual counters")?;
    if counts.schema_id != "loop-timing-witness.neural-capture-counts.v1"
        || !(1..=32).contains(&counts.drop_counter_bits)
    {
        return Err("Invalid original counter receipt version/width.".into());
    }
    let mut channels = Vec::new();
    for (index, declaration) in manifest.channels.iter().enumerate() {
        let population = if index == 2 {
            manifest.completion.observed_service_packets as u32
        } else {
            manifest.step_count
        };
        let c = &counts.channels[index];
        if c.role != declaration.role || c.dropped > (1_u64 << counts.drop_counter_bits) - 1 {
            return Err("Original counter role/value outside admitted range.".into());
        }
        let raw = read_bound(root, &declaration.capture, (population as usize + 2) * 16)?;
        let payload = read_bound(root, &declaration.payload, population as usize * 16)?;
        let markers = read_bound(root, &declaration.markers, 32)?;
        let channel = capture::decode(&raw, declaration.role, population)?;
        files.insert(format!("{}_capture", declaration.role), raw);
        files.insert(format!("{}_payload", declaration.role), payload);
        files.insert(format!("{}_markers", declaration.role), markers);
        channels.push(channel);
    }
    Ok(BoundRun {
        root: root.to_path_buf(),
        manifest,
        sources,
        files,
        channels,
        counts,
    })
}
