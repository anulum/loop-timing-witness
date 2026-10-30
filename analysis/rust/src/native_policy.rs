// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — typed selected compiler and artifact policy

//! Typed exact source and compiled-object identities shared by the public admission path.

use crate::files::FileRef;
use serde::Deserialize;
use std::collections::BTreeMap;

/// Finite complete compiled-object allocation.
pub(crate) const ARTIFACT_LIMIT: usize = 8 * 1024 * 1024;

/// Fixed complete original source pin.
#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Pin {
    pub sha256: String,
    pub byte_length: u64,
}

/// Closed actual compiled artifact population.
#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Artifacts {
    pub native_executable: FileRef,
    pub generated_model_archive: FileRef,
    pub generated_model_header: FileRef,
    pub verilated_runtime_object: FileRef,
    pub verilated_threads_object: FileRef,
}

impl Artifacts {
    /// Iterate every actual artifact once in the same semantic order.
    pub fn entries(&self) -> [(&str, &FileRef); 5] {
        [
            ("native_executable", &self.native_executable),
            ("generated_model_archive", &self.generated_model_archive),
            ("generated_model_header", &self.generated_model_header),
            ("verilated_runtime_object", &self.verilated_runtime_object),
            ("verilated_threads_object", &self.verilated_threads_object),
        ]
    }
}

/// Native qualification policy compiled into this consumer, never loaded from a run.
#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Policy {
    pub sources: BTreeMap<String, Pin>,
    pub compiled_artifacts: BTreeMap<String, Artifacts>,
    pub tool_versions: BTreeMap<String, String>,
}
