// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — consumer-registry acquisition through the public Rust API

//! Analyse one acquisition against a consumer registry described by a test.
//!
//! The Python parity tests write a registry description naming the reviewed
//! policy bytes and the executor, run this test with
//! `NEURAL_REGISTRY_SPEC`, and compare the recorded outcome with the Python
//! result for the same acquisition. With `command` set, the analysis command
//! runs against the same registry and publishes into that new directory.
//! Without the variable the test has no input.
//!
//! With `CONTROL_RUN_SPEC` the second test loads one CONTROL or COMPUTE run,
//! optionally from root bytes the description names, decodes its events and
//! records the inputs, the events or the refusal for the same comparison.

use serde::Deserialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::path::PathBuf;
use witness_analysis::public_runtime::{Installation, InstalledFile};
use witness_analysis::{
    ImageExecutor, NeuralEntry, NeuralRegistry, build_neural_run_report, decode_control_events,
    load_control_run, load_control_run_bytes, load_neural_run_with_registry, neural_key,
    public_command,
};

/// Registry description written by the Python parity helper.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Spec {
    manifest: PathBuf,
    outcome: PathBuf,
    source_sha256: String,
    policy: PathBuf,
    checker: PathBuf,
    executor: Executor,
    command: Option<PathBuf>,
}

/// The reviewed executor of the single registry entry.
#[derive(Deserialize)]
#[serde(deny_unknown_fields, rename_all = "lowercase")]
enum Executor {
    Image {
        root: PathBuf,
        binding: PathBuf,
        runtime: PathBuf,
    },
    Host {
        contract: PathBuf,
        files: Vec<File>,
        import_roots: Vec<PathBuf>,
        worker_import_root: PathBuf,
    },
}

/// One reviewed host runtime file.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct File {
    name: String,
    path: PathBuf,
    sha256: String,
    byte_length: u64,
}

/// Read one file the description names.
fn read(path: &PathBuf) -> Vec<u8> {
    std::fs::read(path).expect("file named by the registry description")
}

/// Build the entry the description names; construction refusals are outcomes too.
fn entry(spec: &Spec) -> Result<NeuralEntry, String> {
    let (policy, checker) = (read(&spec.policy), read(&spec.checker));
    match &spec.executor {
        Executor::Image {
            root,
            binding,
            runtime,
        } => Ok(NeuralEntry::image(
            policy,
            checker,
            ImageExecutor::new(root.clone(), &read(binding), read(runtime))?,
        )),
        Executor::Host {
            contract,
            files,
            import_roots,
            worker_import_root,
        } => {
            let files = files
                .iter()
                .map(|item| InstalledFile {
                    name: item.name.clone(),
                    path: item.path.clone(),
                    sha256: item.sha256.clone(),
                    byte_length: item.byte_length,
                })
                .collect();
            Ok(NeuralEntry::host(
                policy,
                checker,
                Installation::from_selected_contract(
                    read(contract),
                    files,
                    import_roots.clone(),
                    worker_import_root.clone(),
                )?,
            ))
        }
    }
}

#[test]
fn consumer_registry_acquisition() {
    let Some(path) = std::env::var_os("NEURAL_REGISTRY_SPEC") else {
        return;
    };
    let spec: Spec =
        serde_json::from_slice(&read(&PathBuf::from(path))).expect("closed registry description");
    let (manifest, outcome) = (spec.manifest.clone(), spec.outcome.clone());
    let command = spec.command.clone();
    let mut registry = NeuralRegistry::new();
    registry.insert(
        neural_key(spec.source_sha256.clone()),
        Box::new(move || entry(&spec)),
    );
    let rendered: Value = if let Some(output) = command {
        let (mut stdout, mut stderr) = (Vec::new(), Vec::new());
        let arguments = [manifest.into(), "--output-dir".into(), output.into()];
        let status = public_command::run(&arguments, &registry, &mut stdout, &mut stderr);
        json!({
            "status": status,
            "stdout": String::from_utf8(stdout).expect("authored UTF-8"),
            "stderr": String::from_utf8(stderr).expect("authored UTF-8"),
        })
    } else {
        match load_neural_run_with_registry(&manifest, &registry) {
            Ok(inputs) => json!({ "report": build_neural_run_report(&inputs) }),
            Err(refusal) => json!({ "refusal": refusal }),
        }
    };
    std::fs::write(
        outcome,
        serde_json::to_vec(&rendered).expect("outcome JSON"),
    )
    .expect("outcome file");
}

/// Run description written by the Python control-run parity helper.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ControlSpec {
    manifest: PathBuf,
    outcome: PathBuf,
    root: Option<PathBuf>,
}

#[test]
fn control_run_acquisition() {
    let Some(path) = std::env::var_os("CONTROL_RUN_SPEC") else {
        return;
    };
    let spec: ControlSpec =
        serde_json::from_slice(&read(&PathBuf::from(path))).expect("closed run description");
    let loaded = match &spec.root {
        Some(root) => load_control_run_bytes(&spec.manifest, &read(root)),
        None => load_control_run(&spec.manifest),
    };
    let rendered = match loaded {
        Err(refusal) => json!({ "refusal": refusal }),
        Ok(inputs) => {
            let files: serde_json::Map<String, Value> = inputs
                .files()
                .iter()
                .map(|(name, bytes)| (name.clone(), json!(format!("{:x}", Sha256::digest(bytes)))))
                .collect();
            let events = decode_control_events(&inputs).map(|events| {
                events
                    .iter()
                    .map(|event| json!([event.name, event.cycle, event.ticks]))
                    .collect::<Vec<_>>()
            });
            json!({
                "manifest": inputs.manifest(),
                "domain": inputs.domain(),
                "files": files,
                "directory": inputs.directory(),
                "events": events.as_ref().ok(),
                "events_refusal": events.err(),
            })
        }
    };
    std::fs::write(
        spec.outcome,
        serde_json::to_vec(&rendered).expect("outcome JSON"),
    )
    .expect("outcome file");
}
