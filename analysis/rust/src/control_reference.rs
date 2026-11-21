// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — fabric timebase against a pulse-per-second reference

//! Fit the fabric counter against the edges of a pulse-per-second reference.
//!
//! The first recorded edge anchors the reference. Each later edge is accepted
//! when its counter distance to the previous accepted edge is a whole, positive
//! number of seconds at the declared clock frequency, within one part in
//! `GLITCH_TOLERANCE`; other edges are counted as rejected and left out. The
//! accepted edges' seconds are the sums of those whole numbers, so a pulse the
//! reference did not send leaves a two-second step. The ordinary least-squares
//! line through (second, counter value) gives ticks per second, the scale
//! error against the declared clock in parts per million and the slope's
//! standard uncertainty from the residual variance, never below the counter's
//! quantization variance of `1/12` tick squared per edge, as the Python
//! `reference_timebase.reference_timebase` does. Every sum runs left to right
//! in plain `f64` arithmetic in Python's operation order, so both give the same
//! bits. The reference's own error is not inferred.

use crate::control_events::Edge;
use serde_json::{Value, json};

/// Scale of a relative error in parts per million.
const PARTS_PER_MILLION: f64 = 1_000_000.0;

/// Edges that determine a line; a residual variance needs one more.
const LINE_POINTS: usize = 2;

/// An accepted edge lies within one part in this many of a whole number of seconds.
const GLITCH_TOLERANCE: f64 = 1000.0;

/// Variance of one edge's counter value in ticks squared: a uniform error within one tick.
const QUANTIZATION_VARIANCE: f64 = 1.0 / 12.0;

/// Largest cumulative second count a float holds exactly (2^53); an edge beyond it is rejected.
const MAX_SECONDS: f64 = 9_007_199_254_740_992.0;

/// Sum floats left to right.
fn total(values: impl Iterator<Item = f64>) -> f64 {
    let mut sum = 0.0;
    for value in values {
        sum += value;
    }
    sum
}

/// Whole seconds and counter offsets of the edges a whole second apart.
///
/// `pulses` holds at least one edge; both lists start at the first edge.
fn accepted(pulses: &[Edge], clock_hz: f64) -> (Vec<f64>, Vec<f64>) {
    let first = pulses[0].ticks;
    let mut seconds = vec![0.0];
    let mut ticks = vec![0.0];
    let mut previous = first;
    for edge in &pulses[1..] {
        let elapsed = edge.ticks.wrapping_sub(previous) as f64;
        let whole = (elapsed / clock_hz + 0.5).floor();
        let last = seconds[seconds.len() - 1];
        if edge.ticks <= previous
            || whole < 1.0
            || last + whole > MAX_SECONDS
            || (elapsed - whole * clock_hz).abs() * GLITCH_TOLERANCE > whole * clock_hz
        {
            continue;
        }
        seconds.push(last + whole);
        ticks.push((edge.ticks - first) as f64);
        previous = edge.ticks;
    }
    (seconds, ticks)
}

/// The report's `reference_timebase` block of the pulse-per-second edges.
///
/// `pulses` are the edges of the `PPS` event in capture order; the block is
/// `null` without them. The fit values need two accepted edges, the
/// root-mean-square residual three.
pub(crate) fn reference_timebase(pulses: &[Edge], clock_hz: f64) -> Value {
    let (Some(first), Some(last)) = (pulses.first(), pulses.last()) else {
        return Value::Null;
    };
    let count = pulses.len();
    let (seconds, ticks) = accepted(pulses, clock_hz);
    let points = seconds.len();
    let mut block = json!({
        "event": "PPS",
        "edges": count,
        "first_sequence": first.sequence,
        "last_sequence": last.sequence,
        "missing_edges": u64::from(last.sequence - first.sequence) + 1 - count as u64,
        "rejected_edges": count - points,
        "seconds": seconds[points - 1] as u64,
        "ticks_per_second": null,
        "scale_error_ppm": null,
        "scale_standard_error_ppm": null,
        "residual_rms_ticks": null,
        "max_abs_residual_ticks": null,
    });
    if points < LINE_POINTS {
        return block;
    }
    let mean_seconds = total(seconds.iter().copied()) / points as f64;
    let mean_ticks = total(ticks.iter().copied()) / points as f64;
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
    let mut variance = QUANTIZATION_VARIANCE;
    if points > LINE_POINTS {
        variance = (squares / (points - LINE_POINTS) as f64).max(QUANTIZATION_VARIANCE);
        block["residual_rms_ticks"] = json!((squares / points as f64).sqrt());
    }
    block["ticks_per_second"] = json!(slope);
    block["scale_error_ppm"] = json!((slope - clock_hz) / clock_hz * PARTS_PER_MILLION);
    block["scale_standard_error_ppm"] =
        json!((variance / spread).sqrt() / clock_hz * PARTS_PER_MILLION);
    block["max_abs_residual_ticks"] = json!(largest);
    block
}

#[cfg(test)]
#[path = "../tests/unit/control_reference.rs"]
mod tests;
