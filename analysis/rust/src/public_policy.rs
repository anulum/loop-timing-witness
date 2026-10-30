// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — closed public source and checker contracts

//! Exact consumer-owned registration and complete source-policy declarations.

use crate::files::{FileRef, decode, digest, read_expected};
use crate::native_policy::{Artifacts, Pin, Policy};
use crate::public_image::Executor;
use crate::public_manifest_fields::PublicManifest;
use serde::Deserialize;
use std::collections::BTreeMap;
use std::path::Path;

/// Approved neural carrier identity.
pub(crate) const ID: &str = "loop-timing-witness.neural-step-run.v1";
/// Approved public source-cohort name.
pub(crate) const COHORT: &str = "sc-neurocore-neural-step-1n1b16t.v1";

/// Complete closed public source-policy successor.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct PublicPolicy {
    pub schema_sha256: String,
    pub schema_id: String,
    pub cohort: String,
    pub sources: BTreeMap<String, Pin>,
    pub compiled_artifacts: BTreeMap<String, Artifacts>,
    pub tool_versions: BTreeMap<String, String>,
    pub checker_policy_ref: FileRef,
}

impl PublicPolicy {
    /// Share native receipt predicates without rewriting the public identity.
    pub fn native(&self) -> Policy {
        Policy {
            sources: self.sources.clone(),
            compiled_artifacts: self.compiled_artifacts.clone(),
            tool_versions: self.tool_versions.clone(),
        }
    }
}

/// Complete fixed checker selection; argument strings never come from a run.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct CheckerPolicy {
    pub schema_id: String,
    pub entry_point: FileRef,
    pub source_files: Vec<FileRef>,
    pub runtime_contract_ref: FileRef,
    pub generate_arguments: Vec<String>,
    pub check_arguments: Vec<String>,
    pub execution_contract: crate::public_runtime::ExecutionContract,
}

/// Immutable consumer registration, never an acquisition-selected installation.
pub(crate) struct Registration {
    pub source_digest: &'static str,
    pub policy: &'static [u8],
    pub checker: &'static [u8],
    pub installation: fn() -> Result<Executor, String>,
}

/// Fully decoded and installation-bound reviewed source contract.
pub(crate) struct Contract {
    pub policy_bytes: &'static [u8],
    pub checker_bytes: &'static [u8],
    pub policy: PublicPolicy,
    pub checker: CheckerPolicy,
    pub installation: Executor,
}

/// Bind only a consumer-reviewed exact identity before any checker operation.
pub(crate) fn admit(root: &Path, manifest: &PublicManifest) -> Result<Contract, String> {
    static REVIEWED: &[Registration] = &[
        Registration {
            source_digest: "ec1236a69fc9e16a4eff1dfa7bdad8aa8b6088fc4ebceb8d8c43d33517199304",
            policy: include_bytes!("../public-data/neural-selected-source-contract.json"),
            checker: include_bytes!("../public-data/neural-selected-checker-policy.json"),
            installation: crate::selected_profile::installation,
        },
        Registration {
            source_digest: "5ff959e55f59ca3b1d1993bbc2ed9028c49e08feb6ff15a0fd5af156959d5488",
            policy: include_bytes!("../public-data/neural-image-source-contract.json"),
            checker: include_bytes!("../public-data/neural-image-checker-policy.json"),
            installation: crate::selected_profile::image,
        },
    ];
    let registration = REVIEWED
        .iter()
        .find(|entry| entry.source_digest == manifest.source_contract_ref.sha256)
        .ok_or("No reviewed source contract is admitted for this neural run.")?;
    if digest(registration.policy) != registration.source_digest {
        return Err("Consumer public source policy differs from its reviewed identity.".into());
    }
    let policy: PublicPolicy = decode(registration.policy, "consumer public source policy")?;
    if policy.schema_id != ID
        || policy.schema_sha256 != crate::public_manifest::SCHEMA_SHA256
        || policy.cohort != COHORT
        || manifest.schema_id != policy.schema_id
        || manifest.native_source_cohort != policy.cohort
        || policy.sources.is_empty()
        || policy.compiled_artifacts.is_empty()
    {
        return Err("Consumer public source policy does not implement its closed contract.".into());
    }
    read_expected(
        root,
        &manifest.source_contract_ref,
        65536,
        registration.policy,
        "Acquired neural source contract differs from its reviewed consumer policy.",
    )?;
    read_expected(
        root,
        &policy.checker_policy_ref,
        65536,
        registration.checker,
        "Acquired checker policy differs from its reviewed consumer binding.",
    )?;
    let checker: CheckerPolicy = decode(registration.checker, "consumer checker policy")?;
    let expected_generate = ["--generate", "--steps", "1000", "--seed", "42"];
    let expected_check = ["--check", "--steps", "1000", "--seed", "42"];
    if checker.schema_id != "loop-timing-witness.sc-checker-policy.v1"
        || checker.generate_arguments != expected_generate
        || checker.check_arguments != expected_check
        || checker.source_files.is_empty()
        || !checker
            .source_files
            .iter()
            .any(|reference| same(reference, &checker.entry_point))
    {
        return Err("Selected checker requires its complete closed fixed-operation policy.".into());
    }
    let installation = (registration.installation)()?;
    installation.verify()?;
    read_expected(
        root,
        &checker.runtime_contract_ref,
        1048576,
        installation.contract_bytes(),
        "Acquired checker runtime differs from the complete selected installation.",
    )?;
    if checker.execution_contract != *installation.execution_contract() {
        return Err(
            "Acquired checker runtime differs from the complete selected installation.".into(),
        );
    }
    Ok(Contract {
        policy_bytes: registration.policy,
        checker_bytes: registration.checker,
        policy,
        checker,
        installation,
    })
}

/// Compare complete references without relying on a digest alone.
pub(crate) fn same(left: &FileRef, right: &FileRef) -> bool {
    left.path == right.path && left.sha256 == right.sha256 && left.byte_length == right.byte_length
}
