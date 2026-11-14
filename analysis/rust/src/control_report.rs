// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — complete control-run report

//! The complete per-run report, as Python's `analyze_run.build_report` builds it.
//!
//! The events block, the tracking and energy series, validity, the input
//! digests and the stated limits are assembled in Python's order, so the first
//! refusal is Python's too. The native completion counters and the host load
//! receipt are attached when the run binds them. A run that binds an AMP
//! capture is refused first, until the native analysis implements AMP completion.

use crate::amp_report_completion::attach_amp_completion;
use crate::control_analysis::{Row, events_block, full_control, whole};
use crate::control_events::{Event, Names, decode};
use crate::control_number::{Num, python_number};
use crate::control_receipts::{completion_statistics, host_load, native_metadata, python_equal};
use crate::control_series::{energy_per_cycle, observed_tracking_error, tracking_error};
use serde_json::{Map, Value, json};
use std::collections::BTreeMap;
use std::path::Path;

/// Report schema identifier.
const REPORT_SCHEMA: &str = "loop-timing-witness.analysis-report.v1";
/// The refusal of a campaign whose runs bind an AMP capture, which the native campaign does not
/// analyse.
pub(crate) const AMP_UNSUPPORTED: &str =
    "AMP capture completion is not analysed by the native analysis";
/// Hardware artefacts whose digests a board report lists.
const HARDWARE: [&str; 4] = ["bitstream", "firmware", "linux_image", "controller_binary"];
/// The limit stated when the event FIFO overflowed.
const OVERFLOW_LIMIT: &str = "FIFO overflow can remove actuator or deadline records; captured-event \
                              deadline misses do not establish actual controller misses.";
/// The limit stated with a host load receipt.
const HOST_LOAD_LIMIT: &str = "Host load counters cover the whole worker span, including work before \
                               and after the enclosed native interval. Host monotonic time is not \
                               fabric event time. Loopback UDP does not measure NIC traffic; file \
                               fsync does not establish uncached block-device load. Host stress does \
                               not qualify processor timing or power.";

/// The report and interval rows of one validated run.
pub(crate) fn build_report(
    manifest: &Map<String, Value>,
    domain: &Value,
    files: &BTreeMap<String, Vec<u8>>,
    directory: &Path,
) -> Result<(Value, Vec<Row>), String> {
    let contracts = &domain["design_contracts"];
    let names = Names::of(contracts);
    let profile = manifest["profile"]
        .as_str()
        .expect("schema-checked profile");
    let cycle_count = Num::of(&manifest["cycle_count"]);
    let warmup = Num::of(&manifest["warmup_cycles"]);
    let events = decode(&files["events"], contracts, profile, cycle_count)?;
    let (mut summary, rows) = events_block(manifest, contracts, &events)?;
    let (cycles, first) = (
        u64::try_from(whole(cycle_count)).unwrap_or(u64::MAX),
        u64::try_from(whole(warmup)).unwrap_or(u64::MAX),
    );
    let unit = manifest["plant"]["tracking_unit"]
        .as_str()
        .unwrap_or_default();
    let mut tracking = if manifest.get("tracking_sampling") == Some(&json!("observed")) {
        observed_tracking_error(&files["tracking"], &events, &names, cycles, first, unit)?
    } else if profile == "CONTROL" {
        tracking_error(
            files.get("tracking").map(Vec::as_slice),
            cycles,
            first,
            unit,
        )?
    } else {
        object(json!({"status": "not_applicable", "reason": "COMPUTE has no control plant"}))
    };
    let rails: Vec<&str> = contracts["power_rails"]
        .as_array()
        .expect("schema-checked rails")
        .iter()
        .map(|rail| rail.as_str().expect("schema-checked rail"))
        .collect();
    let mut energy = energy_per_cycle(
        files.get("power").map(Vec::as_slice),
        &events,
        &names,
        profile,
        first,
        &rails,
    )?;
    let duration = summary["duration_ticks"].clone();
    tracking.insert("duration_ticks".to_owned(), duration.clone());
    energy.insert("duration_ticks".to_owned(), duration);
    tracking.entry("sample_count").or_insert(json!(0));
    if energy["status"] == "unavailable" {
        energy.insert("sample_count".to_owned(), json!(0));
    }
    let anchors = if profile == "CONTROL" {
        summary["control"]["observed_deadlines"].clone()
    } else {
        json!(
            events
                .iter()
                .filter(|event| names.get(event.code) == Some("INPUT_WRITE")
                    && u64::from(event.cycle) >= first)
                .count()
        )
    };
    let complete = python_equal(&anchors, &summary["cycle_count"]);
    let overflow = &manifest["instrument"]["fifo_overflow_count"];
    let missing_tracking = profile == "CONTROL" && tracking["status"] != "available";
    let missing_energy = energy["status"] != "available";
    let valid = complete && !Num::of(overflow).truthy() && !missing_tracking && !missing_energy;
    let mut reasons = Vec::new();
    if Num::of(overflow).truthy() {
        reasons.push("event FIFO overflow");
    }
    if !complete {
        reasons.push("missing cycle anchor events");
    }
    if tracking["status"] == "partial" {
        reasons.push("tracking series incomplete");
    } else if missing_tracking {
        reasons.push("tracking series unavailable");
    }
    if missing_energy {
        reasons.push("power series unavailable");
    }
    let resolution = &contracts["timebase"]["resolution_ns"];
    let mut limits = vec![
        format!(
            "Timebase ticks resolve {} ns; interconnect offsets require calibration.",
            python_number(resolution)
        ),
        "The plant is emulated; these are not physical-machine control results.".to_owned(),
        "Power rails share processor and fabric consumption. Energy is a window mean.".to_owned(),
    ];
    if tracking.get("sampling") == Some(&json!("observed")) {
        limits.push(
            "Tracking errors describe observed cycles only; missing samples may bias the metric."
                .to_owned(),
        );
    }
    let source_kind = &manifest["source"]["kind"];
    let mut report = object(json!({
        "schema": REPORT_SCHEMA,
        "run_id": manifest["run_id"],
        "started_utc": manifest["started_utc"],
        "source_kind": source_kind,
        "evidence_status": if source_kind == "rtl_simulation" {
            "simulation_only"
        } else {
            "board_declaration_unverified"
        },
        "profile": profile,
        "placement": manifest["placement"],
        "measurement_domain_sha256": manifest["measurement_domain"]["sha256"],
        "input_sha256": input_hashes(manifest),
        "timebase_resolution_ns": resolution,
        "instrument_floor_ticks": manifest["instrument"]["floor_ticks"],
        "fifo_overflow_count": overflow,
        "valid": valid,
        "invalid_reasons": reasons,
        "events": Value::Null,
        "tracking_error": tracking,
        "energy": energy,
        "limits": limits,
    }));
    report.insert("events".to_owned(), std::mem::take(&mut summary));
    attach_completion(manifest, contracts, files, &events, &names, &mut report)?;
    attach_amp_completion(manifest, contracts, files, directory, &events, &mut report)?;
    attach_host_load(manifest, files, &mut report)?;
    Ok((Value::Object(report), rows))
}

