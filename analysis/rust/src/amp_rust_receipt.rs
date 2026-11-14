// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — captured Rust kernel preparations and compiled outputs

//! Check an AMP image's Rust kernel as the Python module `amp_rust_receipt`
//! does.
//!
//! [`validate_rust_image_receipt`] follows the arithmetic backend that the
//! image's preparation declares. For the Rust kernel it reads the captured
//! `rust_preparation.json` and checks it against everything captured beside
//! it: the toolchain identity, the literal compiler vectors, the runtime
//! library snapshot, the crate sources, the target library snapshot and the
//! metadata dependency records; then it checks the compiled dependency
//! records, the static archive and the controller library against the
//! image's receipt. Every refusal and read error is Python's, met in Python's
//! order.
//!
//! [`validate_rust_image_receipt`]: crate::amp_rust_receipt::validate_rust_image_receipt

use crate::amp_failure::AmpFailure;
use crate::amp_files::{file_bytes, file_digest, load_document};
use crate::amp_runtime_snapshot::validate_runtime_snapshot;
use crate::amp_rust_dependencies::rust_dependency_hashes;
use crate::amp_rust_vectors::{ADAPTER, CORE, LIBRARY, rust_vectors};
use crate::control_paths::{parent_and_name, pure, realpath};
use crate::control_receipts::python_equal;
use crate::control_schema::Schema;
use serde_json::{Map, Value, json};
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};
use std::sync::LazyLock;

/// Python's `TOOLCHAIN` schema of a Rust preparation, committed beside the crate.
static SCHEMA: LazyLock<Schema> = LazyLock::new(|| {
    Schema::load(include_str!("../amp-rust-toolchain.schema.json")).expect("committed schema")
});

/// A refusal with Python's text.
fn refused<T>(text: &str) -> Result<T, AmpFailure> {
    Err(AmpFailure::Refused(text.into()))
}

/// A member of a decoded object, or JSON null as Python's `dict.get` gives `None`.
fn member<'a>(object: &'a Map<String, Value>, name: &str) -> &'a Value {
    object.get(name).unwrap_or(&Value::Null)
}

/// The digests of files under `directory`, keyed by their names there.
fn digests(directory: &Path, names: &[&str]) -> Result<Map<String, Value>, AmpFailure> {
    let mut found = Map::new();
    for name in names {
        let digest = file_digest(&pure(&directory.join(name)))?;
        found.insert((*name).to_owned(), Value::String(digest));
    }
    Ok(found)
}

/// Python 3.15's `PurePath(name).stem` and `.suffix`: the suffix starts at the
/// last dot after any leading dots, and a stem keeps at least one character
/// that is not a dot.
fn stem_and_suffix(name: &str) -> (&str, &str) {
    let (_, last) = parent_and_name(Path::new(name));
    let last = last.to_str().expect("UTF-8 decoded name");
    let stem = last
        .rfind('.')
        .map(|dot| &last[..dot])
        .filter(|stem| !stem.trim_start_matches('.').is_empty())
        .unwrap_or(last);
    let bare = last.trim_start_matches('.');
    (stem, bare.rfind('.').map_or("", |dot| &bare[dot..]))
}

/// Python's `_admit_sources`: the eight crate sources must resolve inside the
/// captured `source` tree and hold the preparation's digests.
fn admit_sources(
    directory: &Path,
    data: &Map<String, Value>,
) -> Result<Map<String, Value>, AmpFailure> {
    let names: Vec<String> = [CORE, ADAPTER]
        .iter()
        .flat_map(|component| {
            ["Cargo.toml", "Cargo.lock", "README.md", "src/lib.rs"]
                .map(|name| format!("source/{component}/{name}"))
        })
        .collect();
    let snapshot = realpath(directory).map_err(AmpFailure::Os)?.join("source");
    for name in &names {
        let resolved = realpath(&pure(&directory.join(name))).map_err(AmpFailure::Os)?;
        if !resolved.starts_with(&snapshot) {
            return refused("Rust captured source paths escape original preparation");
        }
    }
    let sources = digests(
        directory,
        &names.iter().map(String::as_str).collect::<Vec<_>>(),
    )?;
    if !python_equal(member(data, "sources"), &Value::Object(sources.clone())) {
        return refused("Rust captured original source bytes changed");
    }
    Ok(sources)
}

/// Python's `_admit_target_libraries`: matching archives and metadata, the
/// core and builtins libraries among them, an index in name order, and every
/// captured copy inside `directory` with its digest.
fn admit_target_libraries(
    directory: &Path,
    data: &Map<String, Value>,
    names: &Map<String, Value>,
) -> Result<(), AmpFailure> {
    let root = realpath(directory).map_err(AmpFailure::Os)?;
    let mut archives = BTreeSet::new();
    let mut metadata = BTreeSet::new();
    let mut other = false;
    for (stem, suffix) in names.keys().map(|name| stem_and_suffix(name)) {
        match suffix {
            ".rlib" => archives.insert(stem),
            ".rmeta" => metadata.insert(stem),
            _ => {
                other = true;
                false
            }
        };
    }
    if archives != metadata
        || !archives.iter().any(|stem| stem.starts_with("libcore-"))
        || !archives
            .iter()
            .any(|stem| stem.starts_with("libcompiler_builtins-"))
        || other
    {
        return refused("Rust original target archives and metadata are incomplete");
    }
    let index: Map<String, Value> = names
        .iter()
        .enumerate()
        .map(|(number, (name, digest))| {
            let (_, suffix) = stem_and_suffix(name);
            let path = format!("rust_target_libraries/{number:04}{suffix}");
            (name.clone(), json!({"path": path, "sha256": digest}))
        })
        .collect();
    if !python_equal(member(data, "target_index"), &Value::Object(index.clone())) {
        return refused("Rust original target library snapshot index disagrees");
    }
    for item in index.values() {
        let path = pure(&directory.join(item["path"].as_str().expect("built index path")));
        if !realpath(&path).map_err(AmpFailure::Os)?.starts_with(&root)
            || item["sha256"].as_str() != Some(file_digest(&path)?.as_str())
        {
            return refused("Rust captured target library bytes or paths changed");
        }
    }
    Ok(())
}

