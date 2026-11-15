// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — complete public neural report

//! Preserve separate whole-run dimensions, exact original bindings and actual checker evidence.

use crate::files::{decode, digest};
use crate::public_binding::PublicRun;
use serde_json::{Value, json};
use std::collections::BTreeMap;

/// Return deterministic UTF-8 JSON bytes with the complete trailing newline.
pub(crate) fn canonical(value: &Value) -> Result<Vec<u8>, String> {
    // The alternate form is the pretty serialiser, which cannot fail for a JSON value.
    Ok(format!("{value:#}\n").into_bytes())
}

/// Return bytes the analysis already admitted through their typed form as a JSON value.
fn admitted(raw: &[u8]) -> Value {
    serde_json::from_slice(raw).unwrap_or(Value::Null)
}

/// Preserve a whole original byte identity without exposing content-derived execution.
fn identity(raw: &[u8]) -> Value {
    json!({"sha256":digest(raw),"byte_length":raw.len()})
}

/// Keep each finding group independent, with no numerical override of other failures.
fn dimension(findings: &[String]) -> Value {
    json!({"pass":findings.is_empty(),"findings":findings})
}

/// Compute every public verdict from the entire source-bound acquisition and fresh checks.
pub(crate) fn analyze(mut run: PublicRun) -> Result<Value, String> {
    let d = dimensions(&mut run)?;
    let whole = [&d.source, &d.capture, &d.numerical, &d.completion, &d.clock]
        .iter()
        .all(|findings| findings.is_empty());
    let verification = json!({
        "source_binding":dimension(&d.source),"capture":dimension(&d.capture),
        "numerical":dimension(&d.numerical),"completion":dimension(&d.completion),"clock":dimension(&d.clock),
        "whole":whole,
    });
    let mut capture = d.capture_report;
    capture["pass"] = Value::Bool(d.capture.is_empty());
    capture["findings"] = json!(d.capture);
    let clock_schedule = admitted(&run.core.files["clock_schedule_ref"]);
    Ok(json!({
        "schema_id":"loop-timing-witness.neural-step-analysis-report.v1",
        "profile":run.core.manifest.profile,"evidence_class":run.core.manifest.evidence_class,
        "run_id":run.core.manifest.run_id,
        "source_binding":source_binding(&run, d.source),
        "capture":capture,
        "numerical":{
            "pass":d.numerical.is_empty(),"findings":d.numerical,
            "requested_steps":run.core.manifest.step_count,"actual_raw_spikes":d.raw_spikes,
            "actual_service_packets":d.services,
            "original_oracle_equal":d.oracle_equal,
            "source_checker_executed":d.executed,
        },
        "completion":completion(&run, d.completion)?,
        "clock":{"pass":d.clock.is_empty(),"findings":d.clock,"actual_schedule":clock_schedule},
        "verification":verification,
        "limits":[
            "Capture ticks are simulator edges; physical timing and calibration are unavailable.",
            "File integrity and correspondence do not authenticate a remote producer.",
            "This verdict covers the selected single-neuron source cohort and full original acquisition.",
            "A passing run does not establish model-family, physical or whole-project acceptance.",
        ],
    }))
}

/// Every verification dimension's findings and the facts the report states with them.
struct Dimensions {
    /// Source binding findings.
    source: Vec<String>,
    /// Capture findings.
    capture: Vec<String>,
    /// Numerical findings.
    numerical: Vec<String>,
    /// Completion findings.
    completion: Vec<String>,
    /// Clock findings.
    clock: Vec<String>,
    /// Capture component report.
    capture_report: Value,
    /// Observed raw spikes.
    raw_spikes: u64,
    /// Observed service packets.
    services: u64,
    /// Whether the traces equal the original oracle.
    oracle_equal: bool,
    /// Whether the source checker executed.
    executed: bool,
}

/// Analyse traces, completion, clock, native runtime, reset and checker, by dimension.
fn dimensions(run: &mut PublicRun) -> Result<Dimensions, String> {
    let original = crate::rows::load(&run.core)?;
    let traces = crate::traces::analyze(&run.core, &original);
    let (done, mut completion) = crate::clock_completion::completion(&run.core, &traces)?;
    let clock = crate::native_clock::analyze(&run.core, &done)?;
    let channels = crate::clock_completion::channels(
        &run.core,
        "markers differ from actual selected source schedule.",
    );
    let (source_receipts, publication) =
        crate::native_runtime::analyze(&mut run.core, &run.contract.policy.native())?;
    let mut source = traces.source.clone();
    source.extend(source_receipts);
    source.extend(crate::checker_receipt::checker(&run.core, &traces)?);
    let reset = crate::reset::analyze(&run.core, &original)?;
    let checker = crate::public_checker::verify(run)?;
    source.extend(checker.source);
    completion.extend(publication);
    completion.extend(reset);
    completion.extend(checker.completion);
    let component = crate::public_capture::analyze(&run.core);
    let mut capture = component.findings;
    capture.extend(traces.joins);
    capture.extend(channels);
    capture.extend(traces.service);
    let oracle_equal = traces.numerical.is_empty();
    let mut numerical = traces.numerical;
    numerical.extend(checker.numerical);
    Ok(Dimensions {
        source,
        capture,
        numerical,
        completion,
        clock,
        capture_report: component.report,
        raw_spikes: traces.raw_spikes,
        services: traces.services,
        oracle_equal,
        executed: checker.executed,
    })
}

/// The source binding block: findings, admitted identity, receipts and original inputs.
fn source_binding(run: &PublicRun, source: Vec<String>) -> Value {
    let sources: BTreeMap<_, _> = run
        .core
        .sources
        .iter()
        .map(|(name, raw)| (name.clone(), identity(raw)))
        .collect();
    let inputs: BTreeMap<_, _> = run
        .core
        .files
        .iter()
        .filter(|(name, _)| {
            !["input", "state", "service"].iter().any(|role| {
                ["capture", "payload", "markers"]
                    .iter()
                    .any(|kind| **name == format!("{role}_{kind}"))
            })
        })
        .map(|(name, raw)| (name.clone(), identity(raw)))
        .collect();
    let checker_receipts: BTreeMap<_, Value> = ["generate", "check"]
        .into_iter()
        .map(|operation| {
            let raw = &run.core.files[&format!("fresh_checker_{operation}_execution_receipt")];
            (operation, admitted(raw))
        })
        .collect();
    let compiled = admitted(&run.core.files["compiler_simulator_runtime"]);
    let source_identity = [
        crate::public_policy::ID,
        crate::public_manifest::SCHEMA_SHA256,
        crate::public_policy::COHORT,
        &digest(&run.contract.policy_bytes),
    ];
    json!({
        "pass":source.is_empty(),"findings":source,
        "source_contract_ref":run.source_contract_ref,"admitted_source_identity":source_identity,
        "tool_receipt":run.tool,"compiled_runtime":compiled,
        "checker_invocations":checker_receipts,"original_sources":sources,"original_inputs":inputs,
    })
}

/// The completion block: findings, epoch, declared completion and actual receipts.
fn completion(run: &PublicRun, completion: Vec<String>) -> Result<Value, String> {
    let actual_done = admitted(&run.core.files["actual_completion"]);
    let reset_receipt: Option<Value> = run
        .core
        .files
        .get("reset_epoch_receipt")
        .map(|raw| admitted(raw));
    Ok(json!({
        "pass":completion.is_empty(),"findings":completion,"epoch":run.core.manifest.epoch,
        "declared":decode::<Value>(&run.core.files["manifest"],"original public root")?["completion"],
        "actual_receipt":actual_done,"reset_receipt":reset_receipt,
    }))
}
