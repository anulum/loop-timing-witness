// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — public neural carrier declaration reader

//! Validate carrier declarations without opening referenced sources or admitting a run.

use crate::capture::Role;
use crate::files::{FileRef, digest};
use crate::public_manifest_fields::PublicManifest;
use serde_json::Value;
use std::collections::BTreeSet;
use std::fs::OpenOptions;
use std::io::Read;
use std::os::unix::fs::OpenOptionsExt;
use std::path::Path;

/// Exact schema used by the public declaration reader.
pub const SCHEMA_SHA256: &str = "846d131e51cff0dee88d8c9484e435eb02444e0f0a18b58e9d5f053633164f8f";
const JSON_LIMIT: usize = 65536;
const SOURCE_LIMIT: u64 = 1048576;
const PATH_LIMIT: usize = 4096;
const LINUX_O_NOFOLLOW: i32 = 0o400000;
const LINUX_O_NONBLOCK: i32 = 0o4000;

/// Return whether the entire lowercase SHA-256 declaration is valid.
fn valid_digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

/// Check portable canonical names and role allocations without opening the reference.
fn reference(reference: &FileRef, limit: u64) -> Result<(), String> {
    let name = &reference.path;
    if name.is_empty()
        || name.len() > PATH_LIMIT
        || name.split('/').any(|part| {
            part.is_empty()
                || part == "."
                || part == ".."
                || !part
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || b"_.-".contains(&byte))
        })
        || reference.byte_length > limit
        || !valid_digest(&reference.sha256)
    {
        return Err("Neural file reference requires a bounded portable within-run path.".into());
    }
    Ok(())
}

/// Read a finite regular Linux manifest descriptor without following the final symlink.
fn root_bytes(path: &Path) -> Result<Vec<u8>, String> {
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(LINUX_O_NOFOLLOW | LINUX_O_NONBLOCK)
        .open(path)
        .map_err(|_| {
            "Cannot read neural manifest as a regular file without symlinks.".to_owned()
        })?;
    if !file
        .metadata()
        .map_err(|_| "Cannot inspect neural manifest descriptor.".to_owned())?
        .is_file()
    {
        return Err("Neural manifest must be a regular file.".into());
    }
    let mut raw = Vec::new();
    file.take(JSON_LIMIT as u64 + 1)
        .read_to_end(&mut raw)
        .map_err(|_| "Cannot read neural manifest bytes.".to_owned())?;
    if raw.len() > JSON_LIMIT {
        return Err("Neural manifest exceeds its byte allocation.".into());
    }
    Ok(raw)
}

/// Require the public root identity, complete finite populations and exact event meanings.
fn identity(m: &PublicManifest) -> Result<(), String> {
    let name = &m.run_id;
    let valid_name = !name.is_empty()
        && name.len() <= 128
        && name.as_bytes()[0].is_ascii_alphanumeric()
        && name
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"_.-".contains(&byte));
    let codes = &m.event_codes;
    if m.schema_id != "loop-timing-witness.neural-step-run.v1"
        || m.native_source_cohort != "sc-neurocore-neural-step-1n1b16t.v1"
        || m.profile != "neural-step-capture"
        || m.evidence_class != "simulated-timing"
        || !valid_name
        || m.epoch > 1
        || m.step_count != 1000
        || m.counter_bits != 64
        || m.encoder_timestamp_bits != 16
        || m.encoder_id_width != 1
        || ![8, 1024].contains(&m.fifo_capacity_records)
        || !(1..=65535).contains(&m.capture_horizon_edges)
        || m.encoder_tail_edges != 4
        || m.accepted_oracle_commit != "0593c3df906d9493ac5c1da5c5e528f6078d275e"
        || (
            codes.input_step_applied,
            codes.state_and_raw_spike_observed,
            codes.encoder_packet_serviced,
            codes.alignment_marker,
        ) != (14, 15, 16, 17)
    {
        return Err("Neural manifest violates its closed schema or exact integer contract.".into());
    }
    Ok(())
}

