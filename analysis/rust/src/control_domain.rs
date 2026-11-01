// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — cross-field rules of the measurement-domain contract

//! Apply the cross-field rules of a schema-valid measurement-domain contract.
//!
//! The rules and their finding texts are those of the Python
//! `validate_measurement_domain.semantic_findings`, in its order: identity,
//! evidence maturity, event record, timebase, event profiles, event buffer and
//! controller placements. Numbers keep Python's arithmetic and text through
//! [`Num`], so an integral float such as `16.0` behaves and prints as in Python.

use crate::control_number::{Num, python_number};
use serde_json::Value;
use std::cmp::Ordering;
use std::collections::{BTreeMap, BTreeSet};

/// The project a run-bound domain must name.
const PROJECT: &str = "LOOP-TIMING-WITNESS";
/// The group a run-bound domain must name.
const GROUP: &str = "SC-NEUROMORPHIC-COMPUTING-SYSTEMS";
/// Fields every event record must declare.
const REQUIRED_RECORD_FIELDS: [&str; 3] = ["cycle", "event_type", "timebase_ticks"];
/// The profile whose sample rate bounds a control loop.
const PERIODIC_PROFILE: &str = "CONTROL";

/// Return every cross-field finding of a schema-valid domain, in Python's order.
pub(crate) fn semantic_findings(domain: &Value) -> Vec<String> {
    let contracts = &domain["design_contracts"];
    let mut findings = identity(domain);
    findings.extend(evidence(domain));
    findings.extend(record(contracts));
    findings.extend(timebase(contracts));
    findings.extend(profiles(contracts));
    findings.extend(buffer(contracts));
    findings.extend(placements(contracts));
    findings
}

/// The text of a schema-checked string member.
fn text(value: &Value) -> &str {
    value.as_str().expect("schema-checked string")
}

/// The items of a schema-checked array member.
fn items(value: &Value) -> &[Value] {
    value.as_array().expect("schema-checked array")
}

/// Python's `repr` of a string matched by a schema identifier pattern.
fn quoted(value: &str) -> String {
    format!("'{value}'")
}

/// Tell whether any text occurs twice.
fn repeated<'a>(names: impl IntoIterator<Item = &'a str>) -> bool {
    let mut seen = BTreeSet::new();
    names.into_iter().any(|name| !seen.insert(name))
}

/// Check project, group and canonical-path agreement.
fn identity(domain: &Value) -> Vec<String> {
    let mut findings = Vec::new();
    let (project, group) = (text(&domain["project"]), text(&domain["group"]));
    if project != PROJECT {
        findings.push(format!("project: must be {}", quoted(PROJECT)));
    }
    if group != GROUP {
        findings.push(format!("group: must be {}", quoted(GROUP)));
    }
    let expected = format!("03_CODE/{group}/repositories/{project}");
    if text(&domain["canonical_path"]) != expected {
        findings.push(format!("canonical_path: must be {}", quoted(&expected)));
    }
    let related: Vec<&str> = items(&domain["related_projects"])
        .iter()
        .map(|entry| text(&entry["project"]))
        .collect();
    if repeated(related.iter().copied()) {
        findings.push("related_projects: project names must be unique".to_owned());
    }
    if related.contains(&project) {
        findings.push("related_projects: must not name the project itself".to_owned());
    }
    findings
}

/// Check the evidence-maturity truth rules of `architecture_only`.
fn evidence(domain: &Value) -> Vec<String> {
    let mut findings = Vec::new();
    if !items(&domain["capabilities"]).is_empty() {
        findings.push("capabilities: must be [] at architecture_only".to_owned());
    }
    if !items(&domain["claims"]).is_empty() {
        findings.push("claims: must be [] at architecture_only".to_owned());
    }
    if domain["target_platform"]["verified_on_hardware"] == Value::Bool(true) {
        findings.push(
            "target_platform.verified_on_hardware: must be false at architecture_only".to_owned(),
        );
    }
    findings
}

/// The width in bytes of a schema-checked field type.
fn width(kind: &Value) -> Num {
    Num::Int(match text(kind) {
        "u8" => 1,
        "u16" => 2,
        "u32" => 4,
        _ => 8,
    })
}

