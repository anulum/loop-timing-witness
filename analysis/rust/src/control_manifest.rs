// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — CONTROL and COMPUTE run loading with hash-bound inputs

//! Load one CONTROL or COMPUTE run and bind its input bytes to the manifest hashes.
//!
//! The steps, their order and every refusal text are those of the Python
//! `run_manifest.load_run`: the bounded JSON object, the run schema, the UTC
//! timestamp, the hash-bound measurement domain with its schema, cross-field
//! rules and 16-byte wire layout, the run's agreement with the domain, the
//! source and hardware artefacts, the optional receipts and the declared files
//! in document order. A file is interpreted only after its complete bytes
//! match the declared digest.

use crate::control_domain::semantic_findings;
use crate::control_json::{Orders, decode_object};
use crate::control_number::Num;
use crate::control_schema::Schema;
use crate::control_text::{os_error, os_error_without_path, python_display};
use crate::files::digest;
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::cmp::Ordering;
use std::collections::BTreeMap;
use std::io::Read;
use std::path::{Component, Path, PathBuf};
use std::sync::LazyLock;

/// The committed run manifest schema.
static RUN_SCHEMA: LazyLock<Schema> = LazyLock::new(|| {
    Schema::load(include_str!("../run-manifest.schema.json")).expect("committed schema")
});
/// The committed measurement-domain schema.
static DOMAIN_SCHEMA: LazyLock<Schema> = LazyLock::new(|| {
    Schema::load(include_str!("../measurement-domain.schema.json")).expect("committed schema")
});
/// The 16-byte host wire layout: name and type of each field, contiguous from offset zero.
const WIRE_FIELDS: [(&str, &str); 5] = [
    ("event_type", "u8"),
    ("reserved_byte", "u8"),
    ("reserved_word", "u16"),
    ("cycle", "u32"),
    ("timebase_ticks", "u64"),
];
/// Hardware artefacts every board declaration binds.
const HARDWARE: [&str; 4] = ["bitstream", "firmware", "linux_image", "controller_binary"];
/// Optional receipts, read before the declared files.
const RECEIPTS: [&str; 3] = ["native_metadata", "host_load", "amp_capture"];

/// Why a run cannot be loaded, as Python's `load_run` raises it.
///
/// A repeat campaign keeps a run its contract refuses as a refused repeat, but
/// refuses the whole campaign when a bound file cannot be opened or read.
#[derive(Debug)]
pub(crate) enum Failure {
    /// Python's `OSError`: a manifest or bound file cannot be opened or read.
    Os(String),
    /// Python's `ValueError`: the run's contract refuses it.
    Refused(String),
}

impl From<String> for Failure {
    /// A refusal of the run's contract.
    fn from(text: String) -> Self {
        Self::Refused(text)
    }
}

impl Failure {
    /// The text Python's exception carries.
    pub(crate) fn text(self) -> String {
        match self {
            Self::Os(text) | Self::Refused(text) => text,
        }
    }
}

/// A validated run with its hash-bound input bytes.
#[derive(Debug)]
pub(crate) struct ControlRun {
    /// The schema-valid run manifest.
    pub(crate) manifest: Map<String, Value>,
    /// The valid measurement-domain contract.
    pub(crate) domain: Value,
    /// Complete input bytes by name; absent optional inputs have no entry.
    pub(crate) files: BTreeMap<String, Vec<u8>>,
    /// The resolved manifest directory.
    pub(crate) directory: PathBuf,
}

/// Load a run from its manifest path, or from root bytes already read for it.
pub(crate) fn load(path: &Path, root: Option<&[u8]>) -> Result<ControlRun, String> {
    load_classified(path, root).map_err(Failure::text)
}

/// Load a run as [`load`] does, telling an unreadable file from a refused run.
pub(crate) fn load_classified(path: &Path, root: Option<&[u8]>) -> Result<ControlRun, Failure> {
    let raw = match root {
        Some(bytes) => bytes.to_vec(),
        None => read_file(path)?,
    };
    let (manifest, orders) = decode_object(&raw, &python_display(path))?;
    let document = Value::Object(manifest.clone());
    if let Some(location) = RUN_SCHEMA.locations(&document).first() {
        return Err(
            format!("run manifest {location}: does not satisfy the run manifest schema").into(),
        );
    }
    if !utc_timestamp(text(&document["started_utc"])) {
        return Err("started_utc must be an RFC 3339 date-time in UTC"
            .to_owned()
            .into());
    }
    let directory = resolve(path)
        .parent()
        .map(Path::to_path_buf)
        .unwrap_or_default();
    let item = &document["measurement_domain"];
    let domain = load_domain(&read_bound(&directory, item)?, text(&item["path"]))?;
    agree(&document, &domain)?;
    for item in items(&document["source"]["files"]) {
        verify_artifact(&directory, item)?;
    }
    if !document["hardware_artifacts"].is_null() {
        for name in HARDWARE {
            verify_artifact(&directory, &document["hardware_artifacts"][name])?;
        }
    }
    let mut files = BTreeMap::new();
    for name in RECEIPTS {
        if let Some(item) = document.get(name) {
            files.insert(name.to_owned(), read_bound(&directory, item)?);
        }
    }
    for name in declared_files(&orders) {
        let item = &document["files"][name.as_str()];
        if !item.is_null() {
            let content = read_bound(&directory, item)?;
            files.insert(name, content);
        }
    }
    Ok(ControlRun {
        manifest,
        domain,
        files,
        directory,
    })
}

