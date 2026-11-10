// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — repeat campaign report files

//! The files of a repeat campaign report, byte for byte as Python's
//! `campaign_outputs.write_campaign_report` builds them, in its writing order.
//!
//! `campaign_report.json` is written as the run report is. The CSV tables
//! flatten the per-repeat, pooled and spread statistics with the run tables'
//! cell rules; a row is a mapping merged in Python's order, so a later member,
//! such as a jitter statistic's own `status`, replaces an earlier one.

use crate::control_campaign_report::SPREAD_STATISTICS;
use crate::control_json_text::canonical_json;
use crate::control_outputs::csv_table;
use serde_json::{Map, Value, json};

/// Distribution columns of the per-repeat and pooled tables.
const DISTRIBUTION: [&str; 6] = [
    "sample_count",
    "median_ticks",
    "p95_ticks",
    "p99_ticks",
    "p999_ticks",
    "maximum_ticks",
];
/// Each metric's name and its block in a repeat entry or the pooled statistics.
const METRICS: [(&str, &str); 2] = [("latency", "intervals"), ("jitter", "jitter")];

/// The identity columns of every campaign row.
fn identity(report: &Value) -> Map<String, Value> {
    let mut row = Map::new();
    for name in ["campaign_id", "evidence_status"] {
        row.insert(name.to_owned(), report[name].clone());
    }
    row
}

/// The members of a statistics object.
fn members(value: &Value) -> &Map<String, Value> {
    value.as_object().expect("statistics object")
}

/// One row per repeat, metric and interval; a refused repeat has one row
/// without statistics.
fn repeat_rows(report: &Value) -> Vec<Map<String, Value>> {
    let mut rows = Vec::new();
    for entry in report["repeats"].as_array().expect("repeat entries") {
        let mut repeat = identity(report);
        for name in ["repeat_index", "run_id", "status"] {
            repeat.insert(name.to_owned(), entry[name].clone());
        }
        if entry["intervals"].is_null() {
            rows.push(repeat);
            continue;
        }
        for (metric, key) in METRICS {
            for (name, statistics) in members(&entry[key]) {
                let mut row = repeat.clone();
                row.insert("metric".to_owned(), json!(metric));
                row.insert("interval".to_owned(), json!(name));
                row.extend(members(statistics).clone());
                row.insert("duration_ticks".to_owned(), entry["duration_ticks"].clone());
                rows.push(row);
            }
        }
    }
    rows
}

/// One row per metric and periodic interval of the pooled statistics.
fn pooled_rows(report: &Value) -> Vec<Map<String, Value>> {
    let pooled = &report["pooled"];
    let mut rows = Vec::new();
    for (metric, key) in METRICS {
        for (name, statistics) in members(&pooled[key]) {
            let mut row = identity(report);
            row.insert("metric".to_owned(), json!(metric));
            row.insert("interval".to_owned(), json!(name));
            row.insert("repeat_count".to_owned(), pooled["repeat_count"].clone());
            row.extend(members(statistics).clone());
            rows.push(row);
        }
    }
    rows
}

/// One row per metric, interval and spread statistic.
fn spread_rows(report: &Value) -> Vec<Map<String, Value>> {
    let mut rows = Vec::new();
    for (metric, key) in METRICS {
        for (name, statistics) in members(&report["spread"][key]) {
            for statistic in SPREAD_STATISTICS {
                let mut row = identity(report);
                row.insert("metric".to_owned(), json!(metric));
                row.insert("interval".to_owned(), json!(name));
                row.insert("statistic".to_owned(), json!(statistic));
                row.extend(members(&statistics[statistic]).clone());
                rows.push(row);
            }
        }
    }
    rows
}

/// Every file of the campaign report directory, named, in Python's writing order.
pub(crate) fn campaign_files(report: &Value) -> Vec<(String, Vec<u8>)> {
    let identity = ["campaign_id", "evidence_status"];
    let repeat_columns: Vec<&str> = identity
        .into_iter()
        .chain(["repeat_index", "run_id", "status", "metric", "interval"])
        .chain(DISTRIBUTION)
        .chain(["duration_ticks"])
        .collect();
    let pooled_columns: Vec<&str> = identity
        .into_iter()
        .chain(["metric", "interval", "repeat_count"])
        .chain(DISTRIBUTION)
        .chain([
            "expected_pair_count",
            "missing_pair_count",
            "pair_coverage_fraction",
            "duration_ticks",
        ])
        .collect();
    let spread_columns: Vec<&str> = identity
        .into_iter()
        .chain([
            "metric",
            "interval",
            "statistic",
            "minimum",
            "maximum",
            "range",
        ])
        .collect();
    vec![
        ("campaign_report.json".to_owned(), canonical_json(report)),
        (
            "repeat_summary.csv".to_owned(),
            csv_table(&repeat_columns, &repeat_rows(report)),
        ),
        (
            "pooled_summary.csv".to_owned(),
            csv_table(&pooled_columns, &pooled_rows(report)),
        ),
        (
            "repeat_spread.csv".to_owned(),
            csv_table(&spread_columns, &spread_rows(report)),
        ),
    ]
}