/// Check the binary event-record layout.
fn record(contracts: &Value) -> Vec<String> {
    let record = &contracts["event_record"];
    let fields = items(&record["fields"]);
    let names: Vec<&str> = fields.iter().map(|item| text(&item["name"])).collect();
    let mut findings = Vec::new();
    if repeated(names.iter().copied()) {
        findings.push("event_record.fields: names must be unique".to_owned());
    }
    for required in REQUIRED_RECORD_FIELDS {
        if !names.contains(&required) {
            findings.push(format!(
                "event_record.fields: missing required field {}",
                quoted(required)
            ));
        }
    }
    let mut expected = Num::Int(0);
    for item in fields {
        let offset = Num::of(&item["offset_bytes"]);
        if !offset.same(expected) {
            findings.push(format!(
                "event_record.fields.{}: offset must be {expected} (fields are contiguous and ordered)",
                text(&item["name"])
            ));
        }
        expected = offset.add(width(&item["type"]));
    }
    if !expected.same(Num::of(&record["record_size_bytes"])) {
        findings.push(format!(
            "event_record: fields end at byte {expected}, record size is {}",
            python_number(&record["record_size_bytes"])
        ));
    }
    let widths: BTreeMap<&str, Num> = fields
        .iter()
        .map(|item| (text(&item["name"]), width(&item["type"])))
        .collect();
    let cycles = Num::of(&contracts["run_plan"]["cycles_per_repeat"]);
    if let Some(cycle) = widths.get("cycle")
        && cycles.compare(Num::Int(8).mul(*cycle).power_of_two()) == Ordering::Greater
    {
        findings.push(format!(
            "event_record.fields.cycle: {cycles} cycles per repeat do not fit its width"
        ));
    }
    let counter = Num::of(&contracts["timebase"]["counter_bits"]);
    if let Some(ticks) = widths.get("timebase_ticks")
        && Num::Int(8).mul(*ticks).compare(counter) == Ordering::Less
    {
        findings.push(
            "event_record.fields.timebase_ticks: narrower than the timebase counter".to_owned(),
        );
    }
    findings
}

/// Check clock resolution and counter wrap against the run plan.
fn timebase(contracts: &Value) -> Vec<String> {
    let timebase = &contracts["timebase"];
    let clock = Num::of(&timebase["clock_hz"]);
    let mut findings = Vec::new();
    if !Num::of(&timebase["resolution_ns"])
        .mul(clock)
        .same(Num::Int(1_000_000_000))
    {
        findings.push("timebase.resolution_ns: must equal one clock period".to_owned());
    }
    let control = &contracts["event_profiles"][PERIODIC_PROFILE]["sample_rate_hz"];
    if !control.is_null() {
        let run_ticks = Num::of(&contracts["run_plan"]["cycles_per_repeat"]).mul(clock);
        let wrap = Num::of(&timebase["counter_bits"])
            .power_of_two()
            .mul(Num::of(&control["minimum"]));
        if wrap.compare(run_ticks) != Ordering::Greater {
            findings.push("timebase.counter_bits: the counter wraps within one repeat at the minimum sample rate".to_owned());
        }
    }
    findings
}

/// Every event name of a profile, periodic before occasional.
fn profile_events(profile: &Value) -> impl Iterator<Item = &str> {
    items(&profile["periodic_events"])
        .iter()
        .chain(items(&profile["occasional_events"]))
        .map(text)
}

