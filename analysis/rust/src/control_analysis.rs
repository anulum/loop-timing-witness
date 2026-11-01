// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — interval, deadline, fault and jitter statistics of one run

//! Build the `events` block of a run report as the Python analysis does.
//!
//! The steps are those of the Python `analyze_run.events_block`: the captured
//! fault injections must match the fault schedule; same-cycle intervals,
//! deadlines, fault detection and safe-state times are taken from the analysed
//! cycles; adjacent-cycle jitter pairs the same interval in consecutive
//! cycles. Distributions use Type-7 quantiles with Python's floating-point
//! operations in Python's order, and counts derived from the declared cycles
//! keep Python's integer or float type.

use crate::control_events::{Event, Names};
use crate::control_number::Num;
use serde_json::{Map, Value, json};
use std::cmp::Ordering;

/// The jitter definition named in every report.
pub(crate) const JITTER_METHOD: &str = "absolute_cycle_to_cycle_latency_change.v1";

/// One same-cycle interval observation.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Row {
    /// Analysed cycle.
    pub(crate) cycle: u32,
    /// Interval name.
    pub(crate) interval: String,
    /// Length in clock ticks.
    pub(crate) ticks: u64,
}

/// Interval samples by name, in declaration order.
type Samples = Vec<(String, Vec<u64>)>;

/// Event ticks of one cycle, by event name.
struct Cycle {
    number: u32,
    ticks: Vec<(String, u64)>,
}

impl Cycle {
    /// The tick of one named event in this cycle.
    fn get(&self, name: &str) -> Option<u64> {
        self.ticks
            .iter()
            .find(|(event, _)| event == name)
            .map(|&(_, ticks)| ticks)
    }
}

/// Return a Type-7 distribution of clock-tick samples, as Python's `distribution`.
pub(crate) fn distribution(values: &[u64]) -> Map<String, Value> {
    let mut result = Map::new();
    result.insert("sample_count".to_owned(), json!(values.len()));
    let names = ["median_ticks", "p95_ticks", "p99_ticks", "p999_ticks"];
    if values.is_empty() {
        for name in names.into_iter().chain(["maximum_ticks"]) {
            result.insert(name.to_owned(), Value::Null);
        }
        return result;
    }
    let mut ordered = values.to_vec();
    ordered.sort_unstable();
    for (name, probability) in names.into_iter().zip([0.5, 0.95, 0.99, 0.999]) {
        let position = (ordered.len() - 1) as f64 * probability;
        let (low, high) = (position.floor(), position.ceil());
        let (lower, upper) = (ordered[low as usize], ordered[high as usize]);
        let value = lower as f64 + (upper - lower) as f64 * (position - low);
        result.insert(name.to_owned(), json!(value));
    }
    result.insert(
        "maximum_ticks".to_owned(),
        json!(ordered[ordered.len() - 1]),
    );
    result
}

/// Group decoded events into cycles in ascending order.
fn cycles(events: &[Event], names: &Names) -> Vec<Cycle> {
    let mut cycles: Vec<Cycle> = Vec::new();
    for event in events {
        if cycles
            .last()
            .is_none_or(|cycle| cycle.number != event.cycle)
        {
            cycles.push(Cycle {
                number: event.cycle,
                ticks: Vec::new(),
            });
        }
        let name = names.get(event.code).unwrap_or_default().to_owned();
        cycles
            .last_mut()
            .expect("current cycle")
            .ticks
            .push((name, event.ticks));
    }
    cycles
}

/// The text of a schema-checked string member.
fn text(value: &Value) -> &str {
    value.as_str().expect("schema-checked string")
}

/// Same-cycle intervals of the analysed cycles, with their samples by name.
fn intervals(
    cycles: &[Cycle],
    profile: &Value,
    warmup: Num,
) -> Result<(Samples, Vec<Row>), String> {
    let declared: Vec<&Value> = profile["intervals"]
        .as_array()
        .expect("schema-checked array")
        .iter()
        .filter(|interval| text(&interval["name"]) != "time_to_safe_state")
        .collect();
    let mut values: Samples = declared
        .iter()
        .map(|interval| (text(&interval["name"]).to_owned(), Vec::new()))
        .collect();
    let mut rows = Vec::new();
    for cycle in cycles {
        if Num::Int(u128::from(cycle.number)).compare(warmup) == Ordering::Less {
            continue;
        }
        for (index, interval) in declared.iter().enumerate() {
            let name = text(&interval["name"]);
            let (Some(start), Some(end)) = (
                cycle.get(text(&interval["start_event"])),
                cycle.get(text(&interval["end_event"])),
            ) else {
                continue;
            };
            let ticks = end
                .checked_sub(start)
                .ok_or_else(|| format!("cycle {}: {name} ends before it starts", cycle.number))?;
            values[index].1.push(ticks);
            rows.push(Row {
                cycle: cycle.number,
                interval: name.to_owned(),
                ticks,
            });
        }
    }
    Ok((values, rows))
}

