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
use crate::manifest::SourcePins;
use crate::native_policy::Pin;
use crate::public_manifest;
use crate::public_policy::{self, Contract};
use crate::public_registry::NeuralRegistry;
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
pub(crate) fn load(path: &Path, registry: &NeuralRegistry) -> Result<PublicRun, String> {
    let (raw, _, manifest) = public_manifest::acquire(path)?;
    let root = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."))
        .canonicalize()
        .map_err(|_| "Cannot bind the complete public neural acquisition.".to_owned())?;
    let contract = public_policy::admit(&root, &manifest, registry)?;
    let sources = bind_sources(&root, &manifest.source_files, &contract.policy.sources)?;
    check_pins(&sources, &manifest.sc_body_pins)?;
    check_checker_closure(&root, &sources, &contract.checker.source_files)?;
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
    files.insert("checker_policy".into(), contract.checker_bytes.clone());
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

/// Bind the complete reviewed source population and read every source body.
fn bind_sources(
    root: &Path,
    references: &[FileRef],
    expected: &BTreeMap<String, Pin>,
) -> Result<BTreeMap<String, Vec<u8>>, String> {
    let paths: BTreeSet<_> = references
        .iter()
        .map(|reference| reference.path.as_str())
        .collect();
    // Declarations already refused a repeated source path.
    if paths != expected.keys().map(String::as_str).collect() {
        return Err(
            "Complete public neural source population differs from its reviewed policy.".into(),
        );
    }
    let mut sources = BTreeMap::new();
    for reference in references {
        let identity = expected
            .get(&reference.path)
            .ok_or("Public source role is unavailable in the reviewed policy.")?;
        if reference.sha256 != identity.sha256 || reference.byte_length != identity.byte_length {
            return Err("Public neural source reference differs from its reviewed policy.".into());
        }
        sources.insert(
            reference.path.clone(),
            read_bound(root, reference, 1048576)?,
        );
    }
    Ok(sources)
}

/// Require every SC body pin to equal the digest of its bound source.
fn check_pins(sources: &BTreeMap<String, Vec<u8>>, pins: &SourcePins) -> Result<(), String> {
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
    Ok(())
}

/// Require each checker source role, read as its own file, to equal its admitted body once.
fn check_checker_closure(
    root: &Path,
    sources: &BTreeMap<String, Vec<u8>>,
    checker_sources: &[FileRef],
) -> Result<(), String> {
    let mut checker_paths = BTreeSet::new();
    for reference in checker_sources {
        // Each checker role is bound from the run as its own file, then to the admitted body.
        let body = read_bound(root, reference, 1048576)?;
        if sources.get(&reference.path) != Some(&body) {
            return Err(
                "Checker source closure differs from the admitted whole source population.".into(),
            );
        }
        checker_paths.insert(&reference.path);
    }
    if checker_paths.len() != checker_sources.len() {
        return Err("Selected checker source closure contains duplicate roles.".into());
    }
    Ok(())
}
