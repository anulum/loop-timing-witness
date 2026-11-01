// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — decoded JSON numbers with Python arithmetic and text

//! Compute and print decoded JSON numbers as the Python analysis does.
//!
//! A schema `integer` admits an integral float such as `16.0`, which Python
//! keeps as a float: sums and products with it are floats, comparisons with
//! integers are exact, and messages print it as `16.0`. The rules that use
//! these numbers only see schema-checked, non-negative values within the
//! 64-bit range, so every integer product they form fits `u128`.

use serde_json::Value;
use std::cmp::Ordering;
use std::fmt;

/// A non-negative decoded number, kept as Python keeps it.
#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) enum Num {
    /// A Python `int`.
    Int(u128),
    /// A Python `float`.
    Float(f64),
}

impl Num {
    /// Read a schema-checked non-negative number from a decoded value.
    pub(crate) fn of(value: &Value) -> Self {
        match value.as_u64() {
            Some(integer) => Self::Int(u128::from(integer)),
            None => Self::Float(value.as_f64().expect("schema-checked number")),
        }
    }

    /// Python `self + other`.
    pub(crate) fn add(self, other: Self) -> Self {
        match (self, other) {
            (Self::Int(left), Self::Int(right)) => Self::Int(left + right),
            _ => Self::Float(self.float() + other.float()),
        }
    }

    /// Python `self * other`.
    pub(crate) fn mul(self, other: Self) -> Self {
        match (self, other) {
            (Self::Int(left), Self::Int(right)) => Self::Int(left * right),
            _ => Self::Float(self.float() * other.float()),
        }
    }

    /// Python `2 ** self` for an exponent of at most 64.
    pub(crate) fn power_of_two(self) -> Self {
        match self {
            Self::Int(exponent) => Self::Int(1 << exponent),
            Self::Float(exponent) => Self::Float(2.0_f64.powf(exponent)),
        }
    }

    /// The value converted to a float, rounding to nearest as Python does.
    fn float(self) -> f64 {
        match self {
            Self::Int(integer) => integer as f64,
            Self::Float(float) => float,
        }
    }

    /// Compare exactly, as Python compares an `int` with a `float`.
    pub(crate) fn compare(self, other: Self) -> Ordering {
        match (self, other) {
            (Self::Int(left), Self::Int(right)) => left.cmp(&right),
            (Self::Float(left), Self::Float(right)) => left.total_cmp(&right),
            (Self::Float(float), Self::Int(integer)) => float_against(float, integer),
            (Self::Int(integer), Self::Float(float)) => float_against(float, integer).reverse(),
        }
    }

    /// Python `self == other`.
    pub(crate) fn same(self, other: Self) -> bool {
        self.compare(other) == Ordering::Equal
    }
}

/// Compare a finite non-negative float with an integer without rounding the integer.
fn float_against(float: f64, integer: u128) -> Ordering {
    let floor = float.floor();
    if floor >= 3.4e38 {
        return Ordering::Greater;
    }
    match (floor as u128).cmp(&integer) {
        Ordering::Equal if float > floor => Ordering::Greater,
        ordering => ordering,
    }
}

impl fmt::Display for Num {
    /// Print as Python's `str`: an integer in decimal, a float as `repr`.
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Int(integer) => write!(formatter, "{integer}"),
            Self::Float(float) => formatter.write_str(&python_float(*float)),
        }
    }
}

/// Print a finite float as Python's `repr`: the shortest round-trip digits,
/// positional for decimal exponents from -4 to 15 with at least one fraction
/// digit, otherwise scientific with a signed exponent of at least two digits.
pub(crate) fn python_float(value: f64) -> String {
    let scientific = format!("{value:e}");
    let (mantissa, exponent) = scientific.split_once('e').expect("scientific notation");
    let exponent: i32 = exponent.parse().expect("decimal exponent");
    let (sign, mantissa) = match mantissa.strip_prefix('-') {
        Some(unsigned) => ("-", unsigned),
        None => ("", mantissa),
    };
    let digits = mantissa.replace('.', "");
    if (-4..16).contains(&exponent) {
        let point = exponent + 1;
        let body = if point <= 0 {
            format!("0.{}{digits}", "0".repeat(point.unsigned_abs() as usize))
        } else if point as usize >= digits.len() {
            format!("{digits}{}.0", "0".repeat(point as usize - digits.len()))
        } else {
            format!(
                "{}.{}",
                &digits[..point as usize],
                &digits[point as usize..]
            )
        };
        return format!("{sign}{body}");
    }
    let marker = if exponent < 0 { '-' } else { '+' };
    format!("{sign}{mantissa}e{marker}{:02}", exponent.unsigned_abs())
}

/// Print a decoded JSON number as Python's `str` of the decoded value.
pub(crate) fn python_number(value: &Value) -> String {
    match value.as_i64() {
        Some(integer) => integer.to_string(),
        None => match value.as_u64() {
            Some(integer) => integer.to_string(),
            None => python_float(value.as_f64().expect("decoded number")),
        },
    }
}

#[cfg(test)]
#[path = "../tests/unit/control_number.rs"]
mod tests;