/// Deadline and fault counts with detection and safe-state samples.
fn control(
    cycles: &[Cycle],
    warmup: Num,
    cycle_count: Num,
) -> Result<(Value, Vec<u64>, Vec<u64>), String> {
    let (first, last) = (whole(warmup), whole(cycle_count));
    let (mut misses, mut observed, mut injections) = (0_u64, 0_u64, 0_u64);
    let (mut detected, mut safe) = (Vec::new(), Vec::new());
    let (mut open, mut missed): (Option<u64>, Option<u64>) = (None, None);
    let empty = Cycle {
        number: 0,
        ticks: Vec::new(),
    };
    let mut next = cycles.iter().peekable();
    for number in first..last {
        while next
            .peek()
            .is_some_and(|cycle| u128::from(cycle.number) < number)
        {
            next.next();
        }
        let cycle = match next.peek() {
            Some(cycle) if u128::from(cycle.number) == number => *cycle,
            _ => &empty,
        };
        if let Some(injection) = cycle.get("FAULT_INJECTED") {
            injections += 1;
            if open.is_some() {
                return Err(format!(
                    "cycle {number}: fault injection overlaps an undetected fault"
                ));
            }
            open = Some(injection);
        }
        if let Some(detection) = cycle.get("FAULT_DETECTED") {
            let injection = open
                .filter(|&injection| detection >= injection)
                .ok_or_else(|| {
                    format!("cycle {number}: fault detection lacks a prior injection")
                })?;
            detected.push(detection - injection);
            open = None;
        }
        if let Some(deadline) = cycle.get("DEADLINE") {
            observed += 1;
            if cycle.get("ACT_WRITE").is_none_or(|write| write >= deadline) {
                misses += 1;
                missed = missed.or(Some(deadline));
            } else {
                missed = None;
            }
        }
        if let Some(state) = cycle.get("SAFE_STATE") {
            let deadline = missed
                .filter(|&deadline| state >= deadline)
                .ok_or_else(|| {
                    format!("cycle {number}: safe state lacks a prior missed deadline")
                })?;
            safe.push(state - deadline);
            missed = None;
        }
    }
    let rate = if observed == 0 {
        Value::Null
    } else {
        json!(misses as f64 / observed as f64)
    };
    let block = json!({
        "observed_deadlines": observed,
        "deadline_misses": misses,
        "deadline_miss_rate": rate,
        "fault_injections": injections,
        "fault_detections": detected.len(),
        "undetected_faults": injections - detected.len() as u64,
        "safe_state_events": safe.len(),
    });
    Ok((block, detected, safe))
}

/// Python `int(number)` of a schema-checked non-negative count.
fn whole(number: Num) -> u128 {
    match number {
        Num::Int(integer) => integer,
        Num::Float(float) => float as u128,
    }
}

