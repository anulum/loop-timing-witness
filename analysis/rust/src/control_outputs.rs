// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — report directory files of a control run

//! The report files of a control run, byte for byte as Python's
//! `report_outputs.write_report` builds them, in its writing order.
//!
//! `report.json` is written by [`canonical_json`]. The CSV tables follow
//! `csv.DictWriter` in the excel dialect: CRLF rows, `str` of each value, an
//! empty cell for `None`, and the dialect's minimal quoting: a cell holding a
//! comma, a quote or a line break is quoted, with its quotes doubled. An
//! identifier can end with a line feed, which its schema pattern admits. The
//! plots come from [`plots`].

use crate::control_analysis::Row;
use crate::control_json_text::{canonical_json, number_text};
use crate::control_plots::plots;
use serde_json::{Map, Value, json};
use std::collections::BTreeMap;

/// Columns of `interval_summary.csv`.
const INTERVAL_COLUMNS: [&str; 10] = [
    "run_id",
    "evidence_status",
    "interval",
    "sample_count",
    "median_ticks",
    "p95_ticks",
    "p99_ticks",
    "p999_ticks",
    "maximum_ticks",
    "duration_ticks",
];
/// Jitter provenance columns, first in both jitter tables.
const PROVENANCE: [&str; 5] = [
    "run_id",
    "evidence_status",
    "jitter_method",
    "timebase_resolution_ns",
    "instrument_floor_ticks",
];
/// Columns of `jitter_summary.csv` after the provenance.
const JITTER_COLUMNS: [&str; 14] = [
    "interval",
    "status",
    "latency_sample_count",
    "sample_count",
    "expected_pair_count",
    "missing_pair_count",
    "pair_coverage_fraction",
    "median_ticks",
    "p95_ticks",
    "p99_ticks",
    "p999_ticks",
    "maximum_ticks",
    "peak_to_peak_ticks",
    "duration_ticks",
];
/// Columns of `cycle_jitter.csv` after the provenance.
const PAIR_COLUMNS: [&str; 7] = [
    "interval",
    "previous_cycle",
    "cycle",
    "previous_ticks",
    "ticks",
    "delta_ticks",
    "absolute_delta_ticks",
];
/// Columns of `cycle_intervals.csv`.
const CYCLE_COLUMNS: [&str; 5] = ["run_id", "evidence_status", "cycle", "interval", "ticks"];

/// Every file of the report directory, named, in Python's writing order.
pub(crate) fn report_files(report: &Value, rows: &[Row]) -> Vec<(String, Vec<u8>)> {
    let mut files = Vec::new();
    files.push(("report.json".to_owned(), canonical_json(report)));
    let identity = |row: &mut Map<String, Value>| {
        row.insert("run_id".to_owned(), report["run_id"].clone());
        row.insert(
            "evidence_status".to_owned(),
            report["evidence_status"].clone(),
        );
    };
    let summary = |metric: &str| -> Vec<Map<String, Value>> {
        report["events"][metric]
            .as_object()
            .expect("summary block")
            .iter()
            .map(|(name, statistics)| {
                let mut row = statistics.as_object().expect("statistics").clone();
                identity(&mut row);
                row.insert("interval".to_owned(), json!(name));
                row
            })
            .collect()
    };
    files.push((
        "interval_summary.csv".to_owned(),
        csv_table(&INTERVAL_COLUMNS, &summary("intervals")),
    ));
    let mut provenance = Map::new();
    for name in PROVENANCE {
        let value = match name {
            "jitter_method" => report["events"]["jitter_method"].clone(),
            _ => report[name].clone(),
        };
        provenance.insert(name.to_owned(), value);
    }
    let with_provenance = |rows: Vec<Map<String, Value>>| -> Vec<Map<String, Value>> {
        rows.into_iter()
            .map(|mut row| {
                row.extend(provenance.clone());
                row
            })
            .collect()
    };
    let columns = |tail: &[&'static str]| -> Vec<&'static str> {
        PROVENANCE.iter().chain(tail).copied().collect()
    };
    files.push((
        "jitter_summary.csv".to_owned(),
        csv_table(
            &columns(&JITTER_COLUMNS),
            &with_provenance(summary("jitter")),
        ),
    ));
    files.push((
        "cycle_jitter.csv".to_owned(),
        csv_table(
            &columns(&PAIR_COLUMNS),
            &with_provenance(jitter_pairs(rows)),
        ),
    ));
    let cycles: Vec<Map<String, Value>> = rows
        .iter()
        .map(|row| {
            let mut fields = Map::new();
            identity(&mut fields);
            fields.insert("cycle".to_owned(), json!(row.cycle));
            fields.insert("interval".to_owned(), json!(row.interval));
            fields.insert("ticks".to_owned(), json!(row.ticks));
            fields
        })
        .collect();
    files.push((
        "cycle_intervals.csv".to_owned(),
        csv_table(&CYCLE_COLUMNS, &cycles),
    ));
    files.extend(plots(report));
    files
}

/// Changes between adjacent cycles of the same interval, as Python's `jitter_pairs`.
///
/// A change can exceed the 64-bit signed range, so it is kept as Python's
/// decimal text of the integer, which is what its CSV cell holds.
fn jitter_pairs(rows: &[Row]) -> Vec<Map<String, Value>> {
    let mut previous: BTreeMap<&str, (u32, u64)> = BTreeMap::new();
    let mut pairs = Vec::new();
    for row in rows {
        if let Some(&(cycle, ticks)) = previous.get(row.interval.as_str())
            && u64::from(row.cycle) == u64::from(cycle) + 1
        {
            let delta = i128::from(row.ticks) - i128::from(ticks);
            let pair = json!({
                "interval": row.interval,
                "previous_cycle": cycle,
                "cycle": row.cycle,
                "previous_ticks": ticks,
                "ticks": row.ticks,
                "delta_ticks": delta.to_string(),
                "absolute_delta_ticks": delta.unsigned_abs().to_string(),
            });
            pairs.push(pair.as_object().cloned().expect("pair object"));
        }
        previous.insert(&row.interval, (row.cycle, row.ticks));
    }
    pairs
}

/// Python's `str` of one CSV cell value, quoted as the excel dialect quotes it;
/// `None` and a missing column are empty cells. Every listed column holds text,
/// a number or `None`.
pub(crate) fn cell(value: Option<&Value>) -> String {
    match value.unwrap_or(&Value::Null) {
        Value::Null => String::new(),
        Value::String(string) if string.contains([',', '"', '\r', '\n']) => {
            format!("\"{}\"", string.replace('"', "\"\""))
        }
        Value::String(string) => string.clone(),
        number => number_text(number, number.is_f64()),
    }
}

/// A CSV table with a header and one CRLF-terminated row per mapping.
pub(crate) fn csv_table(columns: &[&str], rows: &[Map<String, Value>]) -> Vec<u8> {
    let mut text = String::new();
    let line = |fields: Vec<String>, text: &mut String| {
        text.push_str(&fields.join(","));
        text.push_str("\r\n");
    };
    line(
        columns.iter().map(|name| (*name).to_owned()).collect(),
        &mut text,
    );
    for row in rows {
        line(
            columns.iter().map(|name| cell(row.get(*name))).collect(),
            &mut text,
        );
    }
    text.into_bytes()
}
