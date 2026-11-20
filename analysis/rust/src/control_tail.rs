// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — tail quantile intervals and weakly-hard deadline metrics

//! Block-bootstrap intervals of tail quantiles and consecutive deadline-miss
//! metrics, as the Python module `tail_statistics` computes them.
//!
//! Every resample comes from the same SplitMix64 sequence with the same seed,
//! block starts are the generator's outputs modulo the number of starting
//! positions, and quantiles use Python's floating-point operations in Python's
//! order, so both analyses report the same intervals bit for bit.

use serde_json::{Map, Value, json};

/// SplitMix64 seed of every resampling.
const SEED: u64 = 0x4C54_572D_5441_494C;
/// Bootstrap resamples per distribution.
const RESAMPLES: usize = 1000;
/// Coverage of the percentile intervals.
const CONFIDENCE: f64 = 0.95;
/// Expected samples beyond a quantile that make it reportable.
const TAIL_SAMPLES: usize = 10;
/// Reported quantiles, by report name and probability in thousandths.
const QUANTILES: [(&str, usize); 3] = [("p95_ticks", 950), ("p99_ticks", 990), ("p999_ticks", 999)];
/// Window lengths `K` of the weakly-hard metrics, in consecutive deadlines.
const WINDOWS: [usize; 8] = [2, 3, 5, 10, 20, 50, 100, 1000];

/// The SplitMix64 generator of Steele, Lea and Flood.
struct SplitMix64 {
    state: u64,
}

impl SplitMix64 {
    /// The next 64-bit output.
    fn next(&mut self) -> u64 {
        self.state = self.state.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut value = self.state;
        value = (value ^ (value >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        value = (value ^ (value >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        value ^ (value >> 31)
    }
}

/// The Type-7 quantile of non-empty ascending tick samples.
fn ticks_quantile(ordered: &[u64], probability: f64) -> f64 {
    let position = (ordered.len() - 1) as f64 * probability;
    let (low, high) = (position.floor(), position.ceil());
    let (lower, upper) = (ordered[low as usize], ordered[high as usize]);
    lower as f64 + (upper - lower) as f64 * (position - low)
}

/// The Type-7 quantile of non-empty ascending estimates.
fn estimate_quantile(ordered: &[f64], probability: f64) -> f64 {
    let position = (ordered.len() - 1) as f64 * probability;
    let (low, high) = (position.floor(), position.ceil());
    let (lower, upper) = (ordered[low as usize], ordered[high as usize]);
    lower + (upper - lower) * (position - low)
}

/// The smallest block length whose fourth power is at least the sample count.
fn block_length(count: usize) -> usize {
    let mut length = 1_usize;
    while (length as u128).pow(4) < count as u128 {
        length += 1;
    }
    length
}

/// Tail quantiles of one interval series in cycle order with their block-bootstrap intervals:
/// the sample count, block length, resamples and confidence, and per quantile its Type-7
/// estimate, whether it is reportable and the interval bounds.
pub fn tail_quantiles(values: &[u64]) -> Value {
    let count = values.len();
    let reportable =
        QUANTILES.map(|(_, thousandths)| count * (1000 - thousandths) >= TAIL_SAMPLES * 1000);
    let mut ordered = values.to_vec();
    ordered.sort_unstable();
    let length = if count == 0 { 0 } else { block_length(count) };
    let mut bounds: [Option<(f64, f64)>; 3] = [None; 3];
    if reportable.iter().any(|&flag| flag) {
        let mut generator = SplitMix64 { state: SEED };
        let starts = (count - length + 1) as u64;
        let blocks = count.div_ceil(length);
        let mut estimates: [Vec<f64>; 3] = [Vec::new(), Vec::new(), Vec::new()];
        let mut resample = Vec::with_capacity(blocks * length);
        for _ in 0..RESAMPLES {
            resample.clear();
            for _ in 0..blocks {
                let start = (generator.next() % starts) as usize;
                resample.extend_from_slice(&values[start..start + length]);
            }
            resample.truncate(count);
            resample.sort_unstable();
            for (index, (_, thousandths)) in QUANTILES.iter().enumerate() {
                estimates[index].push(ticks_quantile(&resample, *thousandths as f64 / 1000.0));
            }
        }
        let tail = (1.0 - CONFIDENCE) / 2.0;
        for index in 0..QUANTILES.len() {
            if reportable[index] {
                let ranked = &mut estimates[index];
                ranked.sort_by(f64::total_cmp);
                bounds[index] = Some((
                    estimate_quantile(ranked, tail),
                    estimate_quantile(ranked, 1.0 - tail),
                ));
            }
        }
    }
    let mut quantiles = Map::new();
    for (index, (name, thousandths)) in QUANTILES.iter().enumerate() {
        let estimate = if count == 0 {
            Value::Null
        } else {
            json!(ticks_quantile(&ordered, *thousandths as f64 / 1000.0))
        };
        let (lower, upper) = match bounds[index] {
            Some((lower, upper)) => (json!(lower), json!(upper)),
            None => (Value::Null, Value::Null),
        };
        quantiles.insert(
            (*name).to_owned(),
            json!({"estimate": estimate, "reportable": reportable[index], "lower": lower, "upper": upper}),
        );
    }
    json!({
        "sample_count": count,
        "block_length": length,
        "resamples": if bounds.iter().any(Option::is_some) { RESAMPLES } else { 0 },
        "confidence": CONFIDENCE,
        "quantiles": quantiles,
    })
}

/// Consecutive deadline-miss metrics of one run's observed deadlines, in cycle order.
pub fn weakly_hard(misses: &[bool]) -> Value {
    let (mut longest, mut run) = (0_usize, 0_usize);
    for &missed in misses {
        run = if missed { run + 1 } else { 0 };
        longest = longest.max(run);
    }
    let mut windows = Map::new();
    for window in WINDOWS {
        let largest = (window <= misses.len()).then(|| {
            let mut current = misses[..window].iter().filter(|&&missed| missed).count();
            let mut largest = current;
            for index in window..misses.len() {
                current =
                    current + usize::from(misses[index]) - usize::from(misses[index - window]);
                largest = largest.max(current);
            }
            largest
        });
        windows.insert(window.to_string(), json!(largest));
    }
    json!({
        "observed_deadlines": misses.len(),
        "longest_miss_run": longest,
        "maximum_misses_in_window": windows,
    })
}

#[cfg(test)]
#[path = "../tests/unit/control_tail.rs"]
mod tests;
