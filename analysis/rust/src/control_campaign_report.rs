// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — repeat campaign statistics

//! Report every repeat, pool the raw samples of valid repeats and state the
//! spread between them, as Python's `campaign_analysis.build_campaign_report`
//! does.
//!
//! Each repeat is analysed with the per-run report. Only valid repeats
//! contribute samples: latencies and within-repeat jitter pairs are
//! concatenated and summarised with Type-7 quantiles, never averaged. Counts
//! keep Python's integer or float type, minima and maxima keep the first of
//! equal values, and the run plan is compared as Python compares it. A
//! campaign binding an AMP capture is refused: the native analysis does not
//! complete AMP captures.

use crate::control_analysis::{JITTER_METHOD, Row, distribution};
use crate::control_campaign::{Campaign, Repeat, configuration};
use crate::control_number::{Num, python_number};
use crate::control_report::{AMP_UNSUPPORTED, build_report};
use serde_json::{Map, Value, json};
use std::cmp::Ordering;

/// Campaign report schema identifier.
const CAMPAIGN_REPORT_SCHEMA: &str = "loop-timing-witness.repeat-campaign-report.v1";
/// Per-repeat statistics whose range across valid repeats is stated.
pub(crate) const SPREAD_STATISTICS: [&str; 5] = [
    "median_ticks",
    "p95_ticks",
    "p99_ticks",
    "p999_ticks",
    "maximum_ticks",
];
/// Limits every campaign report states.
const LIMITS: [&str; 4] = [
    "Pooled distributions are computed from the concatenated raw samples of valid repeats; \
     per-repeat percentiles are never averaged.",
    "Adjacent-cycle jitter pairs never span two repeats.",
    "Fault detection, time to safe state, tracking error and energy remain per-repeat results \
     in the run reports and are not pooled here.",
    "Spread is the range of each per-repeat statistic across valid repeats.",
];

/// The run report and interval rows of one analysed repeat.
struct Analysed {
    report: Value,
    rows: Vec<Row>,
}

/// Analyse one repeat with the per-run report and summarise its outcome.
fn analyse_repeat(repeat: &Repeat) -> (Map<String, Value>, Option<Analysed>) {
    let mut entry = Map::new();
    entry.insert("repeat_index".to_owned(), repeat.index.clone());
    entry.insert("run_manifest_sha256".to_owned(), json!(repeat.sha256));
    entry.insert("rebooted_before_run".to_owned(), json!(repeat.rebooted));
    entry.insert(
        "run_id".to_owned(),
        repeat
            .run
            .as_ref()
            .map_or(Value::Null, |run| run.manifest["run_id"].clone()),
    );
    entry.insert("status".to_owned(), json!("refused"));
    entry.insert("refusal".to_owned(), json!(repeat.refusal));
    entry.insert("invalid_reasons".to_owned(), json!([]));
    for name in [
        "analysed_cycles",
        "duration_ticks",
        "intervals",
        "jitter",
        "control",
    ] {
        entry.insert(name.to_owned(), Value::Null);
    }
    let Some(run) = &repeat.run else {
        return (entry, None);
    };
    let (report, rows) = match build_report(&run.manifest, &run.domain, &run.files) {
        Ok(analysed) => analysed,
        Err(refusal) => {
            entry.insert("refusal".to_owned(), json!(refusal));
            return (entry, None);
        }
    };
    let events = &report["events"];
    let status = if report["valid"] == true {
        "valid"
    } else {
        "invalid"
    };
    entry.insert("status".to_owned(), json!(status));
    entry.insert(
        "invalid_reasons".to_owned(),
        report["invalid_reasons"].clone(),
    );
    entry.insert("analysed_cycles".to_owned(), events["cycle_count"].clone());
    for name in ["duration_ticks", "intervals", "jitter", "control"] {
        entry.insert(name.to_owned(), events[name].clone());
    }
    (entry, Some(Analysed { report, rows }))
}

/// The pooled jitter summary of one periodic interval.
fn pooled_jitter(changes: &[u64], expected: Num, duration: u64) -> Value {
    let count = changes.len() as u64;
    let status = if count == 0 {
        "unavailable"
    } else if Num::Int(u128::from(count)).same(expected) {
        "available"
    } else {
        "partial"
    };
    let coverage = if expected.truthy() {
        json!(expected.divide(count))
    } else {
        Value::Null
    };
    let mut summary = distribution(changes);
    summary.insert("status".to_owned(), json!(status));
    summary.insert("expected_pair_count".to_owned(), expected.json());
    summary.insert(
        "missing_pair_count".to_owned(),
        expected.sub(Num::Int(u128::from(count))).json(),
    );
    summary.insert("pair_coverage_fraction".to_owned(), coverage);
    summary.insert("duration_ticks".to_owned(), json!(duration));
    Value::Object(summary)
}

