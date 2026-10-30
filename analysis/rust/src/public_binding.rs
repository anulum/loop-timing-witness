// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — complete public acquisition binding

//! Bind public root bytes and all original sources before independent whole-run analysis.

use crate::binding::{self, BoundRun};
use crate::files::{FileRef, digest, read_bound};
use crate::public_manifest;
use crate::public_policy::{self, Contract};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

/// Public policy and original declarations surrounding the shared observation core.
pub(crate) struct PublicRun {
    pub core: BoundRun,
    pub contract: Contract,
    pub source_contract_ref: FileRef,
    pub tool: Value,
}

/// Bind complete public sources and all original acquisition bytes.
pub(crate) fn load(path: &Path) -> Result<PublicRun, String> {
    let (raw, _, manifest) = public_manifest::acquire(path)?;
    let root = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."))
        .canonicalize()
        .map_err(|_| "Public neural acquisition directory is unavailable.".to_owned())?;
    let contract = public_policy::admit(&root, &manifest)?;
    let expected = &contract.policy.sources;
    let paths: BTreeSet<_> = manifest
        .source_files
        .iter()
        .map(|reference| reference.path.as_str())
        .collect();
    if paths.len() != manifest.source_files.len()
        || paths != expected.keys().map(String::as_str).collect()
    {
        return Err(
            "Complete public neural source population differs from its reviewed policy.".into(),
        );
    }
    let mut sources = BTreeMap::new();
    for reference in &manifest.source_files {
        let identity = expected
            .get(&reference.path)
            .ok_or("Public source role is unavailable in the reviewed policy.")?;
        if reference.sha256 != identity.sha256 || reference.byte_length != identity.byte_length {
            return Err("Public neural source reference differs from its reviewed policy.".into());
        }
        sources.insert(
            reference.path.clone(),
            read_bound(&root, reference, 1048576)?,
        );
    }
    let pins = &manifest.sc_body_pins;
    for (name, expected) in [
        ("hdl/sc_lif_neuron.v", &pins.lif),
        ("hdl/tb_sc_lif_neuron.v", &pins.testbench),
        ("hdl/sc_aer_encoder.v", &pins.encoder),
        ("src/sc_neurocore/neurons/fixed_point_lif.py", &pins.model),
        ("src/sc_neurocore/constants.py", &pins.constants),
        ("scripts/cosim_gen_and_check.py", &pins.checker),
        ("tests/test_cosim_gen_and_check.py", &pins.checker_tests),
    ] {
        if sources
            .get(&format!("source/SC-NEUROCORE/{name}"))
            .is_none_or(|raw| digest(raw) != *expected)
        {
            return Err(
                "Public neural SC body pin differs from its complete source binding.".into(),
            );
        }
    }
    let mut checker_paths = BTreeSet::new();
    for reference in &contract.checker.source_files {
        if !checker_paths.insert(&reference.path)
            || sources.get(&reference.path).is_none_or(|body| {
                body.len() as u64 != reference.byte_length || digest(body) != reference.sha256
            })
        {
            return Err(
                "Checker source closure differs from the admitted whole source population.".into(),
            );
        }
    }
    let source_contract_ref = manifest.source_contract_ref.clone();
    let observations = manifest.into_observations();
    let mut files = BTreeMap::from([("manifest".into(), raw)]);
    for (name, reference) in [
        ("input_trace", &observations.input_trace),
        ("numerical_trace", &observations.numerical_trace),
        ("numerical_projection", &observations.numerical_projection),
        ("reference_projection", &observations.reference_projection),
        ("service_trace", &observations.service_trace),
        ("clock_schedule_ref", &observations.clock_schedule_ref),
        ("tool_receipt", &observations.tool_receipt),
    ] {
        binding::role(&mut files, &root, name, reference, 65536)?;
    }
    let tool = crate::public_tools::bind(&root, observations.epoch, &mut files)?;
    files.insert("checker_policy".into(), contract.checker_bytes.to_vec());
    files.insert(
        "checker_runtime_contract".into(),
        contract.installation.contract_bytes().to_vec(),
    );
    let core = binding::finish(&root, observations, sources, files)?;
    Ok(PublicRun {
        core,
        contract,
        source_contract_ref,
        tool,
    })
}
