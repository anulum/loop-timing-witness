// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — captured firmware preprocessing dependency snapshots

//! Check a captured firmware dependency snapshot and the preprocessing record
//! count as the Python module `amp_image_dependencies` does.
//!
//! - [`image_dependency_record_count`] reads the kernel backend of a
//!   preparation receipt: five records for the C kernel, four for the Rust
//!   kernel.
//! - [`validate_image_dependency_snapshot`] reads
//!   `compiler_source_index.json`, requires it to equal the index Python
//!   assigns to the preparation's compiler dependency identities, and checks
//!   every copy under `compiler_sources` in the index document's order.
//!
//! [`image_dependency_record_count`]: crate::amp_image_dependencies::image_dependency_record_count
//! [`validate_image_dependency_snapshot`]: crate::amp_image_dependencies::validate_image_dependency_snapshot

use crate::amp_failure::AmpFailure;
use crate::amp_files::load_document;
use crate::amp_snapshot_index::{snapshot_index, verify_copies};
use crate::control_receipts::python_equal;
use crate::control_schema::Schema;
use serde_json::{Map, Value};
use std::path::Path;
use std::sync::LazyLock;

/// Preprocessing records of an image built with the C kernel.
const RECORD_COUNT: usize = 5;

/// Python's `HASH_SCHEMA` of compiler dependency identities, committed beside the crate.
static SCHEMA: LazyLock<Schema> = LazyLock::new(|| {
    Schema::load(include_str!(
        "../amp-firmware-dependency-hashes.schema.json"
    ))
    .expect("committed schema")
});

/// Tell how many preprocessing records the preparation's kernel backend has.
///
/// # Errors
///
/// [`AmpFailure::Refused`] with Python's text when a declared backend is not
/// `"rust"` or its inputs do not name the Rust preparation.
pub fn image_dependency_record_count(data: &Map<String, Value>) -> Result<usize, AmpFailure> {
    let Some(backend) = data.get("kernel_backend") else {
        return Ok(RECORD_COUNT);
    };
    let inputs = data.get("inputs").and_then(Value::as_object);
    let declared = inputs.is_some_and(|inputs| inputs.contains_key("rust_preparation.json"));
    if *backend != "rust" || !declared {
        let text = "AMP original arithmetic backend or Rust preparation identity is invalid";
        return Err(AmpFailure::Refused(text.into()));
    }
    Ok(RECORD_COUNT - 1)
}

/// Check the captured firmware preprocessing sources of an image directory.
///
/// `identities` are the preparation's `compiler_dependencies`, or JSON null
/// when it has none.
///
/// # Errors
///
/// [`AmpFailure::Os`] with Python's text when the index or a copy cannot be
/// read; [`AmpFailure::Refused`] with Python's text when the index is not a
/// bounded JSON object, the identities are invalid or name a `..` part, the
/// index disagrees with them, or a copy resolves outside `directory` or holds
/// other bytes.
pub fn validate_image_dependency_snapshot(
    directory: &Path,
    identities: &Value,
) -> Result<(), AmpFailure> {
    let (index, orders) = load_document(directory, "compiler_source_index.json")?;
    if !SCHEMA.locations(identities).is_empty() {
        let text = "AMP original firmware dependency identities are invalid";
        return Err(AmpFailure::Refused(text.into()));
    }
    let hashes = identities.as_object().expect("schema-checked identities");
    if hashes
        .keys()
        .any(|name| name.split('/').any(|part| part == ".."))
    {
        let text = "AMP original firmware dependency paths escape their source root";
        return Err(AmpFailure::Refused(text.into()));
    }
    let expected = snapshot_index(hashes, "compiler_sources", "source");
    if !python_equal(&Value::Object(index.clone()), &expected) {
        let text = "AMP original firmware dependency snapshot index disagrees";
        return Err(AmpFailure::Refused(text.into()));
    }
    let changed = "AMP captured firmware dependency bytes or paths changed";
    verify_copies(directory, &index, &orders, changed)
}
