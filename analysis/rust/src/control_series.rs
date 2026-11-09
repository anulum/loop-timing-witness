// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — tracking and energy series of a control run

//! Tracking error and energy per cycle, as Python's `run_series` and
//! `tracking_observations` compute them.
//!
//! The series are hash-bound CSV tables. Their values are exact decimals with
//! every sum, product and quotient correctly rounded to 28 digits, and the
//! report holds the correctly rounded floats of the results. The refusal texts
//! and their order are Python's.

use crate::control_csv::{DictRows, Row};
use crate::control_decimal::{Decimal, count, measurement};
use crate::control_events::{Event, Names};
use crate::control_text::python_repr;
use serde_json::{Map, Value, json};
use std::collections::{BTreeMap, BTreeSet};

/// Header of a tracking table.
const TRACKING_COLUMNS: [&str; 3] = ["cycle", "reference", "output"];
/// Header of a power table.
const POWER_COLUMNS: [&str; 5] = [
    "timebase_ticks",
    "rail",
    "voltage_v",
    "current_a",
    "energy_j",
];

/// Complete data rows of one series table, as `run_series._rows` reads them.
fn rows(content: &[u8], columns: &[&str]) -> Result<Vec<Vec<String>>, String> {
    let text = std::str::from_utf8(content).map_err(|_| "series file is not UTF-8".to_owned())?;
    let invalid = |error: String| format!("invalid CSV: {error}");
    let (header, rows) = DictRows::new(text).map_err(invalid)?;
    if header.unwrap_or_default() != columns {
        return Err(format!("CSV header must be {}", columns.join(",")));
    }
    let rows: Vec<Row> = rows.collect::<Result<_, _>>().map_err(invalid)?;
    let incomplete = || "CSV has no data or contains an incomplete row".to_owned();
    let mut complete = Vec::with_capacity(rows.len());
    for row in rows {
        let Row::Complete(cells) = row else {
            return Err(incomplete());
        };
        complete.push(cells);
    }
    if complete.is_empty() {
        return Err(incomplete());
    }
    Ok(complete)
}

/// The analysed cycles of a run: from the warm-up count up to the cycle count.
fn analysed(warmup_cycles: u64, cycle_count: u64) -> std::ops::Range<u64> {
    warmup_cycles..cycle_count
}

/// Mean square and peak magnitude of nonempty errors, as report floats.
fn error_metrics(errors: &[&Decimal]) -> (f64, f64) {
    let total = errors
        .iter()
        .fold(Decimal::zero(), |sum, error| sum.add(&error.mul(error)));
    let mean_square = total.divide(u64::try_from(errors.len()).expect("count"));
    let peak = errors
        .iter()
        .map(|error| error.abs())
        .max()
        .expect("nonempty errors");
    (mean_square.float().sqrt(), peak.float())
}

/// RMS and peak absolute error from one tracking row per control cycle, as
/// Python's `tracking_error`.
pub(crate) fn tracking_error(
    content: Option<&[u8]>,
    cycle_count: u64,
    warmup_cycles: u64,
    unit: &str,
) -> Result<Map<String, Value>, String> {
    let Some(content) = content else {
        return Ok(object(json!({
            "status": "unavailable",
            "reason": "tracking file not supplied",
            "unit": unit,
        })));
    };
    let mut observations: BTreeMap<u64, Decimal> = BTreeMap::new();
    for row in rows(content, &TRACKING_COLUMNS)? {
        let cycle = count(&row[0], "cycle")?;
        if cycle >= cycle_count || observations.contains_key(&cycle) {
            return Err(format!(
                "tracking cycle {cycle} is duplicated or outside the run"
            ));
        }
        let reference = measurement(&row[1], "reference")?;
        let output = measurement(&row[2], "output")?;
        observations.insert(cycle, reference.sub(&output));
    }
    let errors: Option<Vec<&Decimal>> = analysed(warmup_cycles, cycle_count)
        .map(|cycle| observations.get(&cycle))
        .collect();
    let errors = errors.ok_or_else(|| "tracking file lacks an analysed cycle".to_owned())?;
    let (rms, peak) = error_metrics(&errors);
    Ok(object(json!({
        "status": "available",
        "unit": unit,
        "sample_count": errors.len(),
        "rms": rms,
        "peak_absolute": peak,
    })))
}

