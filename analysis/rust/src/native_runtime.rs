// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — native compiler and artifact reconciliation

//! Complete recorded native source/configuration/object/run predicates.

use crate::binding::BoundRun;
use crate::files::{FileRef, decode, read_bound};
use crate::native_jobs::{Job, unique_paths};
use crate::native_policy::{ARTIFACT_LIMIT, Artifacts, Policy};
use serde::Deserialize;
use std::collections::{BTreeMap, BTreeSet};

/// Actual closed model parameter tuple.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Parameters {
    #[serde(rename = "EXTRA_STATE_REGISTER")]
    state: u64,
    #[serde(rename = "TIMESTAMP_OFFSET")]
    timestamp: u64,
    #[serde(rename = "DROP_ENCODER_FEED")]
    feed: u64,
    #[serde(rename = "ADDRESS_BITS")]
    address: u64,
}
/// Closed actual compiler version fields.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Versions {
    verilator: String,
    #[serde(rename = "g++")]
    cpp: String,
}

/// All actual recorded runtime fields.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Runtime {
    scope: String,
    backend: String,
    dialect: String,
    epoch: u64,
    steps: u64,
    parameters: Parameters,
    tool_versions: Versions,
    source_files: Vec<FileRef>,
    #[serde(deserialize_with = "unique_paths")]
    actual_source_paths: BTreeMap<String, String>,
    jobs: Vec<Job>,
    compiled_artifacts: Artifacts,
    runtime_object_source_scope: String,
}

/// Compare exact references before reading their entire bound original bytes.
fn same(a: &FileRef, b: &FileRef) -> bool {
    a.path == b.path && a.sha256 == b.sha256 && a.byte_length == b.byte_length
}

