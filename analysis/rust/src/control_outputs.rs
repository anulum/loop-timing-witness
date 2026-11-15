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
use std::borrow::Cow;
use std::collections::BTreeMap;
use std::fmt::Write;

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
    files.push((
        "interval_summary.csv".to_owned(),
        csv_table(&INTERVAL_COLUMNS, &summary_rows(report, "intervals")),
    ));
    let provenance = provenance(report);
    files.push((
        "jitter_summary.csv".to_owned(),
        csv_table(
            &provenance_columns(&JITTER_COLUMNS),
            &with_provenance(summary_rows(report, "jitter"), &provenance),
        ),
    ));
    files.push(("cycle_jitter.csv".to_owned(), pair_table(&provenance, rows)));
    files.push(("cycle_intervals.csv".to_owned(), cycle_table(report, rows)));
    files.extend(plots(report));
    files
}

/// Add the run identity and evidence status to one table row.
fn identify(report: &Value, row: &mut Map<String, Value>) {
    row.insert("run_id".to_owned(), report["run_id"].clone());
    row.insert(
        "evidence_status".to_owned(),
        report["evidence_status"].clone(),
    );
}

/// One identified row per interval of an `events` summary block.
fn summary_rows(report: &Value, metric: &str) -> Vec<Map<String, Value>> {
    report["events"][metric]
        .as_object()
        .expect("summary block")
        .iter()
        .map(|(name, statistics)| {
            let mut row = statistics.as_object().expect("statistics").clone();
            identify(report, &mut row);
            row.insert("interval".to_owned(), json!(name));
            row
        })
        .collect()
}

/// The provenance columns of the jitter tables.
fn provenance(report: &Value) -> Map<String, Value> {
    let mut provenance = Map::new();
    for name in PROVENANCE {
        let value = match name {
            "jitter_method" => report["events"]["jitter_method"].clone(),
            _ => report[name].clone(),
        };
        provenance.insert(name.to_owned(), value);
    }
    provenance
}

/// The rows with the provenance columns added.
fn with_provenance(
    rows: Vec<Map<String, Value>>,
    provenance: &Map<String, Value>,
) -> Vec<Map<String, Value>> {
    rows.into_iter()
        .map(|mut row| {
            row.extend(provenance.clone());
            row
        })
        .collect()
}

/// The provenance column names followed by a table's own columns.
fn provenance_columns(tail: &[&'static str]) -> Vec<&'static str> {
    PROVENANCE.iter().chain(tail).copied().collect()
}

/// `cycle_intervals.csv`: one identified row per analysed cycle interval.
///
/// Rows are written as they are formed, so no table of row mappings is held.
fn cycle_table(report: &Value, rows: &[Row]) -> Vec<u8> {
    let identity = format!(
        "{},{}",
        cell(Some(&report["run_id"])),
        cell(Some(&report["evidence_status"]))
    );
    let mut text = header(&CYCLE_COLUMNS);
    for row in rows {
        let _ = write!(
            text,
            "{identity},{},{},{}\r\n",
            row.cycle,
            text_cell(&row.interval),
            row.ticks
        );
    }
    text.into_bytes()
}

/// Changes between adjacent cycles of the same interval, as Python's `jitter_pairs`.
///
/// A change can exceed the 64-bit signed range, so it is kept as Python's
/// decimal text of the integer, which is what its CSV cell holds.
///
/// Rows are written as they are formed, after the provenance cells, so no table of
/// pair mappings is held.
fn pair_table(provenance: &Map<String, Value>, rows: &[Row]) -> Vec<u8> {
    let identity = PROVENANCE
        .iter()
        .map(|name| cell(provenance.get(*name)))
        .collect::<Vec<_>>()
        .join(",");
    let mut text = header(&provenance_columns(&PAIR_COLUMNS));
    let mut previous: BTreeMap<&str, (u32, u64)> = BTreeMap::new();
    for row in rows {
        if let Some(&(cycle, ticks)) = previous.get(row.interval.as_str())
            && u64::from(row.cycle) == u64::from(cycle) + 1
        {
            let delta = i128::from(row.ticks) - i128::from(ticks);
            let _ = write!(
                text,
                "{identity},{},{cycle},{},{ticks},{},{delta},{}\r\n",
                text_cell(&row.interval),
                row.cycle,
                row.ticks,
                delta.unsigned_abs()
            );
        }
        previous.insert(&row.interval, (row.cycle, row.ticks));
    }
    text.into_bytes()
}

/// Python's `str` of one CSV cell value, quoted as the excel dialect quotes it;
/// `None` and a missing column are empty cells. Every listed column holds text,
/// a number or `None`.
pub(crate) fn cell(value: Option<&Value>) -> String {
    match value.unwrap_or(&Value::Null) {
        Value::Null => String::new(),
        Value::String(string) => text_cell(string).into_owned(),
        number => number_text(number, number.is_f64()),
    }
}

/// One text cell, quoted as the excel dialect quotes it.
fn text_cell(string: &str) -> Cow<'_, str> {
    if string.contains([',', '"', '\r', '\n']) {
        Cow::Owned(format!("\"{}\"", string.replace('"', "\"\"")))
    } else {
        Cow::Borrowed(string)
    }
}

/// The CRLF-terminated header line of a table.
fn header(columns: &[&str]) -> String {
    let mut text = columns.join(",");
    text.push_str("\r\n");
    text
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