/// Validate every source pin, channel role/count and complete file declaration.
fn declarations(m: &PublicManifest) -> Result<(), String> {
    let pins = &m.sc_body_pins;
    if [
        &pins.lif,
        &pins.testbench,
        &pins.encoder,
        &pins.model,
        &pins.constants,
        &pins.checker,
        &pins.checker_tests,
    ]
    .iter()
    .any(|pin| !valid_digest(pin))
    {
        return Err("Neural source pins require lowercase SHA-256 declarations.".into());
    }
    if m.source_files.is_empty() {
        return Err("Neural manifest requires a nonempty source population.".into());
    }
    let mut paths = BTreeSet::new();
    for source in &m.source_files {
        reference(source, SOURCE_LIMIT)?;
        if !paths.insert(&source.path) {
            return Err("Neural source references contain a duplicate path.".into());
        }
    }
    for item in [
        &m.tool_receipt,
        &m.input_trace,
        &m.numerical_trace,
        &m.numerical_projection,
        &m.reference_projection,
        &m.service_trace,
        &m.clock_schedule_ref,
        &m.source_contract_ref,
    ] {
        reference(item, JSON_LIMIT as u64)?;
    }
    let completion = &m.completion;
    if [
        completion.requested_steps,
        completion.observed_states,
        completion.raw_spikes,
        completion.observed_service_packets,
    ]
    .iter()
    .any(|count| *count > 65535)
    {
        return Err("Neural completion count exceeds its carrier allocation.".into());
    }
    for (channel, role) in m
        .channels
        .iter()
        .zip([Role::Input, Role::State, Role::Service])
    {
        if channel.role != role
            || channel.marker_records > 2
            || [
                channel.attempts,
                channel.accepted,
                channel.dropped,
                channel.drained,
                channel.payload_records,
            ]
            .iter()
            .any(|count| *count > 65535)
        {
            return Err("Neural channel declarations violate their closed carrier.".into());
        }
        for item in [&channel.capture, &channel.payload, &channel.markers] {
            reference(item, JSON_LIMIT as u64)?;
        }
    }
    Ok(())
}

/// Exclude serde's positional struct encoding where the JSON schema requires objects.
fn object_containers(document: &Value) -> bool {
    document.is_object()
        && [
            "sc_body_pins",
            "completion",
            "event_codes",
            "tool_receipt",
            "input_trace",
            "numerical_trace",
            "numerical_projection",
            "reference_projection",
            "service_trace",
            "clock_schedule_ref",
            "source_contract_ref",
        ]
        .iter()
        .all(|name| document[name].is_object())
        && document["source_files"]
            .as_array()
            .is_some_and(|sources| sources.iter().all(Value::is_object))
        && document["channels"].as_array().is_some_and(|channels| {
            channels.iter().all(|channel| {
                channel.is_object()
                    && ["capture", "payload", "markers"]
                        .iter()
                        .all(|name| channel[name].is_object())
            })
        })
}

/// Read the closed public carrier as declarations only, without trusted source admission.
///
/// The final manifest component must be a regular Linux file, at most 65,536 bytes.
/// All integer and boolean fields are deserialised directly into their distinct types;
/// unknown and duplicate members are refused by the closed typed decoder. Schema objects
/// cannot be replaced with positional arrays, including nested file references, channel
/// declarations, source pins, completion and event meanings. Referenced source, policy,
/// trace and runtime files are never opened. A successful result is not
/// a complete bound run, numerical verdict, runtime selection or source-owner adoption.
///
/// # Errors
///
/// Returns an authored refusal for malformed bytes, unsupported file kinds, excessive
/// allocations or declarations contradicting the public schema and portable path laws.
pub fn load_neural_manifest(path: &Path) -> Result<Value, String> {
    let (_, document, _) = acquire(path)?;
    Ok(document)
}

/// Acquire one root snapshot and validate its entire closed typed declaration.
pub(crate) fn acquire(path: &Path) -> Result<(Vec<u8>, Value, PublicManifest), String> {
    let raw = root_bytes(path)?;
    if digest(include_bytes!("../neural-step-run.schema.json")) != SCHEMA_SHA256 {
        return Err("Installed neural manifest schema differs from its admitted body.".into());
    }
    let document = crate::files::decode(&raw, "public neural manifest")?;
    if !object_containers(&document) {
        return Err("Neural manifest requires schema object containers.".into());
    }
    let manifest: PublicManifest = crate::files::decode(&raw, "public neural manifest")?;
    identity(&manifest)?;
    declarations(&manifest)?;
    Ok((raw, document, manifest))
}