/// The members of the declared `files` object in document order.
fn declared_files(orders: &Orders) -> Vec<String> {
    orders[&vec!["files".to_owned()]].clone()
}

/// Resolve the manifest path as Python's non-strict `Path.resolve` does.
///
/// An existing file resolves completely; a missing file keeps its name under
/// its resolved directory, as when root bytes were read before it vanished.
pub(crate) fn resolve(path: &Path) -> PathBuf {
    std::fs::canonicalize(path).unwrap_or_else(|_| {
        let absolute = std::path::absolute(path).unwrap_or_default();
        let parent = absolute.parent().map(Path::to_path_buf).unwrap_or_default();
        std::fs::canonicalize(&parent)
            .unwrap_or(parent)
            .join(absolute.file_name().unwrap_or_default())
    })
}

/// The text of a schema-checked string member.
fn text(value: &Value) -> &str {
    value.as_str().expect("schema-checked string")
}

/// The items of a schema-checked array member.
fn items(value: &Value) -> &[Value] {
    value.as_array().expect("schema-checked array")
}

/// Tell whether a text is one RFC 3339 date-time with a zero UTC offset.
///
/// The rule is Python's: `YYYY-MM-DD`, `T` or `t`, `HH:MM:SS`, an optional
/// fraction of any length, then `Z`, `z`, `+00:00` or `-00:00`, naming a real
/// instant from year 1 without a leap second.
pub(crate) fn utc_timestamp(value: &str) -> bool {
    let bytes = value.as_bytes();
    let digit = |index: usize| bytes.get(index).copied().filter(u8::is_ascii_digit);
    let number = |start: usize, length: usize| -> Option<u32> {
        (start..start + length).try_fold(0, |total, index| {
            Some(total * 10 + u32::from(digit(index)? - b'0'))
        })
    };
    let shape = bytes.len() >= 20
        && bytes[4] == b'-'
        && bytes[7] == b'-'
        && matches!(bytes[10], b'T' | b't')
        && bytes[13] == b':'
        && bytes[16] == b':';
    if !shape {
        return false;
    }
    let mut end = 19;
    if bytes[end] == b'.' {
        let fraction = bytes[end + 1..]
            .iter()
            .take_while(|byte| byte.is_ascii_digit())
            .count();
        if fraction == 0 {
            return false;
        }
        end += 1 + fraction;
    }
    let zone = &bytes[end..];
    if !matches!(zone, b"Z" | b"z" | b"+00:00" | b"-00:00") {
        return false;
    }
    let fields = [
        number(0, 4),
        number(5, 2),
        number(8, 2),
        number(11, 2),
        number(14, 2),
        number(17, 2),
    ];
    let [
        Some(year),
        Some(month),
        Some(day),
        Some(hour),
        Some(minute),
        Some(second),
    ] = fields
    else {
        return false;
    };
    let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
    let days = match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 if leap => 29,
        2 => 28,
        _ => 0,
    };
    year >= 1 && (1..=days).contains(&day) && hour < 24 && minute < 60 && second < 60
}

/// Load and validate the run-bound measurement-domain contract.
pub(crate) fn load_domain(raw: &[u8], source: &str) -> Result<Value, String> {
    let (domain, _) = decode_object(raw, source)?;
    let domain = Value::Object(domain);
    let mut findings: Vec<String> = DOMAIN_SCHEMA
        .locations(&domain)
        .iter()
        .map(|location| {
            format!("schema: {location}: does not satisfy the measurement-domain schema")
        })
        .collect();
    if findings.is_empty() {
        findings = semantic_findings(&domain);
    }
    if !findings.is_empty() {
        return Err(format!(
            "measurement domain invalid: {}",
            findings.join("; ")
        ));
    }
    let record = &domain["design_contracts"]["event_record"];
    let fields = items(&record["fields"]);
    // The cross-field rules already require contiguous offsets from zero, so
    // matching names and types in order fix every offset of the wire layout.
    let wire = Num::of(&record["record_size_bytes"]).same(Num::Int(16))
        && fields.len() == WIRE_FIELDS.len()
        && fields.iter().zip(WIRE_FIELDS).all(|(field, (name, kind))| {
            text(&field["name"]) == name && text(&field["type"]) == kind
        });
    if !wire {
        return Err(
            "measurement domain event record differs from the 16-byte host wire layout".to_owned(),
        );
    }
    Ok(domain)
}

