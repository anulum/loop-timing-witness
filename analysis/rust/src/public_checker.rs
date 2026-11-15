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

/// Map a failed owned staging operation to the refusal Python gives any OS error here.
fn staged<T>(result: std::io::Result<T>) -> Result<T, String> {
    result.map_err(|_| "Cannot bind the complete public neural acquisition.".to_owned())
}

/// Independent source, numerical and process-completion findings.
pub(crate) struct Findings {
    pub source: Vec<String>,
    pub numerical: Vec<String>,
    pub completion: Vec<String>,
    pub executed: bool,
}

/// Execute the complete source-owned model from only its admitted source closure.
pub(crate) fn verify(run: &mut PublicRun) -> Result<Findings, String> {
    let source = crate::public_checker_receipts::findings(run)?;
    let digests: Vec<String> = run
        .contract
        .checker
        .source_files
        .iter()
        .map(|reference| reference.sha256.clone())
        .collect();
    let mut findings = Findings {
        source,
        numerical: Vec::new(),
        completion: Vec::new(),
        executed: true,
    };
    let temporary = OwnedDirectory::create(&std::env::temp_dir(), "neural-checker-")?;
    let copied = stage(run, &temporary.path)?;
    let script = temporary
        .path
        .join("source-closure")
        .join(&run.contract.checker.entry_point.path);
    for operation in ["generate", "check"] {
        let directory = temporary.path.join(operation);
        let (actual, trace) = execute(run, &script, operation, &directory, &copied, &digests)?;
        findings.source.extend(trace);
        findings.executed &= actual
            .observation
            .as_ref()
            .is_some_and(|value| value.phase == "source");
        let (source_findings, numerical_findings, completion_findings) =
            invocation_findings(&actual);
        findings.source.extend(source_findings);
        findings.numerical.extend(numerical_findings);
        findings.completion.extend(completion_findings);
        if operation == "generate" && actual.returncode == 0 {
            findings
                .source
                .extend(generation_findings(run, &directory)?);
        }
        retain(run, operation, actual)?;
    }
    run.contract.installation.verify()?;
    Ok(findings)
}

/// Write the admitted checker source closure and the projection under the owned directory.
///
/// Returns the paths of the copied source files.
fn stage(run: &PublicRun, root: &Path) -> Result<BTreeSet<PathBuf>, String> {
    let source_root = root.join("source-closure");
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
        root.join("check/results_verilog.txt"),
        &run.core.files["numerical_projection"],
    ));
    let directories: BTreeSet<_> = files
        .iter()
        .filter_map(|(path, _)| path.parent())
        .chain([root.join("generate").as_path()])
        .map(Path::to_path_buf)
        .collect();
    for directory in &directories {
        staged(std::fs::create_dir_all(directory))?;
    }
    for (path, body) in &files {
        staged(std::fs::write(path, body))?;
    }
    Ok(copied)
}

/// Run one checker operation on the host installation or the image, with its trace findings.
fn execute(
    run: &PublicRun,
    script: &Path,
    operation: &str,
    directory: &Path,
    copied: &BTreeSet<PathBuf>,
    digests: &[String],
) -> Result<(Invocation, Vec<String>), String> {
    match &run.contract.installation {
        NeuralExecutor::Host(installation) => {
            let actual = invoke(installation, script, operation, directory)?;
            let trace = crate::public_trace::findings(&actual, directory, copied, installation)?;
            Ok((actual, trace))
        }
        NeuralExecutor::Image(image) => {
            let actual = image.invoke(operation, directory)?;
            let trace = image.findings(&actual, digests);
            Ok((actual, trace))
        }
    }
}

/// Compare the generated stimulus and expected results with the bound original fixture.
fn generation_findings(run: &PublicRun, directory: &Path) -> Result<Vec<String>, String> {
    let mut findings = Vec::new();
    for (filename, role) in [
        ("stimuli.txt", "original_stimulus"),
        ("results_expected.txt", "reference_projection"),
    ] {
        if output_bytes(&directory.join(filename), 65536)? != run.core.files[role] {
            findings
                .push("Actual source generation differs from the bound original fixture.".into());
        }
    }
    Ok(findings)
}

/// Retain one operation's execution receipt, output streams and opened-file trace in the run.
fn retain(run: &mut PublicRun, operation: &str, actual: Invocation) -> Result<(), String> {
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
    Ok(())
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
