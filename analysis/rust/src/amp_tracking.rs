// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — bounded raw controller observations of a capture

//! Decode the raw controller tracking a capture retains as the Python
//! function `native_tracking.decode_tracking` does.
//!
//! [`decode_tracking`] reads UTF-8 CSV text exactly as Python's
//! `csv.DictReader(strict=True)` reads it, requires the raw ABI header, admits
//! every cell's ASCII decimal syntax and field bound in row and header order,
//! and requires unique increasing cycles and the completion's sample count.
//! Every refusal is Python's text for the same first defect.
//!
//! [`decode_tracking`]: crate::amp_tracking::decode_tracking

use crate::control_csv::Records;

/// The raw controller ABI columns, in their only order.
const FIELDS: [&str; 13] = [
    "cycle",
    "reference_raw",
    "output_raw",
    "velocity_raw",
    "command_raw",
    "integral_raw",
    "derivative_raw",
    "clipped",
    "integral_held",
    "submitted",
    "sample_ticks",
    "irq_generation",
    "overload_work",
];
/// Digits of the widest bound, `u64::MAX`; a longer magnitude exceeds every bound.
const SIGNIFICANT_DIGITS: usize = 20;
/// The refusal of a missing, empty or excess cell.
const INCOMPLETE: &str = "native tracking contains an incomplete row";

/// One observed row: its cycle and raw Q8.24 reference and output.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct TrackingRow {
    /// Zero-based control cycle.
    pub cycle: u32,
    /// Raw Q8.24 reference.
    pub reference: i32,
    /// Raw Q8.24 plant output.
    pub output: i32,
}

/// The inclusive bounds of a column; the cycle lies inside the configured run.
fn bounds(column: usize, cycles: u32) -> (i128, i128) {
    match column {
        0 => (0, i128::from(cycles) - 1),
        1..=6 => (i128::from(i32::MIN), i128::from(i32::MAX)),
        7..=9 => (0, 1),
        _ => (0, i128::from(u64::MAX)),
    }
}

/// Python's `_integer`: one nonempty ASCII decimal cell within its bounds,
/// with any count of leading zeros.
fn integer(cell: Option<&String>, (low, high): (i128, i128)) -> Result<i128, String> {
    let Some(text) = cell.filter(|text| !text.is_empty()) else {
        return Err(INCOMPLETE.to_owned());
    };
    let digits = text.strip_prefix('-').unwrap_or(text);
    if digits.is_empty() || !digits.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err("native tracking integer is not ASCII decimal".to_owned());
    }
    let significant = digits.trim_start_matches('0');
    if significant.len() <= SIGNIFICANT_DIGITS {
        let magnitude = significant
            .bytes()
            .fold(0, |value, digit| value * 10 + i128::from(digit - b'0'));
        let value = if text.starts_with('-') {
            -magnitude
        } else {
            magnitude
        };
        if (low..=high).contains(&value) {
            return Ok(value);
        }
    }
    Err("native tracking integer is outside its ABI bounds".to_owned())
}

/// Decode one data record into its observed row.
fn row(record: &[String], cycles: u32) -> Result<TrackingRow, String> {
    if record.len() > FIELDS.len() {
        return Err(INCOMPLETE.to_owned());
    }
    let mut values = [0; FIELDS.len()];
    for (column, value) in values.iter_mut().enumerate() {
        *value = integer(record.get(column), bounds(column, cycles))?;
    }
    let narrow = |value: i128| i32::try_from(value).expect("an admitted 32-bit field");
    Ok(TrackingRow {
        cycle: u32::try_from(values[0]).expect("an admitted cycle"),
        reference: narrow(values[1]),
        output: narrow(values[2]),
    })
}

/// Validate every raw ABI column and keep the ordered observations.
///
/// `cycles` is the configured cycle count and `sample_count` the
/// completion's sample count.
///
/// # Errors
///
/// Python's refusal text when the bytes are not UTF-8, the CSV is malformed,
/// the header differs from the raw ABI, a row is incomplete, a cell is not
/// ASCII decimal or lies outside its bounds, the cycles are not unique and
/// increasing, or the row count differs from `sample_count`.
pub fn decode_tracking(
    content: &[u8],
    cycles: u32,
    sample_count: u64,
) -> Result<Vec<TrackingRow>, String> {
    let malformed = |_| "native tracking contains malformed CSV".to_owned();
    let text = std::str::from_utf8(content).map_err(|_| "native tracking is not UTF-8")?;
    let mut records = Records::new(text);
    let header = records.next().transpose().map_err(malformed)?;
    if header.is_none_or(|names| names != FIELDS) {
        return Err("native tracking header does not match the raw controller ABI".to_owned());
    }
    let mut rows: Vec<TrackingRow> = Vec::new();
    for record in records {
        let record = record.map_err(malformed)?;
        if record.is_empty() {
            continue;
        }
        let observed = row(&record, cycles)?;
        if rows.last().is_some_and(|last| observed.cycle <= last.cycle) {
            return Err("native tracking cycles must be unique and increasing".to_owned());
        }
        rows.push(observed);
    }
    if rows.len() as u64 != sample_count {
        return Err("native sample count does not match tracking rows".to_owned());
    }
    Ok(rows)
}