/// Refuse run fields that disagree with the measurement-domain contract.
fn agree(manifest: &Value, domain: &Value) -> Result<(), String> {
    let contracts = &domain["design_contracts"];
    let placement = text(&manifest["placement"]);
    if !items(&contracts["controller_placements"])
        .iter()
        .any(|item| text(&item["identifier"]) == placement)
    {
        return Err("placement is not declared in measurement-domain.json".to_owned());
    }
    let rate = &contracts["event_profiles"][text(&manifest["profile"])]["sample_rate_hz"];
    if !rate.is_null() {
        let clock = Num::of(&contracts["timebase"]["clock_hz"]);
        let period = &manifest["sample_period_ticks"];
        let inside = !period.is_null()
            && Num::of(&rate["minimum"])
                .mul(Num::of(period))
                .compare(clock)
                != Ordering::Greater
            && clock.compare(Num::of(&rate["maximum"]).mul(Num::of(period))) != Ordering::Greater;
        if !inside {
            return Err(
                "sample_period_ticks falls outside the declared control rate range".to_owned(),
            );
        }
    }
    let cycles = Num::of(&manifest["cycle_count"]);
    if Num::of(&manifest["warmup_cycles"]).compare(cycles) != Ordering::Less {
        return Err("warmup_cycles must leave at least one analysed cycle".to_owned());
    }
    for fault in items(&manifest["fault_schedule"]) {
        if Num::of(&fault["cycle"]).compare(cycles) != Ordering::Less {
            return Err("fault schedule cycle is outside the run".to_owned());
        }
        if text(&fault["kind"]) != "delay" && !Num::of(&fault["delay_periods"]).same(Num::Int(0)) {
            return Err("delay_periods is nonzero for a non-delay fault".to_owned());
        }
    }
    let overflow = Num::of(&manifest["instrument"]["fifo_overflow_count"]);
    if text(&manifest["source"]["kind"]) == "board" && !overflow.same(Num::Int(0)) {
        return Err("board run with FIFO overflow is invalid measurement evidence".to_owned());
    }
    Ok(())
}

/// Resolve one declared path without leaving the run directory.
///
/// The path names what Python's `Path` makes of it: repeated separators, `.`
/// parts and a final separator are dropped before it is resolved.
fn bound_path(directory: &Path, item: &Value) -> Result<PathBuf, String> {
    let declared = text(&item["path"]);
    let relative = Path::new(declared);
    // The schema pattern starts every path with a letter or digit, so it is never absolute.
    if relative
        .components()
        .any(|part| part == Component::ParentDir)
    {
        return Err(format!(
            "input path must stay within the run directory: {declared}"
        ));
    }
    let parts: PathBuf = relative.components().collect();
    std::fs::canonicalize(directory.join(parts))
        .ok()
        .filter(|path| path.starts_with(directory) && path.is_file())
        .ok_or_else(|| format!("input is not a regular file inside the run directory: {declared}"))
}

/// Read a whole file as Python's `Path.read_bytes` reports failures: an
/// opening error names the path, a reading error does not. Python's `open`
/// refuses a directory once it is open, naming the path, as here.
pub(crate) fn read_file(path: &Path) -> Result<Vec<u8>, Failure> {
    let mut stream =
        std::fs::File::open(path).map_err(|error| Failure::Os(os_error(&error, path)))?;
    if stream.metadata().is_ok_and(|status| status.is_dir()) {
        let error = std::io::Error::from_raw_os_error(rustix::io::Errno::ISDIR.raw_os_error());
        return Err(Failure::Os(os_error(&error, path)));
    }
    let mut content = Vec::new();
    stream
        .read_to_end(&mut content)
        .map_err(|error| Failure::Os(os_error_without_path(&error)))?;
    Ok(content)
}

/// Read one bound file completely and verify its digest.
fn read_bound(directory: &Path, item: &Value) -> Result<Vec<u8>, Failure> {
    let path = bound_path(directory, item)?;
    let content = read_file(&path)?;
    if digest(&content) != text(&item["sha256"]) {
        return Err(format!("input SHA-256 mismatch: {}", text(&item["path"])).into());
    }
    Ok(content)
}

/// Stream-check one source or hardware artefact in 1 MiB blocks.
fn verify_artifact(directory: &Path, item: &Value) -> Result<(), Failure> {
    let path = bound_path(directory, item)?;
    let mut stream =
        std::fs::File::open(&path).map_err(|error| Failure::Os(os_error(&error, &path)))?;
    let mut hasher = Sha256::new();
    let mut block = vec![0; 1 << 20];
    loop {
        let count = stream
            .read(&mut block)
            .map_err(|error| Failure::Os(os_error_without_path(&error)))?;
        if count == 0 {
            break;
        }
        hasher.update(&block[..count]);
    }
    if crate::files::hex(&hasher.finalize()) != text(&item["sha256"]) {
        return Err(format!("artefact SHA-256 mismatch: {}", text(&item["path"])).into());
    }
    Ok(())
}

#[cfg(test)]
#[path = "../tests/unit/control_manifest.rs"]
mod tests;
