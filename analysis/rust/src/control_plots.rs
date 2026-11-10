// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — SVG plots of a control report

//! Draw the report's labelled bar charts as Python's `report_outputs._plots`
//! and `_svg_plot` draw them, with `%.3f` and `%.6g` number text and
//! `xml.sax.saxutils.escape`.

use serde_json::Value;

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
pub(crate) fn plots(report: &Value) -> Vec<(String, Vec<u8>)> {
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
