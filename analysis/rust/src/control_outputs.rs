// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — report directory files of a control run

//! The report files of a control run, byte for byte as Python's
//! `report_outputs.write_report` builds them.
//!
//! `report.json` is `json.dumps(…, ensure_ascii=False, indent=2,
//! sort_keys=True)` with a final newline and Python's float text. The CSV
//! tables follow `csv.DictWriter` in the excel dialect: CRLF rows, `str` of
//! each value and an empty cell for `None`. Their cells are identifiers, fixed
//! words and numbers, which the schemas keep free of commas, quotes and line
//! breaks, so the dialect's minimal quoting never applies. The SVG plots use
//! Python's `%.3f` and `%.6g` number formats and `xml.sax.saxutils.escape`.

use crate::control_analysis::Row;
use crate::control_number::python_float;
use serde_json::{Map, Value, json};
use std::collections::BTreeMap;
use std::fmt::Write as _;

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

/// `json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)` and a newline.
pub(crate) fn canonical_json(value: &Value) -> Vec<u8> {
    let mut text = String::new();
    json_value(value, 0, &mut text);
    text.push('\n');
    text.into_bytes()
}

/// Append one value at an indentation depth.
fn json_value(value: &Value, depth: usize, text: &mut String) {
    match value {
        Value::Null => text.push_str("null"),
        Value::Bool(flag) => text.push_str(if *flag { "true" } else { "false" }),
        Value::Number(number) => text.push_str(&number_text(value, number.is_f64())),
        Value::String(string) => json_string(string, text),
        Value::Array(items) => {
            let rendered = items
                .iter()
                .map(|item| {
                    let mut part = String::new();
                    json_value(item, depth + 1, &mut part);
                    part
                })
                .collect();
            bracketed(('[', ']'), rendered, depth, text);
        }
        Value::Object(members) => {
            let rendered = members
                .iter()
                .map(|(name, member)| {
                    let mut part = String::new();
                    json_string(name, &mut part);
                    part.push_str(": ");
                    json_value(member, depth + 1, &mut part);
                    part
                })
                .collect();
            bracketed(('{', '}'), rendered, depth, text);
        }
    }
}

/// Append rendered items between brackets, one per line, or the bare brackets when empty.
fn bracketed(brackets: (char, char), items: Vec<String>, depth: usize, text: &mut String) {
    text.push(brackets.0);
    if !items.is_empty() {
        let inner = "  ".repeat(depth + 1);
        text.push('\n');
        text.push_str(&inner);
        text.push_str(&items.join(&format!(",\n{inner}")));
        text.push('\n');
        text.push_str(&"  ".repeat(depth));
    }
    text.push(brackets.1);
}

/// Python's text of a decoded JSON number: integers as digits, floats as `repr`.
fn number_text(value: &Value, float: bool) -> String {
    if float {
        python_float(value.as_f64().expect("float"))
    } else {
        value.to_string()
    }
}

/// A JSON string as Python's encoder writes it without ASCII escaping.
fn json_string(string: &str, text: &mut String) {
    text.push('"');
    for character in string.chars() {
        match character {
            '"' => text.push_str("\\\""),
            '\\' => text.push_str("\\\\"),
            '\n' => text.push_str("\\n"),
            '\r' => text.push_str("\\r"),
            '\t' => text.push_str("\\t"),
            '\u{8}' => text.push_str("\\b"),
            '\u{c}' => text.push_str("\\f"),
            control if control < ' ' => {
                let _ = write!(text, "\\u{:04x}", u32::from(control));
            }
            other => text.push(other),
        }
    }
    text.push('"');
}

/// Python's `str` of one CSV cell value; `None` and a missing column are empty
/// cells. Every listed column holds text, a number or `None`.
fn cell(value: Option<&Value>) -> String {
    match value.unwrap_or(&Value::Null) {
        Value::Null => String::new(),
        Value::String(string) => string.clone(),
        number => number_text(number, number.is_f64()),
    }
}

