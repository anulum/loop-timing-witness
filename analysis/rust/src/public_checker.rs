// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — fresh whole source-checker verification

//! Copy exact admitted sources, execute both real operations and retain original observations.

use crate::public_binding::PublicRun;
use crate::public_execution::{Invocation, invoke, output_bytes};
use crate::public_image::NeuralExecutor;
use crate::public_temporary::OwnedDirectory;
use serde_json::json;
use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

/// Independent source, numerical and process-completion findings.
/// Map a failed owned staging operation to the refusal Python gives any OS error here.
fn staged<T>(result: std::io::Result<T>) -> Result<T, String> {
    result.map_err(|_| "Cannot bind the complete public neural acquisition.".to_owned())
}

pub(crate) struct Findings {
    pub source: Vec<String>,
    pub numerical: Vec<String>,
    pub completion: Vec<String>,
    pub executed: bool,
}

/// Execute the complete source-owned model from only its admitted source closure.
pub(crate) fn verify(run: &mut PublicRun) -> Result<Findings, String> {
    let mut source = crate::public_checker_receipts::findings(run)?;
    let digests: Vec<String> = run
        .contract
        .checker
        .source_files
        .iter()
        .map(|reference| reference.sha256.clone())
        .collect();
    let mut numerical = Vec::new();
    let mut completion = Vec::new();
    let mut executed = true;
    let temporary = OwnedDirectory::create(&std::env::temp_dir(), "neural-checker-")?;
    let source_root = temporary.path.join("source-closure");
    // Binding admitted every checker source body against its reference.
    let mut files: Vec<(PathBuf, &[u8])> = run
        .contract
        .checker
        .source_files
        .iter()
        .map(|reference| {
            let body = run.core.sources[&reference.path].as_slice();
            (source_root.join(&reference.path), body)
        })
        .collect();
    let copied: BTreeSet<_> = files.iter().map(|(path, _)| path.clone()).collect();
    files.push((
        temporary.path.join("check/results_verilog.txt"),
        &run.core.files["numerical_projection"],
    ));
    let directories: BTreeSet<_> = files
        .iter()
        .filter_map(|(path, _)| path.parent())
        .chain([temporary.path.join("generate").as_path()])
        .map(Path::to_path_buf)
        .collect();
    for directory in &directories {
        staged(std::fs::create_dir_all(directory))?;
    }
    for (path, body) in &files {
        staged(std::fs::write(path, body))?;
    }
    let script = source_root.join(&run.contract.checker.entry_point.path);
    for operation in ["generate", "check"] {
        let directory = temporary.path.join(operation);
        let actual = match &run.contract.installation {
            NeuralExecutor::Host(installation) => {
                let actual = invoke(installation, &script, operation, &directory)?;
                source.extend(crate::public_trace::findings(
                    &actual,
                    &directory,
                    &copied,
                    installation,
                )?);
                actual
            }
            NeuralExecutor::Image(image) => {
                let actual = image.invoke(operation, &directory)?;
                source.extend(image.findings(&actual, &digests));
                actual
            }
        };
        executed &= actual
            .observation
            .as_ref()
            .is_some_and(|value| value.phase == "source");
        let (source_findings, numerical_findings, completion_findings) =
            invocation_findings(&actual);
        source.extend(source_findings);
        numerical.extend(numerical_findings);
        completion.extend(completion_findings);
        if operation == "generate" && actual.returncode == 0 {
            for (filename, role) in [
                ("stimuli.txt", "original_stimulus"),
                ("results_expected.txt", "reference_projection"),
            ] {
                if output_bytes(&directory.join(filename), 65536)? != run.core.files[role] {
                    source.push(
                        "Actual source generation differs from the bound original fixture.".into(),
                    );
                }
            }
        }
        let receipt = json!({
            "command":actual.command,
            "native_returncode":actual.returncode,
            "started_ns":actual.started_ns,
            "completed_ns":actual.completed_ns,
            "elapsed_ns":actual.elapsed_ns,
            "interrupted":actual.interrupted,
            "worker_observation":actual.observation,
        });
        run.core.files.insert(
            format!("fresh_checker_{operation}_execution_receipt"),
            crate::public_report::canonical(&receipt)?,
        );
        run.core
            .files
            .insert(format!("fresh_checker_{operation}_stdout"), actual.stdout);
        run.core
            .files
            .insert(format!("fresh_checker_{operation}_stderr"), actual.stderr);
        run.core.files.insert(
            format!("fresh_checker_{operation}_opened_files"),
            actual.trace,
        );
    }
    run.contract.installation.verify()?;
    Ok(Findings {
        source,
        numerical,
        completion,
        executed,
    })
}

/// Reconcile actual process completion independently from numerical comparison.
fn invocation_findings(actual: &Invocation) -> (Vec<String>, Vec<String>, Vec<String>) {
    let mut source = Vec::new();
    let mut numerical = Vec::new();
    let mut completion = Vec::new();
    if actual.interrupted || actual.observation.is_none() {
        completion.push("Actual source checker lacks a complete reaped observation.".into());
    } else if actual
        .observation
        .as_ref()
        .is_some_and(|observation| observation.native_returncode != actual.returncode)
    {
        source.push("Actual source checker worker and native process status differ.".into());
    }
    if actual.returncode != 0 {
        numerical.push("Actual source checker refused the complete selected projection.".into());
    }
    if !actual.stderr.is_empty() {
        completion.push("Actual source checker reported an execution diagnostic.".into());
    }
    (source, numerical, completion)
}
