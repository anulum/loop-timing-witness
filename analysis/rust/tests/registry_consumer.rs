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
//!
//! With `CONTROL_COMMAND_SPEC` the third test runs the analysis command with
//! the described arguments, optionally under a file-size limit set in this
//! process and restored before the outcome is written, and records its status
//! and printed text. With `CAMPAIGN_COMMAND_SPEC` the fourth test runs the
//! repeat campaign command in the same way.

#[path = "support/digest.rs"]
mod digest;

use digest::sha256_hex;
use rustix::process::{Resource, Rlimit, getrlimit, setrlimit};
use serde::Deserialize;
use serde_json::{Value, json};
use std::path::PathBuf;
use witness_analysis::public_runtime::{Installation, InstalledFile};
use witness_analysis::{
    ImageExecutor, NeuralEntry, NeuralRegistry, build_neural_run_report, campaign_command,
    control_events_summary, control_run_report, decode_control_events, load_control_run,
    load_control_run_bytes, load_neural_run_with_registry, neural_key, public_command,
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
                .map(|(name, bytes)| (name.clone(), json!(sha256_hex(bytes))))
                .collect();
            let events = decode_control_events(&inputs).map(|events| {
                events
                    .iter()
                    .map(|event| json!([event.name, event.cycle, event.ticks]))
                    .collect::<Vec<_>>()
            });
            let summary = control_events_summary(&inputs).map(|(block, rows)| {
                let rows: Vec<Value> = rows
                    .iter()
                    .map(|row| json!([row.cycle, row.interval, row.ticks]))
                    .collect();
                json!({ "block": block, "rows": rows })
            });
            let report = control_run_report(&inputs).map(|(report, rows)| {
                let rows: Vec<Value> = rows
                    .iter()
                    .map(|row| json!([row.cycle, row.interval, row.ticks]))
                    .collect();
                json!({ "report": report, "rows": rows })
            });
            json!({
                "manifest": inputs.manifest(),
                "domain": inputs.domain(),
                "files": files,
                "directory": inputs.directory(),
                "events": events.as_ref().ok(),
                "events_refusal": events.err(),
                "summary": summary.as_ref().ok(),
                "summary_refusal": summary.err(),
                "report": report.as_ref().ok(),
                "report_refusal": report.err(),
            })
        }
    };
    std::fs::write(
        spec.outcome,
        serde_json::to_vec(&rendered).expect("outcome JSON"),
    )
    .expect("outcome file");
}

/// Command description written by the Python control-command parity helper.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CommandSpec {
    arguments: Vec<String>,
    outcome: PathBuf,
    /// Largest file, in bytes, the command may write; the caller ignores `SIGXFSZ`.
    #[serde(default)]
    file_size_limit: Option<u64>,
}

/// A command entry point: arguments, standard output and standard error to status.
type Command = fn(&[std::ffi::OsString], &mut Vec<u8>, &mut Vec<u8>) -> i32;

#[test]
fn control_command() {
    described_command("CONTROL_COMMAND_SPEC", |arguments, stdout, stderr| {
        public_command::run(arguments, &NeuralRegistry::reviewed(), stdout, stderr)
    });
}

#[test]
fn campaign_command() {
    described_command("CAMPAIGN_COMMAND_SPEC", |arguments, stdout, stderr| {
        campaign_command::run(arguments, stdout, stderr)
    });
}

/// Run one command as the description in the named variable asks and record its outcome.
fn described_command(variable: &str, command: Command) {
    let Some(path) = std::env::var_os(variable) else {
        return;
    };
    let spec: CommandSpec =
        serde_json::from_slice(&read(&PathBuf::from(path))).expect("closed command description");
    let arguments: Vec<std::ffi::OsString> = spec.arguments.iter().map(Into::into).collect();
    let (mut stdout, mut stderr) = (Vec::new(), Vec::new());
    let limit = getrlimit(Resource::Fsize);
    if let Some(bytes) = spec.file_size_limit {
        let lowered = Rlimit {
            current: Some(bytes),
            maximum: limit.maximum,
        };
        setrlimit(Resource::Fsize, lowered).expect("lower the file-size limit");
    }
    let status = command(&arguments, &mut stdout, &mut stderr);
    setrlimit(Resource::Fsize, limit).expect("restore the file-size limit");
    let rendered = json!({
        "status": status,
        "stdout": String::from_utf8_lossy(&stdout),
        "stderr": String::from_utf8_lossy(&stderr),
    });
    std::fs::write(
        spec.outcome,
        serde_json::to_vec(&rendered).expect("outcome JSON"),
    )
    .expect("outcome file");
}
