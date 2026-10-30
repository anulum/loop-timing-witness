// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — actual native command receipt types

//! Closed build and execution jobs without arbitrary command execution.

use crate::files::FileRef;
use serde::Deserialize;
use std::collections::BTreeMap;

/// Complete actual build job.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Build {
    pub kind: String,
    pub command: Vec<String>,
    pub returncode: i32,
    pub log: FileRef,
}
/// Complete actual execution job.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Execution {
    pub kind: String,
    pub command: Vec<String>,
    pub returncode: i32,
    pub stdout: FileRef,
    pub stderr: FileRef,
}
/// Exact original build/execution alternatives.
#[derive(Deserialize)]
#[serde(untagged)]
pub(crate) enum Job {
    Build(Build),
    Execution(Execution),
}

impl Job {
    /// Original role and argument vector.
    pub fn command(&self) -> (&str, &[String], i32) {
        match self {
            Self::Build(j) => (&j.kind, &j.command, j.returncode),
            Self::Execution(j) => (&j.kind, &j.command, j.returncode),
        }
    }
    /// Actual complete log references by native role.
    pub fn logs(&self) -> Vec<(&str, &FileRef)> {
        match self {
            Self::Build(j) => vec![("log", &j.log)],
            Self::Execution(j) => vec![("stdout", &j.stdout), ("stderr", &j.stderr)],
        }
    }
}

/// Reject duplicate recorded source-path keys, including inside JSON maps.
pub(crate) fn unique_paths<'de, D: serde::Deserializer<'de>>(
    d: D,
) -> Result<BTreeMap<String, String>, D::Error> {
    struct Paths;
    impl<'de> serde::de::Visitor<'de> for Paths {
        type Value = BTreeMap<String, String>;
        fn expecting(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
            f.write_str("distinct recorded source paths")
        }
        fn visit_map<A: serde::de::MapAccess<'de>>(
            self,
            mut a: A,
        ) -> Result<Self::Value, A::Error> {
            let mut paths = BTreeMap::new();
            while let Some((k, v)) = a.next_entry::<String, String>()? {
                if paths.insert(k, v).is_some() {
                    return Err(serde::de::Error::custom("duplicate recorded source path"));
                }
            }
            Ok(paths)
        }
    }
    d.deserialize_map(Paths)
}