/// Input digests by name: declared files, the measurement domain, source files
/// and board artefacts, later names replacing earlier ones as in Python.
fn input_hashes(manifest: &Map<String, Value>) -> Map<String, Value> {
    let mut hashes = Map::new();
    for (name, item) in manifest["files"].as_object().expect("schema-checked files") {
        if !item.is_null() {
            hashes.insert(name.clone(), item["sha256"].clone());
        }
    }
    hashes.insert(
        "measurement_domain".to_owned(),
        manifest["measurement_domain"]["sha256"].clone(),
    );
    for item in manifest["source"]["files"]
        .as_array()
        .expect("schema-checked sources")
    {
        let path = item["path"].as_str().expect("schema-checked path");
        hashes.insert(format!("source:{path}"), item["sha256"].clone());
    }
    let hardware = &manifest["hardware_artifacts"];
    if !hardware.is_null() {
        for name in HARDWARE {
            hashes.insert(name.to_owned(), hardware[name]["sha256"].clone());
        }
    }
    hashes
}

/// Attach the native completion counters and the overflow limit, as Python's
/// `attach_completion_statistics`.
fn attach_completion(
    manifest: &Map<String, Value>,
    contracts: &Value,
    files: &BTreeMap<String, Vec<u8>>,
    events: &[Event],
    names: &Names,
    report: &mut Map<String, Value>,
) -> Result<(), String> {
    if let Some(content) = files.get("native_metadata") {
        let control = if Num::of(&manifest["warmup_cycles"]).truthy() {
            full_control(events, contracts, Num::of(&manifest["cycle_count"]))?
        } else {
            report["events"]["control"].clone()
        };
        let reads = events
            .iter()
            .filter(|event| names.get(event.code) == Some("SAMPLE_READ"))
            .count();
        let result = completion_statistics(content, manifest, events.len(), &control, reads)?;
        report.insert("native_completion".to_owned(), result);
        report["input_sha256"]
            .as_object_mut()
            .expect("input digests")
            .insert(
                "native_metadata".to_owned(),
                manifest["native_metadata"]["sha256"].clone(),
            );
    }
    if Num::of(&report["fifo_overflow_count"]).truthy() {
        push_limit(report, OVERFLOW_LIMIT);
    }
    Ok(())
}

/// Attach the host load receipt and its limit, as Python's `attach_host_load`.
fn attach_host_load(
    manifest: &Map<String, Value>,
    files: &BTreeMap<String, Vec<u8>>,
    report: &mut Map<String, Value>,
) -> Result<(), String> {
    let Some(content) = files.get("host_load") else {
        return Ok(());
    };
    let receipt = host_load(content)?;
    let native = native_metadata(&files["native_metadata"])?;
    let exit = i64::from(Num::of(&native["result"]["overflow"]).truthy());
    if manifest["load_case"] != receipt["profile"]
        || !python_equal(&receipt["native_returncode"], &json!(exit))
    {
        return Err("host load profile or native exit status contradicts the capture".to_owned());
    }
    report.insert("host_load".to_owned(), receipt);
    report["input_sha256"]
        .as_object_mut()
        .expect("input digests")
        .insert(
            "host_load".to_owned(),
            manifest["host_load"]["sha256"].clone(),
        );
    push_limit(report, HOST_LOAD_LIMIT);
    Ok(())
}

/// Append one stated limit.
fn push_limit(report: &mut Map<String, Value>, limit: &str) {
    report["limits"]
        .as_array_mut()
        .expect("limits")
        .push(json!(limit));
}

/// The object of a JSON object literal.
fn object(value: Value) -> Map<String, Value> {
    value.as_object().cloned().expect("object literal")
}

#[cfg(test)]
#[path = "../tests/unit/control_report.rs"]
mod tests;