/// Pool raw latency samples and within-repeat jitter pairs of valid repeats.
///
/// Summed cycle and pair counts stay within 64 bits: each valid repeat has one
/// anchor event in each of at most 2**32 analysed cycles. The summed duration
/// can exceed the range and is refused, as in Python.
fn pooled(valid: &[&Analysed], names: &[String]) -> Result<Value, String> {
    let mut latencies: Vec<Vec<u64>> = vec![Vec::new(); names.len()];
    let mut changes: Vec<Vec<u64>> = vec![Vec::new(); names.len()];
    let mut expected = Num::Int(0);
    let mut cycles = Num::Int(0);
    let mut duration: u128 = 0;
    for analysed in valid {
        let mut previous: Vec<Option<(u32, u64)>> = vec![None; names.len()];
        for row in &analysed.rows {
            let index = names
                .iter()
                .position(|name| *name == row.interval)
                .expect("shared periodic interval");
            latencies[index].push(row.ticks);
            if let Some((cycle, ticks)) = previous[index]
                && u64::from(row.cycle) == u64::from(cycle) + 1
            {
                changes[index].push(row.ticks.abs_diff(ticks));
            }
            previous[index] = Some((row.cycle, row.ticks));
        }
        let events = &analysed.report["events"];
        let analysed_cycles = Num::of(&events["cycle_count"]);
        expected = expected.add(analysed_cycles.sub(Num::Int(1)).at_least_zero());
        cycles = cycles.add(analysed_cycles);
        duration += u128::from(events["duration_ticks"].as_u64().expect("tick span"));
    }
    let duration = u64::try_from(duration)
        .map_err(|_| "pooled duration exceeds the 64-bit tick range".to_owned())?;
    let mut intervals = Map::new();
    let mut jitter = Map::new();
    for (index, name) in names.iter().enumerate() {
        let mut summary = distribution(&latencies[index]);
        summary.insert("duration_ticks".to_owned(), json!(duration));
        intervals.insert(name.clone(), Value::Object(summary));
        jitter.insert(
            name.clone(),
            pooled_jitter(&changes[index], expected, duration),
        );
    }
    let controls: Vec<&Value> = valid
        .iter()
        .map(|analysed| &analysed.report["events"]["control"])
        .collect();
    let control = match controls.first() {
        Some(first) if !first.is_null() => {
            let total = |name: &str| -> u64 {
                controls
                    .iter()
                    .map(|control| control[name].as_u64().expect("event count"))
                    .sum()
            };
            // A valid CONTROL repeat observes a deadline in each of its analysed
            // cycles, at least one, so Python's `None` rate for no observation
            // cannot occur here.
            let (observed, misses) = (total("observed_deadlines"), total("deadline_misses"));
            json!({
                "observed_deadlines": observed,
                "deadline_misses": misses,
                "deadline_miss_rate": misses as f64 / observed as f64,
            })
        }
        _ => Value::Null,
    };
    let run_ids: Vec<Value> = valid
        .iter()
        .map(|analysed| analysed.report["run_id"].clone())
        .collect();
    Ok(json!({
        "repeat_count": valid.len(),
        "run_ids": run_ids,
        "cycle_count": cycles.json(),
        "duration_ticks": duration,
        "intervals": intervals,
        "jitter_method": JITTER_METHOD,
        "jitter": jitter,
        "control": control,
    }))
}

/// Python's `min` or `max` of non-negative numbers: the first value no other beats.
fn extreme<'a>(values: &[&'a Value], beats: Ordering) -> &'a Value {
    values
        .iter()
        .copied()
        .reduce(|kept, value| {
            if Num::of(value).compare(Num::of(kept)) == beats {
                value
            } else {
                kept
            }
        })
        .expect("at least one value")
}

/// The range of each per-repeat statistic across valid repeats; null when any
/// valid repeat could not compute it or no repeat is valid.
fn spread(valid: &[&Analysed], names: &[String], metric: &str) -> Value {
    let mut result = Map::new();
    for name in names {
        let mut statistics = Map::new();
        for statistic in SPREAD_STATISTICS {
            let values: Vec<&Value> = valid
                .iter()
                .map(|analysed| &analysed.report["events"][metric][name.as_str()][statistic])
                .collect();
            let range = if values.is_empty() || values.iter().any(|value| value.is_null()) {
                json!({"minimum": null, "maximum": null, "range": null})
            } else {
                let (low, high) = (
                    extreme(&values, Ordering::Less),
                    extreme(&values, Ordering::Greater),
                );
                json!({
                    "minimum": low,
                    "maximum": high,
                    "range": Num::of(high).sub(Num::of(low)).json(),
                })
            };
            statistics.insert(statistic.to_owned(), range);
        }
        result.insert(name.clone(), Value::Object(statistics));
    }
    Value::Object(result)
}

