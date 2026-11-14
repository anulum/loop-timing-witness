// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — observed tracking and fault schedule of an AMP capture

//! Convert an AMP capture's raw observations and fault schedule to the public
//! run contract as the Python module `amp_capture_observations` does.
//!
//! [`tracking_csv`] writes the observed rows as Python's `csv.writer` writes
//! them, with each Q8.24 value as `str(Decimal(raw) / 2**24)`;
//! [`fault_schedule`] reads the admitted configuration's fault fields.
//!
//! [`tracking_csv`]: crate::amp_observations::tracking_csv
//! [`fault_schedule`]: crate::amp_observations::fault_schedule

use crate::amp_run_input::{native_words, read_amp_run, unsigned};
use crate::amp_tracking::decode_tracking;
use serde_json::{Value, json};

/// Fractional binary digits of the Q8.24 format.
const FRACTION_BITS: u32 = 24;

/// Python's `str(Decimal(raw) / 2**24)`.
///
/// The quotient is exact: `raw * 5**24 / 10**24`. Python's division gives it
/// the exponent nearest zero that holds it exactly, and `str` writes it as
/// `Decimal.to_sci_string` does: plainly while the digits left of the point
/// number more than -6, otherwise with one digit before the point and an
/// exponent.
pub(crate) fn q24_text(raw: i32) -> String {
    let mut coefficient = u128::from(raw.unsigned_abs()) * 5_u128.pow(FRACTION_BITS);
    let mut exponent = -i64::from(FRACTION_BITS);
    while exponent < 0 && coefficient.is_multiple_of(10) {
        coefficient /= 10;
        exponent += 1;
    }
    let digits = coefficient.to_string();
    let left = exponent + i64::try_from(digits.len()).expect("a short coefficient");
    let sign = if raw < 0 { "-" } else { "" };
    let body = match usize::try_from(left) {
        _ if left <= -6 => {
            let fraction = digits.get(1..).filter(|rest| !rest.is_empty());
            let fraction = fraction.map_or_else(String::new, |rest| format!(".{rest}"));
            format!("{}{fraction}E{:+}", &digits[..1], left - 1)
        }
        Ok(point) if point >= digits.len() => digits,
        Ok(point) if point > 0 => format!("{}.{}", &digits[..point], &digits[point..]),
        _ => format!(
            "0.{}{digits}",
            "0".repeat(usize::try_from(-left).expect("a fraction"))
        ),
    };
    format!("{sign}{body}")
}

/// Python's `tracking_csv`: the observed rows as reproducible CSV bytes.
///
/// # Errors
///
/// The raw tracking's refusal text, as [`decode_tracking`] gives it.
pub fn tracking_csv(content: &[u8], cycles: u32, samples: u64) -> Result<Vec<u8>, String> {
    let mut text = String::from("cycle,reference,output\r\n");
    for row in decode_tracking(content, cycles, samples)? {
        let (reference, output) = (q24_text(row.reference), q24_text(row.output));
        text.push_str(&format!("{},{reference},{output}\r\n", row.cycle));
    }
    Ok(text.into_bytes())
}

/// Python's `fault_schedule`: the configured fault, or none.
///
/// # Errors
///
/// The run configuration's refusal text, as `read_amp_run` gives it.
pub fn fault_schedule(configuration: &[u8]) -> Result<Value, String> {
    read_amp_run(configuration)?;
    let words = native_words(configuration)?;
    let fault = words[19];
    if fault == "none" {
        return Ok(json!([]));
    }
    let cycle = unsigned(words[20])?;
    let delay = if fault == "delay" {
        unsigned(words[21])?
    } else {
        0
    };
    let kind = if fault == "overload" {
        "overload_request"
    } else {
        fault
    };
    Ok(json!([{"cycle": cycle, "kind": kind, "delay_periods": delay}]))
}

#[cfg(test)]
#[path = "../tests/unit/amp_observations.rs"]
mod tests;