/// A CSV table with a header and one CRLF-terminated row per mapping.
fn csv_table(columns: &[&str], rows: &[Map<String, Value>]) -> Vec<u8> {
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

/// `xml.sax.saxutils.escape`.
fn escape(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

/// Python's `format(value, ".6g")` of a finite value that is not negative.
fn general(value: f64) -> String {
    if value == 0.0 {
        return "0".to_owned();
    }
    let scientific = format!("{value:.5e}");
    let (mantissa, exponent) = scientific.split_once('e').expect("scientific notation");
    let exponent: i32 = exponent.parse().expect("decimal exponent");
    let trim = |text: String| -> String {
        if text.contains('.') {
            text.trim_end_matches('0').trim_end_matches('.').to_owned()
        } else {
            text
        }
    };
    if (-4..6).contains(&exponent) {
        let decimals = usize::try_from(5 - exponent).expect("decimals");
        trim(format!("{value:.decimals$}"))
    } else {
        let marker = if exponent < 0 { '-' } else { '+' };
        format!(
            "{}e{marker}{:02}",
            trim(mantissa.to_owned()),
            exponent.unsigned_abs()
        )
    }
}

/// A labelled horizontal bar chart, as Python's `_svg_plot`.
fn svg_plot(title: &str, labels: &[String], values: &[f64], unit: &str) -> Vec<u8> {
    let width = 960;
    let height = 160.max(100 + 38 * labels.len());
    let extent = values.iter().copied().fold(0.0_f64, f64::max);
    let scale = if extent == 0.0 { 0.0 } else { 580.0 / extent };
    let mut lines = vec![
        format!(
            "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width}\" height=\"{height}\" \
             viewBox=\"0 0 {width} {height}\" role=\"img\" aria-label=\"{}\">",
            escape(title)
        ),
        "<rect width=\"100%\" height=\"100%\" fill=\"#ffffff\"/>".to_owned(),
        format!(
            "<text x=\"24\" y=\"32\" font-family=\"sans-serif\" font-size=\"20\">{}</text>",
            escape(title)
        ),
        format!(
            "<text x=\"354\" y=\"57\" font-family=\"sans-serif\" font-size=\"12\">{}</text>",
            escape(unit)
        ),
    ];
    for (index, (label, value)) in labels.iter().zip(values).enumerate() {
        let y = 76 + 38 * index;
        lines.push(format!(
            "<text x=\"24\" y=\"{}\" font-family=\"sans-serif\" font-size=\"13\">{}</text>",
            y + 16,
            escape(label)
        ));
        lines.push(format!(
            "<rect x=\"354\" y=\"{y}\" width=\"{:.3}\" height=\"22\" fill=\"#24579b\"/>",
            value * scale
        ));
        lines.push(format!(
            "<text x=\"{:.3}\" y=\"{}\" font-family=\"sans-serif\" font-size=\"12\">{}</text>",
            930.0_f64.min(362.0 + value * scale),
            y + 16,
            general(*value)
        ));
    }
    lines.push("</svg>".to_owned());
    format!("{}\n", lines.join("\n")).into_bytes()
}

/// The plots of the available metrics, in Python's `_plots` order.
fn plots(report: &Value) -> Vec<(String, Vec<u8>)> {
    let status = report["evidence_status"].as_str().expect("evidence status");
    let percentile = |block: &Value| -> (Vec<String>, Vec<f64>) {
        block
            .as_object()
            .expect("summary block")
            .iter()
            .filter(|(_, data)| !data["p99_ticks"].is_null())
            .map(|(name, data)| (name.clone(), data["p99_ticks"].as_f64().expect("ticks")))
            .unzip()
    };
    let mut files = Vec::new();
    let (labels, values) = percentile(&report["events"]["intervals"]);
    files.push((
        "interval_p99.svg".to_owned(),
        svg_plot(
            &format!("99th percentile event intervals ({status})"),
            &labels,
            &values,
            "clock ticks",
        ),
    ));
    let (labels, values) = percentile(&report["events"]["jitter"]);
    files.push((
        "jitter_p99.svg".to_owned(),
        svg_plot(
            &format!("99th percentile absolute adjacent-cycle latency change ({status})"),
            &labels,
            &values,
            "clock ticks",
        ),
    ));
    let energy = &report["energy"];
    if energy["status"] == "available" {
        let (labels, values): (Vec<String>, Vec<f64>) = energy["per_rail"]
            .as_object()
            .expect("rails")
            .iter()
            .map(|(rail, value)| (rail.clone(), value.as_f64().expect("energy")))
            .unzip();
        files.push((
            "energy_per_cycle.svg".to_owned(),
            svg_plot(
                &format!("Mean rail energy per cycle ({status})"),
                &labels,
                &values,
                "J/cycle",
            ),
        ));
    }
    files
}

#[cfg(test)]
#[path = "../tests/unit/control_outputs.rs"]
mod tests;
