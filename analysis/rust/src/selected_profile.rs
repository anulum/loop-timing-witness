// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — exact selected bounded simulation profile

//! Bind the reviewed ec123 source freeze to the SC-selected finite installation.

use crate::files::{decode, digest, read_regular};
use crate::public_image::{ImageExecutor, NeuralExecutor};
use crate::public_runtime::{Installation, InstalledFile};
use serde::Deserialize;
use std::path::PathBuf;

/// Consumer-owned installation aliases, never interpreted from an acquisition.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Settings {
    bindings: Vec<Mapping>,
    import_roots: Vec<PathBuf>,
}

/// One exact portable-to-physical runtime alias from the reviewed installation.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Mapping {
    name: String,
    actual_path: PathBuf,
    sha256: String,
    byte_length: u64,
}

/// Operator variable selecting the reviewed host installation descriptor file.
pub(crate) const INSTALLATION_VARIABLE: &str = "LOOP_TIMING_WITNESS_CHECKER_INSTALLATION";

/// Operator variable selecting the reviewed image executor binding file.
pub(crate) const IMAGE_BINDING_VARIABLE: &str = "LOOP_TIMING_WITNESS_CHECKER_IMAGE_BINDING";

/// Read one host-specific descriptor that the operator selects; only its digest is packaged.
fn operator_file(variable: &str, expected: &str, missing: &str) -> Result<Vec<u8>, String> {
    let selected = std::env::var_os(variable)
        .map(PathBuf::from)
        .filter(|path| path.is_absolute())
        .ok_or_else(|| missing.to_owned())?;
    let (Some(parent), Some(name)) = (
        selected.parent(),
        selected.file_name().and_then(|name| name.to_str()),
    ) else {
        return Err(missing.to_owned());
    };
    let raw = read_regular(parent, name, 262_144)?;
    if digest(&raw) != expected {
        return Err("Selected neural profile asset differs from its reviewed binding.".into());
    }
    Ok(raw)
}

/// Construct only the exact SC-selected installation and exact embedded worker sources.
pub(crate) fn installation() -> Result<NeuralExecutor, String> {
    let runtime = include_bytes!("../public-data/neural-selected-checker-runtime.json");
    if digest(runtime) != "7f37448dcd18d9c2b41b2f1966154a5cff9f96081195a79b6dd5a5c8596b4890" {
        return Err(
            "Selected checker installation descriptor differs from its reviewed binding.".into(),
        );
    }
    let raw = operator_file(
        INSTALLATION_VARIABLE,
        "7e0e98ba8c02f8a5cf6d9ae58d9146d2106b1211ae0739f0945f2eeb093a611d",
        "No reviewed checker installation descriptor is selected for this neural registration.",
    )?;
    let settings: Settings = decode(&raw, "selected consumer checker installation")?;
    let files = settings
        .bindings
        .into_iter()
        .map(|item| InstalledFile {
            name: item.name,
            path: item.actual_path,
            sha256: item.sha256,
            byte_length: item.byte_length,
        })
        .collect();
    let installation = Installation::with_embedded_workers(
        runtime.to_vec(),
        files,
        settings.import_roots,
        &[
            (
                "loop_timing_witness/__init__.py",
                include_bytes!("../checker_worker/loop_timing_witness/__init__.py"),
            ),
            (
                "loop_timing_witness/neural_checker_worker.py",
                include_bytes!("../checker_worker/loop_timing_witness/neural_checker_worker.py"),
            ),
            (
                "loop_timing_witness/neural_checker_isolation.py",
                include_bytes!("../checker_worker/loop_timing_witness/neural_checker_isolation.py"),
            ),
        ],
    )?;
    Ok(NeuralExecutor::Host(Box::new(installation)))
}

/// Operator variable selecting the extracted immutable checker image directory.
pub(crate) const IMAGE_ROOT_VARIABLE: &str = "LOOP_TIMING_WITNESS_CHECKER_IMAGE";

/// Construct the source owner's qualified immutable executor registration.
///
/// The image directory and the executor binding come from the operator, never
/// from acquisition data; both are verified against pinned digests and inventory.
pub(crate) fn image() -> Result<NeuralExecutor, String> {
    let runtime = include_bytes!("../public-data/neural-image-checker-runtime.json");
    if digest(runtime) != "5e3f47b55576fc977f339d994e746ee23166d93e03ad4e6f33b90ca15b04dd9a" {
        return Err("Selected checker image descriptor differs from its reviewed binding.".into());
    }
    let binding = operator_file(
        IMAGE_BINDING_VARIABLE,
        "92727d94d239cab44f1ff966a890a438f5864086e8129b594ad75828c420ae2a",
        "No immutable checker image binding is selected for this neural registration.",
    )?;
    let selected = std::env::var_os(IMAGE_ROOT_VARIABLE)
        .map(PathBuf::from)
        .filter(|path| path.is_absolute())
        .ok_or("No immutable checker image is selected for this neural registration.")?;
    Ok(NeuralExecutor::Image(Box::new(ImageExecutor::new(
        selected,
        &binding,
        runtime.to_vec(),
    )?)))
}
