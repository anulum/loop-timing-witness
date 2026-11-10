// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — public neural carrier declaration reader

//! Validate carrier declarations without opening referenced sources or admitting a run.
//!
//! The checks and their refusal texts follow Python's `decode_neural_manifest`
//! in the same order, so a declaration with several defects is refused for the
//! same first one: the byte allocation, the bounded run JSON decoding, the
//! closed schema with exact integers, the exact identity grammar, each source
//! reference, repeated source paths, then the root and channel references.

use crate::control_json::decode_object;
use crate::control_schema::Schema;
use crate::files::{FileRef, digest};
use crate::public_manifest_fields::PublicManifest;
use serde_json::Value;
use std::collections::BTreeSet;
use std::fs::OpenOptions;
use std::io::Read;
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::OpenOptionsExt;
use std::path::Path;
use std::sync::LazyLock;

/// Exact schema used by the public declaration reader.
pub const SCHEMA_SHA256: &str = "846d131e51cff0dee88d8c9484e435eb02444e0f0a18b58e9d5f053633164f8f";
const JSON_LIMIT: usize = 65536;
const SOURCE_LIMIT: u64 = 1048576;
const PATH_LIMIT: usize = 4096;
const LINUX_O_NOFOLLOW: i32 = 0o400000;
const LINUX_O_NONBLOCK: i32 = 0o4000;
/// The refusal of bytes that are not one bounded strict JSON object.
const NOT_JSON: &str = "Neural manifest must contain a strict UTF-8 JSON object.";
/// The refusal of a document outside the closed schema or its exact integers.
const NOT_CLOSED: &str = "Neural manifest violates its closed schema or exact integer contract.";

/// The embedded carrier schema; one copy serves both its digest check and validation.
static SCHEMA_TEXT: &str = include_str!("../neural-step-run.schema.json");
/// The committed carrier schema, read as Python's validator reads it.
static SCHEMA: LazyLock<Schema> =
    LazyLock::new(|| Schema::load(SCHEMA_TEXT).expect("committed schema"));

/// Return whether the entire lowercase SHA-256 declaration is valid.
fn valid_digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

/// Tell whether any number of the integer-only carrier has a decimal encoding.
fn has_decimal(value: &Value) -> bool {
    match value {
        Value::Number(number) => number.is_f64(),
        Value::Array(items) => items.iter().any(has_decimal),
        Value::Object(members) => members.values().any(has_decimal),
        _ => false,
    }
}

/// Require an exact lowercase digest, then a portable canonical name within the role's allocation.
fn reference(reference: &FileRef, limit: u64) -> Result<&str, String> {
    if !valid_digest(&reference.sha256) {
        return Err("Neural file reference requires an exact lowercase SHA-256.".into());
    }
    // An empty name has one empty part; the schema already requires one character.
    let name = &reference.path;
    if name.len() > PATH_LIMIT
        || name.split('/').any(|part| {
            part.is_empty()
                || part == "."
                || part == ".."
                || !part
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || b"_.-".contains(&byte))
        })
        || reference.byte_length > limit
    {
        return Err("Neural file reference requires a bounded portable within-run path.".into());
    }
    Ok(name)
}

/// Read a finite regular Linux manifest descriptor without following the final symlink.
fn root_bytes(path: &Path) -> Result<Vec<u8>, String> {
    if path.as_os_str().as_bytes().contains(&0) {
        return Err("Neural manifest path contains an invalid NUL character.".into());
    }
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

/// Require the whole run identifier and every source pin, which the schema anchors only by line.
///
/// The schema's `^…$` patterns are searched as Python's `re.search` does, so
/// they also admit the token followed by one final newline; Python's whole-string
/// grammar refuses exactly those. The schema bytes are pinned by their digest.
fn exact_identity(m: &PublicManifest) -> Result<(), String> {
    let pins = &m.sc_body_pins;
    if [
        &m.run_id,
        &pins.lif,
        &pins.testbench,
        &pins.encoder,
        &pins.model,
        &pins.constants,
        &pins.checker,
        &pins.checker_tests,
    ]
    .iter()
    .any(|token| token.ends_with('\n'))
    {
        return Err("Neural run identity and source pins require exact grammar.".into());
    }
    Ok(())
}

/// Check every source reference, then repeated source paths, then the root and channel references.
fn declarations(m: &PublicManifest) -> Result<(), String> {
    let mut paths = BTreeSet::new();
    let mut repeated = false;
    for source in &m.source_files {
        repeated |= !paths.insert(reference(source, SOURCE_LIMIT)?);
    }
    if repeated {
        return Err("Neural source references contain a duplicate path.".into());
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
    for channel in &m.channels {
        for item in [&channel.capture, &channel.payload, &channel.markers] {
            reference(item, JSON_LIMIT as u64)?;
        }
    }
    Ok(())
}

/// Read the closed public carrier as declarations only, without trusted source admission.
///
/// The final manifest component must be a regular Linux file, at most 65,536 bytes.
/// The bytes are decoded with the bounded run JSON rules: nesting at most 64 deep,
/// integers within 64 bits, no repeated member name and no unpaired surrogate. The
/// document must then satisfy the committed closed schema with integer encodings
/// only, so schema objects cannot be replaced with positional arrays. Referenced
/// source, policy, trace and runtime files are never opened. A successful result is
/// not a complete bound run, numerical verdict, runtime selection or source-owner
/// adoption.
///
/// # Errors
///
/// Returns the refusal Python's `load_neural_manifest` gives for the same path and
/// bytes: malformed bytes, unsupported file kinds, excessive allocations, or
/// declarations contradicting the public schema and portable path laws.
pub fn load_neural_manifest(path: &Path) -> Result<Value, String> {
    let (_, document, _) = acquire(path)?;
    Ok(document)
}

/// Acquire one root snapshot and validate its entire closed typed declaration.
pub(crate) fn acquire(path: &Path) -> Result<(Vec<u8>, Value, PublicManifest), String> {
    let raw = root_bytes(path)?;
    if digest(SCHEMA_TEXT.as_bytes()) != SCHEMA_SHA256 {
        return Err("Installed neural manifest schema differs from its admitted body.".into());
    }
    let (object, _) = decode_object(&raw, "neural manifest").map_err(|_| NOT_JSON.to_owned())?;
    let document = Value::Object(object);
    if !SCHEMA.locations(&document).is_empty() || has_decimal(&document) {
        return Err(NOT_CLOSED.into());
    }
    // Every schema-valid integer-only document fits the typed carrier: each
    // member's type and range is closed by the schema, so this refusal is a
    // guard against a schema edit, never a second wording, and no input reaches it.
    let typed = serde_json::from_value::<PublicManifest>(document.clone());
    let manifest = typed.map_err(|_| NOT_CLOSED.to_owned())?;
    exact_identity(&manifest)?;
    declarations(&manifest)?;
    Ok((raw, document, manifest))
}
