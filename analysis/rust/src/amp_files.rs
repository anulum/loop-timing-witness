// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — AMP input files read as Python's manifest_io reads them

//! Read AMP input files as the Python module `manifest_io` does, with a read
//! error told from a refusal.

use crate::amp_failure::AmpFailure;
use crate::control_json::{Orders, decode_object};
use crate::control_manifest::read_file;
use crate::control_paths::pure;
use crate::control_text::python_display;
use crate::files::digest;
use serde_json::{Map, Value};
use std::path::Path;

/// Python's `sha256_of_file`: the digest of a whole file, or the `OSError`
/// text of opening or reading it.
pub(crate) fn file_digest(path: &Path) -> Result<String, AmpFailure> {
    let content = read_file(path).map_err(|failure| AmpFailure::Os(failure.text()))?;
    Ok(digest(&content))
}

/// Python's `load_bounded_json_object(directory / name)`: the `OSError` text
/// naming the path, or the bounded decoder's refusal labelled with it. The
/// member order of every object is returned too.
pub(crate) fn load_document(
    directory: &Path,
    name: &str,
) -> Result<(Map<String, Value>, Orders), AmpFailure> {
    let path = pure(&directory.join(name));
    let raw = read_file(&path).map_err(|failure| AmpFailure::Os(failure.text()))?;
    decode_object(&raw, &python_display(&path)).map_err(AmpFailure::Refused)
}
