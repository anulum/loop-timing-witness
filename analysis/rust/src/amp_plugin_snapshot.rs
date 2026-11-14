// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — captured plugin build receipts and source snapshots

//! Check a capture's plugin build receipt and source snapshot as the Python
//! module `amp_plugin_snapshot` does.
//!
//! [`validate_plugin_snapshot`] decodes the captured `plugin_build.json`,
//! requires it to name the executed plugin library and the observed plant, and
//! its source index to equal the index Python assigns to the receipt's
//! dependencies; then it checks every copy under `plugin_sources`, in the
//! index document's order. Every refusal and read error is Python's.
//!
//! [`validate_plugin_snapshot`]: crate::amp_plugin_snapshot::validate_plugin_snapshot

use crate::amp_failure::AmpFailure;
use crate::amp_files::{file_bytes, load_document};
use crate::amp_plugin_receipt::decode_plugin_receipt;
use crate::amp_snapshot_index::{snapshot_index, verify_copies};
use crate::control_paths::pure;
use crate::control_receipts::python_equal;
use serde_json::Value;
use std::path::Path;

/// Check the captured plugin receipt and sources of a completed capture.
///
/// `plugin_digest` is the digest of the executed plugin library that the
/// capture receipt records, and `thermal` the plant the running RTL reported.
///
/// # Errors
///
/// [`AmpFailure::Os`] with Python's text when the receipt, the index or a copy
/// cannot be read; [`AmpFailure::Refused`] with Python's text when the receipt
/// or the index is refused, the receipt names another library or plant, the
/// index disagrees, or a copy resolves outside `output` or holds other bytes.
pub fn validate_plugin_snapshot(
    output: &Path,
    plugin_digest: &str,
    thermal: bool,
) -> Result<(), AmpFailure> {
    let data = decode_plugin_receipt(&file_bytes(&pure(&output.join("plugin_build.json")))?)?;
    let (index, orders) = load_document(output, "plugin_source_index.json")?;
    let hashes = data["dependencies"]
        .as_object()
        .expect("schema-checked dependencies");
    let expected = snapshot_index(hashes, "plugin_sources", "source");
    // Python's `bool` of the schema-checked plant, 0 or 1 or their float spellings.
    let plant = data["thermal"].as_f64().is_some_and(|value| value != 0.0);
    if data["plugin_sha256"] != plugin_digest
        || plant != thermal
        || !python_equal(&Value::Object(index.clone()), &expected)
    {
        let text = "AMP plugin snapshot library, plant or source index disagrees";
        return Err(AmpFailure::Refused(text.into()));
    }
    let changed = "AMP captured plugin source bytes or paths changed";
    verify_copies(output, &index, &orders, changed)
}

#[cfg(test)]
#[path = "../tests/unit/amp_plugin_receipts.rs"]
mod tests;
