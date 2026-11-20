// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — fabric timebase against a pulse-per-second reference

//! Fit the fabric counter against the edges of a pulse-per-second reference.
//!
//! The ordinary least-squares line through (sequence number, counter value)
//! gives ticks per second, the scale error against the declared clock in parts
//! per million and the slope's standard error from the residuals, as the
//! Python `reference_timebase.reference_timebase` does. Every sum runs left to
//! right in plain `f64` arithmetic in Python's operation order, so both give the
//! same bits. The reference's own error is not inferred.

use crate::control_events::Edge;
use serde_json::{Value, json};

/// Scale of a relative error in parts per million.
const PARTS_PER_MILLION: f64 = 1_000_000.0;

/// Edges that determine a line; a standard error needs one more.
const LINE_POINTS: usize = 2;

/// Sum floats left to right.
fn total(values: impl Iterator<Item = f64>) -> f64 {
    let mut sum = 0.0;
    for value in values {
        sum += value;
    }
    sum
}

/// The report's `reference_timebase` block of the pulse-per-second edges.
///
/// `pulses` are the edges of the `PPS` event in capture order; the block is
/// `null` without them. The fit values need two edges, the standard error and
/// the root-mean-square residual three.
pub(crate) fn reference_timebase(pulses: &[Edge], clock_hz: f64) -> Value {
    let (Some(first), Some(last)) = (pulses.first(), pulses.last()) else {
        return Value::Null;
    };
    let count = pulses.len();
    let mut block = json!({
        "event": "PPS",
        "edges": count,
        "first_sequence": first.sequence,
        "last_sequence": last.sequence,
        "missing_edges": u64::from(last.sequence - first.sequence) + 1 - count as u64,
        "ticks_per_second": null,
        "scale_error_ppm": null,
        "scale_standard_error_ppm": null,
        "residual_rms_ticks": null,
        "max_abs_residual_ticks": null,
    });
    if count < LINE_POINTS {
        return block;
    }
    let seconds: Vec<f64> = pulses
        .iter()
        .map(|edge| f64::from(edge.sequence - first.sequence))
        .collect();
    let ticks: Vec<f64> = pulses
        .iter()
        .map(|edge| (edge.ticks - first.ticks) as f64)
        .collect();
    let mean_seconds = total(seconds.iter().copied()) / count as f64;
    let mean_ticks = total(ticks.iter().copied()) / count as f64;
    let spread = total(
        seconds
            .iter()
            .map(|x| (x - mean_seconds) * (x - mean_seconds)),
    );
    let covariance = total(
        seconds
            .iter()
            .zip(&ticks)
            .map(|(x, y)| (x - mean_seconds) * (y - mean_ticks)),
    );
    let slope = covariance / spread;
    let residuals: Vec<f64> = seconds
        .iter()
        .zip(&ticks)
        .map(|(x, y)| (y - mean_ticks) - slope * (x - mean_seconds))
        .collect();
    let squares = total(residuals.iter().map(|residual| residual * residual));
    let largest = residuals
        .iter()
        .map(|residual| residual.abs())
        .fold(0.0, f64::max);
    block["ticks_per_second"] = json!(slope);
    block["scale_error_ppm"] = json!((slope - clock_hz) / clock_hz * PARTS_PER_MILLION);
    block["max_abs_residual_ticks"] = json!(largest);
    if count > LINE_POINTS {
        block["scale_standard_error_ppm"] = json!(
            (squares / (count - LINE_POINTS) as f64 / spread).sqrt() / clock_hz * PARTS_PER_MILLION
        );
        block["residual_rms_ticks"] = json!((squares / count as f64).sqrt());
    }
    block
}

#[cfg(test)]
#[path = "../tests/unit/control_reference.rs"]
mod tests;