/// Observed tracking errors by cycle, as `tracking_observations._observations` reads them.
fn observations(content: &[u8], cycle_count: u64) -> Result<BTreeMap<u64, Decimal>, String> {
    let text = std::str::from_utf8(content)
        .map_err(|_| "observed tracking file is not UTF-8".to_owned())?;
    let invalid = |error: String| format!("invalid observed tracking CSV: {error}");
    let (header, rows) = DictRows::new(text).map_err(invalid)?;
    if header.unwrap_or_default() != TRACKING_COLUMNS {
        return Err("observed tracking CSV header must be cycle,reference,output".to_owned());
    }
    let mut result = BTreeMap::new();
    for row in rows {
        let Row::Complete(cells) = row.map_err(invalid)? else {
            return Err("observed tracking contains an incomplete row".to_owned());
        };
        let cycle = count(&cells[0], "observed tracking cycle")?;
        if cycle >= cycle_count || result.contains_key(&cycle) {
            return Err("observed tracking cycle is duplicated or outside the run".to_owned());
        }
        let reference = measurement(&cells[1], "observed tracking reference")?;
        let output = measurement(&cells[2], "observed tracking output")?;
        result.insert(cycle, reference.sub(&output));
    }
    Ok(result)
}

/// Tracking error over the captured sample reads only, as Python's
/// `observed_tracking_error`; missing cycles stay listed and are never filled.
pub(crate) fn observed_tracking_error(
    content: &[u8],
    events: &[Event],
    names: &Names,
    cycle_count: u64,
    warmup_cycles: u64,
    unit: &str,
) -> Result<Map<String, Value>, String> {
    let observations = observations(content, cycle_count)?;
    let captured: BTreeSet<u64> = events
        .iter()
        .filter(|event| names.get(event.code) == Some("SAMPLE_READ"))
        .map(|event| u64::from(event.cycle))
        .collect();
    if !observations.keys().copied().eq(captured.iter().copied()) {
        return Err("observed tracking cycles do not match captured SAMPLE_READ events".to_owned());
    }
    let (selected, missing): (Vec<u64>, Vec<u64>) =
        analysed(warmup_cycles, cycle_count).partition(|cycle| observations.contains_key(cycle));
    let expected = cycle_count - warmup_cycles;
    // Both counts are exact floats here, so this is Python's correctly rounded int division.
    let coverage = selected.len() as f64 / expected as f64;
    let mut result = object(json!({
        "status": if missing.is_empty() { "available" } else { "partial" },
        "sampling": "observed",
        "unit": unit,
        "sample_count": selected.len(),
        "expected_cycle_count": expected,
        "missing_cycles": missing,
        "coverage_fraction": coverage,
    }));
    if selected.is_empty() {
        result.insert("status".to_owned(), json!("unavailable"));
        result.insert(
            "reason".to_owned(),
            json!("no observed post-warmup samples"),
        );
        return Ok(result);
    }
    let errors: Vec<&Decimal> = selected.iter().map(|cycle| &observations[cycle]).collect();
    let (rms, peak) = error_metrics(&errors);
    result.insert("rms".to_owned(), json!(rms));
    result.insert("peak_absolute".to_owned(), json!(peak));
    Ok(result)
}

/// Cumulative joules by fabric tick and rail, as `run_series._power_samples` reads them.
fn power_samples(
    content: &[u8],
    rails: &[&str],
) -> Result<BTreeMap<u64, BTreeMap<String, Decimal>>, String> {
    let mut samples: BTreeMap<u64, BTreeMap<String, Decimal>> = BTreeMap::new();
    for row in rows(content, &POWER_COLUMNS)? {
        let ticks = count(&row[0], "timebase_ticks")?;
        let rail = &row[1];
        let sample = samples.entry(ticks).or_default();
        if !rails.contains(&rail.as_str()) || sample.contains_key(rail) {
            return Err(format!(
                "power rail {} is unknown or duplicated at tick {ticks}",
                python_repr(rail)
            ));
        }
        let mut energy = Decimal::zero();
        for (index, field) in POWER_COLUMNS.iter().enumerate().skip(2) {
            let value = measurement(&row[index], field)?;
            if value.is_negative() {
                return Err(format!("{field} cannot be negative"));
            }
            energy = value;
        }
        sample.insert(rail.clone(), energy);
    }
    let complete = samples.len() >= 2 && samples.values().all(|sample| sample.len() == rails.len());
    if !complete {
        return Err("power file needs at least two complete four-rail samples".to_owned());
    }
    Ok(samples)
}