/// Adjacent-cycle jitter distributions and pair coverage by periodic interval.
fn jitter(rows: &[Row], names: &[String], analysed: Num, duration: u64) -> Value {
    let expected = analysed.sub(Num::Int(1)).at_least_zero();
    let mut previous: Vec<(String, u32, u64)> = Vec::new();
    let mut latencies: Vec<Vec<u64>> = vec![Vec::new(); names.len()];
    let mut changes: Vec<Vec<u64>> = vec![Vec::new(); names.len()];
    for row in rows {
        let index = names
            .iter()
            .position(|name| *name == row.interval)
            .expect("declared interval");
        latencies[index].push(row.ticks);
        if let Some(entry) = previous
            .iter_mut()
            .find(|(name, _, _)| *name == row.interval)
        {
            if row.cycle == entry.1 + 1 {
                changes[index].push(row.ticks.abs_diff(entry.2));
            }
            (entry.1, entry.2) = (row.cycle, row.ticks);
        } else {
            previous.push((row.interval.clone(), row.cycle, row.ticks));
        }
    }
    let mut result = Map::new();
    for (index, name) in names.iter().enumerate() {
        let count = changes[index].len() as u64;
        let mut summary = distribution(&changes[index]);
        let status = if count == 0 {
            "unavailable"
        } else if Num::Int(u128::from(count)).same(expected) {
            "available"
        } else {
            "partial"
        };
        let samples = &latencies[index];
        let spread = match (samples.iter().max(), samples.iter().min()) {
            (Some(high), Some(low)) if samples.len() > 1 => json!(high - low),
            _ => Value::Null,
        };
        summary.insert("status".to_owned(), json!(status));
        summary.insert("latency_sample_count".to_owned(), json!(samples.len()));
        summary.insert("expected_pair_count".to_owned(), expected.json());
        summary.insert(
            "missing_pair_count".to_owned(),
            expected.sub(Num::Int(u128::from(count))).json(),
        );
        let coverage = if expected.truthy() {
            json!(expected.divide(count))
        } else {
            Value::Null
        };
        summary.insert("pair_coverage_fraction".to_owned(), coverage);
        summary.insert("duration_ticks".to_owned(), json!(duration));
        summary.insert("peak_to_peak_ticks".to_owned(), spread);
        result.insert(name.clone(), Value::Object(summary));
    }
    Value::Object(result)
}

/// Build the report's `events` block and the per-cycle interval rows.
pub(crate) fn events_block(
    manifest: &Map<String, Value>,
    contracts: &Value,
    events: &[Event],
) -> Result<(Value, Vec<Row>), String> {
    let names = Names::of(contracts);
    let mut scheduled: Vec<Num> = manifest["fault_schedule"]
        .as_array()
        .expect("schema-checked array")
        .iter()
        .map(|fault| Num::of(&fault["cycle"]))
        .collect();
    scheduled.sort_by(|left, right| left.compare(*right));
    let observed: Vec<Num> = events
        .iter()
        .filter(|event| names.get(event.code) == Some("FAULT_INJECTED"))
        .map(|event| Num::Int(u128::from(event.cycle)))
        .collect();
    if scheduled.len() != observed.len()
        || scheduled
            .iter()
            .zip(&observed)
            .any(|(left, right)| !left.same(*right))
    {
        return Err("fault schedule does not match captured FAULT_INJECTED events".to_owned());
    }
    let profile = &contracts["event_profiles"][text(&manifest["profile"])];
    let (cycle_count, warmup) = (
        Num::of(&manifest["cycle_count"]),
        Num::of(&manifest["warmup_cycles"]),
    );
    let grouped = cycles(events, &names);
    let (mut values, rows) = intervals(&grouped, profile, warmup)?;
    let periodic: Vec<String> = values.iter().map(|(name, _)| name.clone()).collect();
    let deadline = profile["periodic_events"]
        .as_array()
        .expect("schema-checked array")
        .iter()
        .any(|name| name == "DEADLINE");
    let mut control_block = Value::Null;
    if deadline {
        let (block, detected, safe) = control(&grouped, warmup, cycle_count)?;
        control_block = block;
        values.push(("fault_detection".to_owned(), detected));
        values.push(("time_to_safe_state".to_owned(), safe));
    }
    let analysed: Vec<&Event> = events
        .iter()
        .filter(|event| Num::Int(u128::from(event.cycle)).compare(warmup) != Ordering::Less)
        .collect();
    let duration = match (analysed.first(), analysed.last()) {
        (Some(first), Some(last)) => last.ticks - first.ticks,
        _ => 0,
    };
    let mut distributions = Map::new();
    for (name, samples) in &values {
        let mut summary = distribution(samples);
        summary.insert("duration_ticks".to_owned(), json!(duration));
        distributions.insert(name.clone(), Value::Object(summary));
    }
    if let Value::Object(block) = &mut control_block {
        block.insert(
            "sample_count".to_owned(),
            block["observed_deadlines"].clone(),
        );
        block.insert("duration_ticks".to_owned(), json!(duration));
    }
    let analysed_cycles = cycle_count.sub(warmup);
    let block = json!({
        "event_count": analysed.len(),
        "cycle_count": analysed_cycles.json(),
        "duration_ticks": duration,
        "intervals": distributions,
        "control": control_block,
        "jitter_method": JITTER_METHOD,
        "jitter": jitter(&rows, &periodic, analysed_cycles, duration),
    });
    Ok((block, rows))
}

#[cfg(test)]
#[path = "../tests/unit/control_analysis.rs"]
mod tests;
