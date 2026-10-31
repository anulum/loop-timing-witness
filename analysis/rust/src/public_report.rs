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
    let checker = crate::public_checker::verify(&mut run)?;
    source.extend(checker.source);
    completion.extend(publication);
    completion.extend(reset);
    completion.extend(checker.completion);
    let component = crate::public_capture::analyze(&run.core);
    let mut capture_findings = component.findings;
    capture_findings.extend(traces.joins);
    capture_findings.extend(channels);
    capture_findings.extend(traces.service);
    let mut numerical = traces.numerical.clone();
    numerical.extend(checker.numerical);
    let whole = [&source, &capture_findings, &numerical, &completion, &clock]
        .iter()
        .all(|findings| findings.is_empty());
    let verification = json!({
        "source_binding":dimension(&source),"capture":dimension(&capture_findings),
        "numerical":dimension(&numerical),"completion":dimension(&completion),"clock":dimension(&clock),
        "whole":whole,
    });
    let mut capture = component.report;
    capture["pass"] = Value::Bool(capture_findings.is_empty());
    capture["findings"] = json!(capture_findings);
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
    let actual_done = admitted(&run.core.files["actual_completion"]);
    let clock_schedule = admitted(&run.core.files["clock_schedule_ref"]);
    let reset_receipt: Option<Value> = run
        .core
        .files
        .get("reset_epoch_receipt")
        .map(|raw| admitted(raw));
    let source_identity = [
        crate::public_policy::ID,
        crate::public_manifest::SCHEMA_SHA256,
        crate::public_policy::COHORT,
        &digest(&run.contract.policy_bytes),
    ];
    Ok(json!({
        "schema_id":"loop-timing-witness.neural-step-analysis-report.v1",
        "profile":run.core.manifest.profile,"evidence_class":run.core.manifest.evidence_class,
        "run_id":run.core.manifest.run_id,
        "source_binding":{
            "pass":source.is_empty(),"findings":source,
            "source_contract_ref":run.source_contract_ref,"admitted_source_identity":source_identity,
            "tool_receipt":run.tool,"compiled_runtime":compiled,
            "checker_invocations":checker_receipts,"original_sources":sources,"original_inputs":inputs,
        },
        "capture":capture,
        "numerical":{
            "pass":numerical.is_empty(),"findings":numerical,
            "requested_steps":run.core.manifest.step_count,"actual_raw_spikes":traces.raw_spikes,
            "actual_service_packets":traces.services,
            "original_oracle_equal":traces.numerical.is_empty(),
            "source_checker_executed":checker.executed,
        },
        "completion":{
            "pass":completion.is_empty(),"findings":completion,"epoch":run.core.manifest.epoch,
            "declared":decode::<Value>(&run.core.files["manifest"],"original public root")?["completion"],
            "actual_receipt":actual_done,"reset_receipt":reset_receipt,
        },
        "clock":{"pass":clock.is_empty(),"findings":clock,"actual_schedule":clock_schedule},
        "verification":verification,
        "limits":[
            "Capture ticks are simulator edges; physical timing and calibration are unavailable.",
            "File integrity and correspondence do not authenticate a remote producer.",
            "This verdict covers the selected single-neuron source cohort and full original acquisition.",
            "A passing run does not establish model-family, physical or whole-project acceptance.",
        ],
    }))
}
