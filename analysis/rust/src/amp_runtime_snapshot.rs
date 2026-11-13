// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — captured runtime library snapshots

//! Check a captured runtime library snapshot as the Python module
//! `amp_runtime_snapshot` does.
//!
//! [`validate_runtime_snapshot`] reads `runtime_source_index.json`, requires
//! it to equal the index Python assigns to the original library identities,
//! and checks every copy under `runtime_sources` in the index document's
//! order. Every refusal and read error is Python's, met in Python's order.
//!
//! [`validate_runtime_snapshot`]: crate::amp_runtime_snapshot::validate_runtime_snapshot

use crate::amp_failure::AmpFailure;
use crate::amp_files::load_document;
use crate::amp_snapshot_index::{snapshot_index, verify_copies};
use crate::control_receipts::python_equal;
use crate::control_schema::Schema;
use serde_json::Value;
use std::path::Path;
use std::sync::LazyLock;

/// Python's `HASH_SCHEMA` of runtime library identities, committed beside the crate.
static SCHEMA: LazyLock<Schema> = LazyLock::new(|| {
    Schema::load(include_str!("../amp-runtime-hashes.schema.json")).expect("committed schema")
});

/// Check the captured runtime libraries of an image or capture directory.
///
/// `identities` are the original absolute library paths and digests that the
/// retained receipt records.
///
/// # Errors
///
/// [`AmpFailure::Os`] with Python's text when the index or a copy cannot be
/// read; [`AmpFailure::Refused`] with Python's text when the index is not a
/// bounded JSON object, the identities are invalid, the index disagrees with
/// them, or a copy resolves outside `output` or holds other bytes.
pub fn validate_runtime_snapshot(output: &Path, identities: &Value) -> Result<(), AmpFailure> {
    let (index, orders) = load_document(output, "runtime_source_index.json")?;
    if !SCHEMA.locations(identities).is_empty() {
        let text = "AMP runtime library identities are invalid";
        return Err(AmpFailure::Refused(text.into()));
    }
    let hashes = identities.as_object().expect("schema-checked identities");
    let expected = snapshot_index(hashes, "runtime_sources", "library");
    if !python_equal(&Value::Object(index.clone()), &expected) {
        let text = "AMP runtime library snapshot index disagrees with original identities";
        return Err(AmpFailure::Refused(text.into()));
    }
    let changed = "AMP captured runtime library bytes or paths changed";
    verify_copies(output, &index, &orders, changed)
}
