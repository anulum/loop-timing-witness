// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — the dedicated-hart logger's counters in a run report

//! Attach an AMP run's logger completion to its report as the Python
//! function `amp_report_completion.attach_amp_completion` does.
//!
//! The capture is admitted with every artifact it binds; the run's
//! declaration is held to the capture, the run configuration and the observed
//! tracking; the logger's counters are held to the full captured event
//! history; then the report gains the completion, the capture's digest and
//! the functional clock limit. Every refusal and read error is Python's
//! text, as the command prints it.

use crate::amp_capture::admitted_capture;
use crate::amp_completion::{AmpCompletion, completion_receipt};
use crate::amp_failure::AmpFailure;
use crate::amp_files::file_bytes;
use crate::amp_observations::{fault_schedule, tracking_csv};
use crate::amp_run_input::{AmpRun, read_amp_run};
use crate::control_analysis::full_control;
use crate::control_events::Event;
use crate::control_manifest::Failure;
use crate::control_number::Num;
use crate::control_paths::pure;
use crate::control_receipts::python_equal;
use serde_json::{Map, Value, json};
use std::collections::BTreeMap;
use std::path::Path;

/// The run contract's coefficient names, in `witness_coefficients` order.
const COEFFICIENT_NAMES: [&str; 11] = [
    "kp",
    "ki_period",
    "derivative_decay",
    "derivative_gain",
    "position_gain",
    "velocity_gain",
    "reference_gain",
    "output_min",
    "output_max",
    "integral_min",
    "integral_max",
];

/// A capture's read error or refusal as the report's failure: Python's
/// `OSError` stays a read error, which a campaign does not take for a refused
/// repeat.
fn classified(failure: AmpFailure) -> Failure {
    match failure {
        AmpFailure::Os(text) => Failure::Os(text),
        AmpFailure::Refused(text) => Failure::Refused(text),
    }
}

/// What the run declaration is held to: the admitted capture, the logger
/// completion, the run configuration's bytes and its run.
struct Admitted<'a> {
    capture: &'a Map<String, Value>,
    completion: AmpCompletion,
    configuration: &'a [u8],
    run: AmpRun,
}

/// The controller name and coefficients a run configures, as the run
/// contract declares them.
fn controller(run: &AmpRun) -> (Value, Value) {
    let coefficients: Map<String, Value> = COEFFICIENT_NAMES
        .iter()
        .zip(run.coefficients)
        .map(|(name, value)| ((*name).to_owned(), json!(value)))
        .collect();
    (
        json!(if run.lqr { "lqr" } else { "pid" }),
        Value::Object(coefficients),
    )
}

/// The plant the running RTL reported.
fn plant(completion: &AmpCompletion) -> Value {
    json!(if completion.thermal {
        "first_order_thermal"
    } else {
        "second_order_mechanical"
    })
}

/// Hold the run declaration to the admitted capture, configuration and
/// tracking, in Python's order; the tracking is read only when reached.
///
/// Python also compares the placement and the source kind; the run schema
/// fixes both for a run that binds a capture, so they always agree here.
fn declared(
    manifest: &Map<String, Value>,
    files: &BTreeMap<String, Vec<u8>>,
    directory: &Path,
    admitted: &Admitted<'_>,
) -> Result<bool, Failure> {
    let (capture, completion, run) = (admitted.capture, admitted.completion, admitted.run);
    let (name, coefficients) = controller(&run);
    let tracking = || {
        let raw = file_bytes(&pure(&directory.join("tracking_raw.csv"))).map_err(classified)?;
        tracking_csv(&raw, run.cycles, completion.samples).map_err(Failure::Refused)
    };
    let same = |value: &Value, expected: &Value| python_equal(value, expected);
    let captured = &capture["files"];
    Ok(same(&manifest["started_utc"], &capture["started_utc"])
        && same(&manifest["cycle_count"], &json!(run.cycles))
        && same(&manifest["sample_period_ticks"], &json!(run.period_ticks))
        && same(&manifest["controller"]["name"], &name)
        && same(&manifest["controller"]["coefficients"], &coefficients)
        && same(
            &manifest["fault_schedule"],
            &fault_schedule(admitted.configuration)?,
        )
        && files["tracking"] == tracking()?
        && same(
            &manifest["measurement_domain"]["sha256"],
            &captured["measurement-domain.json"],
        )
        && same(&manifest["plant"]["fixed_point_format"], &json!("Q8.24"))
        && same(&manifest["plant"]["tracking_unit"], &json!("model_output"))
        && same(&manifest["plant"]["name"], &plant(&completion))
        && same(
            &manifest["files"]["events"]["sha256"],
            &captured["events.bin"],
        ))
}

/// Hold the logger's counters to the full captured event history.
///
/// Python also compares the event count and the sampled cycles' count. The
/// declaration check has bound the run's events to the captured events'
/// digest and cycle count, and the capture check has held those events and
/// the observed tracking to both counts, so they always agree here.
fn counters_agree(
    manifest: &Map<String, Value>,
    contracts: &Value,
    events: &[Event],
    completion: &AmpCompletion,
    run: &AmpRun,
) -> Result<bool, String> {
    let control = full_control(events, contracts, Num::Int(u128::from(run.cycles)))?;
    let overflow = &manifest["instrument"]["fifo_overflow_count"];
    Ok(python_equal(&json!(completion.overflow), overflow)
        && python_equal(&json!(completion.misses), &control["deadline_misses"])
        && python_equal(&control["observed_deadlines"], &json!(run.cycles))
        && completion.safe == Num::of(&control["safe_state_events"]).truthy())
}

/// Attach the logger completion of a run that binds an AMP capture.
///
/// A run without a capture is left unchanged. `directory` is the resolved
/// manifest directory, which every native run carries, so Python's refusal
/// of a run without one has no counterpart here.
pub(crate) fn attach_amp_completion(
    manifest: &Map<String, Value>,
    contracts: &Value,
    files: &BTreeMap<String, Vec<u8>>,
    directory: &Path,
    events: &[Event],
    report: &mut Map<String, Value>,
) -> Result<(), Failure> {
    let Some(content) = files.get("amp_capture") else {
        return Ok(());
    };
    let capture = admitted_capture(directory, content).map_err(classified)?;
    let read = |name: &str| file_bytes(&pure(&directory.join(name))).map_err(classified);
    let completion = completion_receipt(&read("spike.log")?)?;
    let configuration = read("image/configuration.txt")?;
    let run = read_amp_run(&configuration)?;
    let admitted = Admitted {
        capture: &capture,
        completion,
        configuration: &configuration,
        run,
    };
    if !declared(manifest, files, directory, &admitted)? {
        return Err(Failure::Refused(
            "AMP capture configuration does not match the run declaration".to_owned(),
        ));
    }
    if !counters_agree(manifest, contracts, events, &completion, &run)? {
        return Err(Failure::Refused(
            "AMP completion counters do not match captured events".to_owned(),
        ));
    }
    report.insert("amp_completion".to_owned(), capture["completion"].clone());
    report["input_sha256"]["amp_capture"] = manifest["amp_capture"]["sha256"].clone();
    report["limits"]
        .as_array_mut()
        .expect("the report's limits")
        .push(json!(
            "ISA functional clock mapping does not establish physical U54 execution latency."
        ));
    Ok(())
}
