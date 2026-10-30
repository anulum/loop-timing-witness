// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — closed original checker receipt fields

//! Original execution receipts retain exact numeric types and operation-specific roles.

use crate::files::FileRef;
use serde::Deserialize;

/// Original complete generation output or check input fixture.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Fixture {
    pub stimuli: FileRef,
    pub reference: FileRef,
}

/// Original complete numerical comparison input.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Projection {
    pub stimuli: FileRef,
    pub reference: FileRef,
    pub observed: FileRef,
}

/// An actual operation with no declared file roles.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Empty {}

/// Closed operation alternatives; null, unknown and duplicate role keys refuse.
#[derive(Deserialize)]
#[serde(untagged)]
pub(crate) enum Roles {
    Empty(Empty),
    Fixture(Fixture),
    Projection(Projection),
}

/// Complete closed original source-owned execution receipt.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Receipt {
    pub schema_id: String,
    pub source_contract_ref: FileRef,
    pub checker_policy_ref: FileRef,
    pub operation: String,
    pub actual_argv: Vec<String>,
    pub environment_ref: FileRef,
    pub inputs: Roles,
    pub outputs: Roles,
    pub observed_source_inventory_ref: FileRef,
    pub observed_runtime_inventory_ref: FileRef,
    pub stdout_ref: FileRef,
    pub stderr_ref: FileRef,
    pub native_returncode: i32,
    pub started_ns: u64,
    pub completed_ns: u64,
    pub elapsed_ns: u64,
    pub cleanup: String,
}

/// Original closed environment keys are also duplicate-rejecting.
#[derive(Deserialize)]
#[serde(transparent)]
pub(crate) struct Environment(
    #[serde(deserialize_with = "crate::native_jobs::unique_paths")]
    pub  std::collections::BTreeMap<String, String>,
);
