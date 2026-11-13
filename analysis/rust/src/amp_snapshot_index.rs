// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — indexed snapshot folders of AMP images and captures

//! Check an indexed snapshot folder as the Python snapshot modules do.
//!
//! An image or capture keeps copies of original files under
//! `<folder>/<NNNN>/<leaf>`, numbered in the sorted order of their original
//! names, and an index document maps each name to its copy and digest.

use crate::amp_failure::AmpFailure;
use crate::amp_files::file_digest;
use crate::control_json::Orders;
use crate::control_paths::{pure, realpath};
use serde_json::{Map, Value, json};
use std::path::Path;

/// The index Python assigns to checked identities: each original name, in
/// sorted order, mapped to `<folder>/<NNNN>/<leaf>` and its digest.
pub(crate) fn snapshot_index(hashes: &Map<String, Value>, folder: &str, leaf: &str) -> Value {
    let members = hashes.iter().enumerate().map(|(number, (name, sha256))| {
        let path = format!("{folder}/{number:04}/{leaf}");
        (name.clone(), json!({"path": path, "sha256": sha256}))
    });
    Value::Object(members.collect())
}

/// Check every copy an accepted index names, in the index document's order:
/// each must resolve inside `output` and hold its indexed digest.
pub(crate) fn verify_copies(
    output: &Path,
    index: &Map<String, Value>,
    orders: &Orders,
    changed: &str,
) -> Result<(), AmpFailure> {
    let root = realpath(output).map_err(AmpFailure::Os)?;
    for name in &orders[&Vec::new()] {
        let item = &index[name];
        let path = pure(&output.join(item["path"].as_str().expect("accepted index path")));
        if !realpath(&path).map_err(AmpFailure::Os)?.starts_with(&root)
            || item["sha256"].as_str() != Some(file_digest(&path)?.as_str())
        {
            return Err(AmpFailure::Refused(changed.into()));
        }
    }
    Ok(())
}

#[cfg(test)]
#[path = "../tests/unit/amp_snapshots.rs"]
mod tests;