/// Python's built-in `sum` of floats from an integer start of zero: the first
/// value is added to the integer, the rest with Neumaier's compensation, as
/// CPython 3.12 and later do.
pub(crate) fn python_sum(values: &[f64]) -> f64 {
    let Some((&first, rest)) = values.split_first() else {
        return 0.0;
    };
    let mut total = 0.0 + first;
    let mut compensation = 0.0;
    for &value in rest {
        let sum = total + value;
        if total.abs() >= value.abs() {
            compensation += (total - sum) + value;
        } else {
            compensation += (value - sum) + total;
        }
        total = sum;
    }
    if compensation != 0.0 && compensation.is_finite() {
        total += compensation;
    }
    total
}

/// Mean energy per cycle over counter-aligned power windows, as Python's
/// `energy_per_cycle`.
pub(crate) fn energy_per_cycle(
    content: Option<&[u8]>,
    events: &[Event],
    names: &Names,
    profile: &str,
    warmup_cycles: u64,
    rails: &[&str],
) -> Result<Map<String, Value>, String> {
    let Some(content) = content else {
        return Ok(object(json!({
            "status": "unavailable",
            "reason": "power file not supplied",
        })));
    };
    let samples = power_samples(content, rails)?;
    let anchor = if profile == "CONTROL" {
        "SAMPLE_READY"
    } else {
        "INPUT_WRITE"
    };
    let mut cycle_ticks: Vec<u64> = events
        .iter()
        .filter(|event| {
            names.get(event.code) == Some(anchor) && u64::from(event.cycle) >= warmup_cycles
        })
        .map(|event| event.ticks)
        .collect();
    cycle_ticks.sort_unstable();
    let mut energy: Vec<Decimal> = rails.iter().map(|_| Decimal::zero()).collect();
    let (mut covered, mut windows) = (0_u64, 0_u64);
    let boundaries: Vec<(&u64, &BTreeMap<String, Decimal>)> = samples.iter().collect();
    for pair in boundaries.windows(2) {
        let ((&start, first), (&end, last)) = (pair[0], pair[1]);
        let inside = u64::try_from(
            cycle_ticks.partition_point(|&tick| tick < end)
                - cycle_ticks.partition_point(|&tick| tick < start),
        )
        .expect("count");
        if inside != 0 && warmup_cycles != 0 && start < cycle_ticks[0] {
            return Err("power window overlaps discarded warm-up cycles".to_owned());
        }
        for (total, rail) in energy.iter_mut().zip(rails) {
            let delta = last[*rail].sub(&first[*rail]);
            if delta.is_negative() {
                return Err(format!("cumulative energy decreases for {rail}"));
            }
            if inside != 0 {
                *total = total.add(&delta);
            }
        }
        if inside != 0 {
            covered += inside;
            windows += 1;
        }
    }
    if covered != u64::try_from(cycle_ticks.len()).expect("count") || covered == 0 {
        return Err("power windows do not cover every analysed cycle".to_owned());
    }
    let means: Vec<f64> = energy
        .iter()
        .map(|total| total.divide(covered).float())
        .collect();
    let per_rail: Map<String, Value> = rails
        .iter()
        .zip(&means)
        .map(|(rail, mean)| ((*rail).to_owned(), json!(mean)))
        .collect();
    Ok(object(json!({
        "status": "available",
        "unit": "J/cycle",
        "sample_count": covered,
        "window_count": windows,
        "per_rail": per_rail,
        "total": python_sum(&means),
    })))
}

/// The object of a JSON object literal.
fn object(value: Value) -> Map<String, Value> {
    value.as_object().cloned().expect("object literal")
}

#[cfg(test)]
#[path = "../tests/unit/control_series.rs"]
mod tests;