/// Python's `rust_dependency_hashes` result as the JSON object it is compared with.
fn closure(records: &[PathBuf], directory: &Path) -> Result<Value, AmpFailure> {
    let found: BTreeMap<String, String> = rust_dependency_hashes(records, directory)?;
    Ok(Value::Object(
        found
            .into_iter()
            .map(|(name, digest)| (name, Value::String(digest)))
            .collect(),
    ))
}

/// The two dependency records rustc wrote into one output folder.
fn records(directory: &Path, folder: &str) -> Vec<PathBuf> {
    ["core.d", "adapter.d"]
        .map(|name| pure(&directory.join(folder).join(name)))
        .to_vec()
}

/// Python's `validate_rust_preparation_snapshot`.
fn validate_preparation(directory: &Path, data: &Map<String, Value>) -> Result<(), AmpFailure> {
    let identity = member(data, "toolchain");
    let schema = json!("loop-timing-witness.rust-preparation.v1");
    if !python_equal(member(data, "schema"), &schema) || !SCHEMA.locations(identity).is_empty() {
        return refused("Rust captured preparation or original toolchain identity is invalid");
    }
    let compiler = identity["compiler"]["path"]
        .as_str()
        .expect("schema-checked path");
    for (field, metadata) in [("metadata_commands", true), ("compile_commands", false)] {
        if !python_equal(member(data, field), &rust_vectors(compiler, metadata)) {
            return refused("Rust captured original compiler vectors disagree");
        }
    }
    let runtime = &identity["runtime_libraries"];
    validate_runtime_snapshot(&pure(&directory.join("rust_runtime")), runtime)?;
    let sources = admit_sources(directory, data)?;
    let names = identity["target_libraries"]
        .as_object()
        .expect("schema-checked map");
    admit_target_libraries(directory, data, names)?;
    let metadata = records(directory, "rust_metadata");
    let hashes = digests(
        directory,
        &["rust_metadata/core.d", "rust_metadata/adapter.d"],
    )?;
    if !python_equal(member(data, "dependency_records"), &Value::Object(hashes)) {
        return refused("Rust captured original metadata records changed");
    }
    let actual = closure(&metadata, directory)?;
    let expected: Map<String, Value> = sources
        .into_iter()
        .filter(|(name, _)| name.ends_with("/src/lib.rs"))
        .collect();
    if !python_equal(member(data, "dependencies"), &actual)
        || !python_equal(&actual, &Value::Object(expected))
    {
        return refused("Rust captured original metadata source closure changed");
    }
    Ok(())
}

/// Check an image's Rust kernel against its preparation and receipt.
///
/// `image` is the decoded `image.json` and `preparation` the decoded
/// `preparation.json` of the image in `directory`. An image whose preparation
/// declares no arithmetic backend is the C kernel and must not carry a Rust
/// declaration or archive receipt.
///
/// # Errors
///
/// [`AmpFailure::Os`] with Python's text when a captured file cannot be read;
/// [`AmpFailure::Refused`] with Python's text when a declaration, the captured
/// Rust preparation, a snapshot, a dependency record or a compiled output
/// disagrees.
pub fn validate_rust_image_receipt(
    directory: &Path,
    image: &Map<String, Value>,
    preparation: &Map<String, Value>,
) -> Result<(), AmpFailure> {
    let Some(backend) = preparation.get("kernel_backend") else {
        if image.contains_key("kernel_backend") || image.contains_key("rust_kernel") {
            return refused("Rust receipt contradicts the original C arithmetic selection");
        }
        return Ok(());
    };
    if *backend != "rust" || *member(image, "kernel_backend") != "rust" {
        return refused("Rust original arithmetic backend declarations disagree");
    }
    let (data, _) = load_document(directory, "rust_preparation.json")?;
    validate_preparation(directory, &data)?;
    let compiled = records(directory, "objects/rust");
    if !python_equal(&closure(&compiled, directory)?, &data["dependencies"]) {
        return refused("Rust captured final source closure differs from original metadata");
    }
    if !file_bytes(&pure(&directory.join(LIBRARY)))?.starts_with(b"!<arch>\n") {
        return refused("Rust captured compiler output is not a static archive");
    }
    let outputs = [
        "objects/rust/core.d",
        "objects/rust/adapter.d",
        LIBRARY,
        "objects/rust/libwitness_controller.rlib",
    ];
    let expected = json!({"preparation": data, "outputs": digests(directory, &outputs)?});
    if !python_equal(member(image, "rust_kernel"), &expected) {
        return refused("Rust original archive receipt or actual compiler output bytes changed");
    }
    Ok(())
}

#[cfg(test)]
#[path = "../tests/unit/amp_rust_receipt.rs"]
mod tests;