/// Compare the campaign with the measurement-domain run plan.
fn plan(campaign: &Campaign, entries: &[Map<String, Value>], domain: Option<&Value>) -> Value {
    let run_plan = domain.map(|domain| &domain["design_contracts"]["run_plan"]);
    let planned_repeats = run_plan.map(|plan| &plan["repeats"]);
    let planned_cycles = run_plan.map(|plan| &plan["cycles_per_repeat"]);
    let declared = entries.len();
    let mut nonconformities = Vec::new();
    match planned_repeats {
        None => {
            nonconformities
                .push("no repeat could be loaded; the run plan is unavailable".to_owned());
        }
        Some(planned) if !Num::of(planned).same(Num::Int(declared as u128)) => {
            nonconformities.push(format!(
                "{declared} repeats declared; the run plan requires {}",
                python_number(planned)
            ));
        }
        Some(_) => {}
    }
    nonconformities.extend(
        campaign
            .repeats
            .iter()
            .filter(|repeat| !repeat.rebooted)
            .map(|repeat| {
                format!(
                    "repeat {} did not reboot before its run",
                    python_number(&repeat.index)
                )
            }),
    );
    let status = |entry: &Map<String, Value>| entry["status"].as_str().expect("status").to_owned();
    nonconformities.extend(
        entries
            .iter()
            .filter(|entry| status(entry) != "valid")
            .map(|entry| {
                format!(
                    "repeat {} is {}",
                    python_number(&entry["repeat_index"]),
                    status(entry)
                )
            }),
    );
    // Python takes the minimum of a set, which keeps the first of equal values.
    let analysed: Vec<&Value> = entries
        .iter()
        .map(|entry| &entry["analysed_cycles"])
        .filter(|cycles| !cycles.is_null())
        .collect();
    if let Some(planned) = planned_cycles
        && !analysed.is_empty()
    {
        let fewest = extreme(&analysed, Ordering::Less);
        if Num::of(fewest).compare(Num::of(planned)) == Ordering::Less {
            nonconformities.push(format!(
                "{} analysed cycles per repeat; the run plan requires {}",
                python_number(fewest),
                python_number(planned)
            ));
        }
    }
    let count = |wanted: &str| {
        entries
            .iter()
            .filter(|entry| status(entry) == wanted)
            .count()
    };
    json!({
        "planned_repeats": planned_repeats,
        "planned_cycles_per_repeat": planned_cycles,
        "declared_repeats": declared,
        "valid_repeats": count("valid"),
        "invalid_repeats": count("invalid"),
        "refused_repeats": count("refused"),
        "conforms": nonconformities.is_empty(),
        "nonconformities": nonconformities,
    })
}

/// Build the repeat campaign report from the loaded repeats.
pub(crate) fn build_campaign_report(campaign: &Campaign) -> Result<Value, String> {
    let loaded: Vec<_> = campaign
        .repeats
        .iter()
        .filter_map(|repeat| repeat.run.as_ref())
        .collect();
    if loaded
        .iter()
        .any(|run| run.files.contains_key("amp_capture"))
    {
        return Err(AMP_UNSUPPORTED.to_owned());
    }
    let mut entries = Vec::new();
    let mut analysed = Vec::new();
    for repeat in &campaign.repeats {
        let (entry, result) = analyse_repeat(repeat);
        let valid = entry["status"] == "valid";
        entries.push(entry);
        if let Some(result) = result {
            analysed.push((valid, result));
        }
    }
    let valid: Vec<&Analysed> = analysed
        .iter()
        .filter(|(valid, _)| *valid)
        .map(|(_, result)| result)
        .collect();
    let names: Vec<String> = analysed.first().map_or_else(Vec::new, |(_, first)| {
        first.report["events"]["jitter"]
            .as_object()
            .expect("jitter block")
            .keys()
            .cloned()
            .collect()
    });
    let first = loaded.first();
    let plan = plan(campaign, &entries, first.map(|run| &run.domain));
    let source_kind = first.map(|run| run.manifest["source"]["kind"].as_str().expect("kind"));
    let evidence_status = match source_kind {
        None => "unavailable",
        Some("rtl_simulation") => "simulation_only",
        Some(_) => "board_declaration_unverified",
    };
    let mut limits: Vec<&str> = LIMITS.to_vec();
    if source_kind == Some("rtl_simulation") {
        limits.push("RTL simulation repeats are not board measurements.");
    }
    let configuration = first.map_or(Value::Null, |run| {
        Value::Object(
            configuration(run)
                .into_iter()
                .map(|(name, value)| (name.to_owned(), value))
                .collect(),
        )
    });
    let pooled = pooled(&valid, &names)?;
    Ok(json!({
        "schema": CAMPAIGN_REPORT_SCHEMA,
        "campaign_id": campaign.manifest["campaign_id"],
        "campaign_manifest_sha256": campaign.sha256,
        "evidence_status": evidence_status,
        "status": if plan["conforms"] == true { "complete" } else { "incomplete" },
        "configuration": configuration,
        "timebase_resolution_ns": first.map_or(Value::Null, |run| {
            run.domain["design_contracts"]["timebase"]["resolution_ns"].clone()
        }),
        "plan": plan,
        "repeats": entries,
        "pooled": pooled,
        "spread": {
            "intervals": spread(&valid, &names, "intervals"),
            "jitter": spread(&valid, &names, "jitter"),
        },
        "limits": limits,
    }))
}