/// Bind every native artifact/log and reconcile recorded compiler and run semantics.
pub(crate) fn analyze(
    run: &mut BoundRun,
    p: &Policy,
) -> Result<(Vec<String>, Vec<String>), String> {
    let r: Runtime = decode(&run.files["compiler_simulator_runtime"], "native runtime")?;
    if r.backend != "verilator-native-cpp" || r.dialect != "1800-2012" {
        return Err("Unsupported actual native backend or dialect.".into());
    }
    let _scopes = (&r.scope, &r.runtime_object_source_scope);
    let params = [
        r.parameters.state,
        r.parameters.timestamp,
        r.parameters.feed,
        r.parameters.address,
    ];
    if params.iter().any(|v| *v > 65535) || r.epoch > 65535 || r.steps > 65535 || r.jobs.len() != 5
    {
        return Err("Invalid complete native receipt ranges/populations.".into());
    }
    let key = format!(
        "{},{},{},{}:{}",
        params[0], params[1], params[2], params[3], r.epoch
    );
    let expected = p
        .compiled_artifacts
        .get(&key)
        .ok_or("Unsupported actual native compiled artifact cohort.")?;
    for ((name, actual), (_, expected)) in r
        .compiled_artifacts
        .entries()
        .iter()
        .zip(expected.entries())
    {
        if !same(actual, expected) {
            return Err("Unsupported actual native compiled artifact cohort.".into());
        }
        run.files.insert(
            format!("native_{name}"),
            read_bound(&run.root, actual, ARTIFACT_LIMIT)?,
        );
    }
    if r.source_files.len() != run.manifest.source_files.len()
        || r.source_files
            .iter()
            .zip(&run.manifest.source_files)
            .any(|(a, b)| !same(a, b))
    {
        return Err("Native runtime source references differ from root.".into());
    }
    if r.actual_source_paths.len() != p.sources.len()
        || r.actual_source_paths.values().collect::<BTreeSet<_>>()
            != run.sources.keys().collect::<BTreeSet<_>>()
    {
        return Err("Native recorded source path population differs.".into());
    }
    let roles = [
        "RTL_elaboration",
        "generated_model_archive",
        "native_CPP_compile",
        "native_CPP_link",
        "native_execution",
    ];
    for (i, j) in r.jobs.iter().enumerate() {
        let (kind, argv, _) = j.command();
        if kind != roles[i] || argv.is_empty() || (i == 4) != matches!(j, Job::Execution(_)) {
            return Err("Actual native command sequence differs.".into());
        }
        for (name, reference) in j.logs() {
            run.files.insert(
                format!("native_job_{i}_{name}"),
                read_bound(&run.root, reference, 1048576)?,
            );
        }
    }
    let verilator = r.jobs[0].command().1;
    let observed: BTreeSet<_> = verilator
        .iter()
        .filter(|x| x.starts_with("-G"))
        .cloned()
        .collect();
    let names = [
        "EXTRA_STATE_REGISTER",
        "TIMESTAMP_OFFSET",
        "DROP_ENCODER_FEED",
        "ADDRESS_BITS",
    ];
    let expected: BTreeSet<_> = names
        .iter()
        .zip(params)
        .zip([0, 0, 0, 10])
        .filter(|((_, v), default)| v != default)
        .map(|((n, v), _)| format!("-G{n}={v}"))
        .collect();
    let cpp = r.jobs[2].command().1;
    let actual_native = r
        .actual_source_paths
        .iter()
        .find(|(_, v)| *v == "native/native_trial.cpp")
        .ok_or("Native producer path missing.")?
        .0;
    let mode = if run.manifest.epoch == 1 {
        "reset"
    } else {
        "original"
    };
    let mut findings = Vec::new();
    let required: BTreeSet<_> = [
        "native_neural_dut.sv",
        "source/proposed_neural_wrapper.sv",
        "source/SC-NEUROCORE/hdl/sc_lif_neuron.v",
        "source/SC-NEUROCORE/hdl/sc_aer_encoder.v",
        "source/LOOP-TIMING-WITNESS/rtl/clock_reset_release.sv",
        "source/LOOP-TIMING-WITNESS/rtl/shared_event_witness.sv",
        "source/LOOP-TIMING-WITNESS/rtl/event_record_fifo.sv",
    ]
    .into_iter()
    .collect();
    let compiled: BTreeSet<_> = verilator
        .iter()
        .filter_map(|a| r.actual_source_paths.get(a).map(String::as_str))
        .collect();
    if compiled != required {
        findings.push("Actual native compiled RTL source inventory differs.".into());
    }
    if r.tool_versions.verilator != p.tool_versions["verilator"]
        || r.tool_versions.cpp != p.tool_versions["g++"]
    {
        findings.push("Actual native compiler versions differ.".into());
    }
    if r.backend != "verilator-native-cpp"
        || r.dialect != "1800-2012"
        || r.epoch != u64::from(run.manifest.epoch)
        || r.steps != 1000
        || u64::from(run.manifest.fifo_capacity_records) != 1_u64 << params[3]
    {
        findings.push("Actual native runtime identity/configuration differs.".into());
    }
    if observed != expected
        || !verilator
            .windows(2)
            .any(|a| a == ["--language", "1800-2012"])
        || [
            "--cc",
            "--Wall",
            "--assert",
            "+1800-2012ext+v",
            "+1800-2012ext+sv",
        ]
        .iter()
        .any(|x| !verilator.iter().any(|a| a == x))
        || !cpp.contains(actual_native)
        || [
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wconversion",
            "-Wshadow",
        ]
        .iter()
        .any(|x| !cpp.iter().any(|a| a == x))
        || r.jobs[4].command().1.last().map(String::as_str) != Some(mode)
    {
        findings.push("Actual native compiler/dialect/run arguments differ.".into());
    }
    if r.jobs.iter().any(|j| j.command().2 != 0)
        || run.files["native_job_4_stdout"] != b"NATIVE_JOINT_EXPORT_COMPLETE\n"
        || !run.files["native_job_4_stderr"].is_empty()
    {
        findings.push("Actual native build/execution did not complete cleanly.".into());
    }
    if params != [0, 0, 0, 10] {
        findings
            .push("Actual compile parameters differ from selected source configuration.".into());
    }
    let publication = if r.jobs[4].command().2 != 0
        || run.files["native_job_4_stdout"] != b"NATIVE_JOINT_EXPORT_COMPLETE\n"
        || !run.files["native_job_4_stderr"].is_empty()
    {
        vec!["Actual native execution/publication did not finalise cleanly.".into()]
    } else {
        Vec::new()
    };
    Ok((findings, publication))
}