/// Check event-profile consistency and sample-rate bounds.
fn profiles(contracts: &Value) -> Vec<String> {
    let profiles = contracts["event_profiles"]
        .as_object()
        .expect("schema-checked object");
    let all: Vec<&str> = profiles.values().flat_map(profile_events).collect();
    let codes = contracts["event_codes"]
        .as_object()
        .expect("schema-checked object");
    let mut findings = Vec::new();
    if codes.keys().map(String::as_str).collect::<BTreeSet<_>>() != all.iter().copied().collect() {
        findings
            .push("event_codes: names must match the declared profile events exactly".to_owned());
    }
    let numbers: Vec<Num> = codes.values().map(Num::of).collect();
    if numbers
        .iter()
        .enumerate()
        .any(|(index, code)| numbers[..index].iter().any(|earlier| earlier.same(*code)))
    {
        findings.push("event_codes: numeric codes must be unique".to_owned());
    }
    let duplicated: BTreeSet<&str> = all
        .iter()
        .copied()
        .filter(|name| all.iter().filter(|other| *other == name).count() > 1)
        .collect();
    if !duplicated.is_empty() {
        let listed: Vec<String> = duplicated.iter().map(|name| quoted(name)).collect();
        findings.push(format!(
            "event_profiles: event names must be unique across profiles: [{}]",
            listed.join(", ")
        ));
    }
    for (name, profile) in profiles {
        findings.extend(intervals(name, profile));
        let rate = &profile["sample_rate_hz"];
        if !rate.is_null() {
            let (minimum, default, maximum) = (
                Num::of(&rate["minimum"]),
                Num::of(&rate["default"]),
                Num::of(&rate["maximum"]),
            );
            if minimum.compare(default) == Ordering::Greater
                || default.compare(maximum) == Ordering::Greater
            {
                findings.push(format!(
                    "event_profiles.{name}.sample_rate_hz: requires minimum <= default <= maximum"
                ));
            }
        }
    }
    if profiles[PERIODIC_PROFILE]["sample_rate_hz"].is_null() {
        findings.push(format!("event_profiles.{PERIODIC_PROFILE}.sample_rate_hz: a control loop needs sample-rate bounds"));
    }
    findings
}

/// Check that every interval of one profile joins two of its own events.
fn intervals(name: &str, profile: &Value) -> Vec<String> {
    let events: BTreeSet<&str> = profile_events(profile).collect();
    let declared = items(&profile["intervals"]);
    let mut findings = Vec::new();
    if repeated(declared.iter().map(|interval| text(&interval["name"]))) {
        findings.push(format!("event_profiles.{name}: interval names repeat"));
    }
    for interval in declared {
        let label = format!(
            "event_profiles.{name}.intervals.{}",
            text(&interval["name"])
        );
        for end in ["start_event", "end_event"] {
            let event = text(&interval[end]);
            if !events.contains(event) {
                findings.push(format!(
                    "{label}: {end} {} is not an event of this profile",
                    quoted(event)
                ));
            }
        }
        if interval["start_event"] == interval["end_event"] {
            findings.push(format!("{label}: start and end events must differ"));
        }
    }
    findings
}

/// Check the Gray-pointer depth and that the buffer outlasts the slowest drain.
fn buffer(contracts: &Value) -> Vec<String> {
    let fifo = &contracts["event_fifo"];
    let depth = Num::of(&fifo["depth_records"]);
    let mut findings = Vec::new();
    if fifo.get("implementation").and_then(Value::as_str) == Some("gray_pointer_dual_clock") {
        let whole = match depth {
            Num::Int(integer) => integer,
            Num::Float(float) => float as u128,
        };
        if !(2..=16_384).contains(&whole) || !whole.is_power_of_two() {
            findings.push(
                "event_fifo: Gray-pointer depth must be a power of two in [2,16384]".to_owned(),
            );
        }
    }
    let drain = depth.mul(Num::of(&fifo["minimum_drain_rate_hz"]));
    let profiles = contracts["event_profiles"]
        .as_object()
        .expect("schema-checked object");
    for (name, profile) in profiles {
        let rate = &profile["sample_rate_hz"];
        if rate.is_null() {
            continue;
        }
        let count = items(&profile["periodic_events"]).len() as u128;
        if drain.compare(Num::of(&rate["maximum"]).mul(Num::Int(count))) != Ordering::Greater {
            findings.push(format!(
                "event_fifo: fills before the slowest drain at the {name} maximum sample rate"
            ));
        }
    }
    findings
}

/// Check that controller placement identifiers are unique.
fn placements(contracts: &Value) -> Vec<String> {
    let identifiers = items(&contracts["controller_placements"])
        .iter()
        .map(|item| text(&item["identifier"]));
    if repeated(identifiers) {
        vec!["controller_placements: identifiers must be unique".to_owned()]
    } else {
        Vec::new()
    }
}

#[cfg(test)]
#[path = "../tests/unit/control_domain.rs"]
mod tests;
