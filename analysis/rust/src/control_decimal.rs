// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — Python decimal arithmetic of the run series

//! Series values and their arithmetic as Python's `decimal` computes them.
//!
//! The Python analysis parses measurements with `run_series.measurement` and
//! counts with `run_series.count`, then sums, multiplies and divides them in
//! the default context: 28 significant digits, rounding half to even. Every
//! operation there is exact and then correctly rounded to that precision, so a
//! result depends only on the operands' values. [`Decimal`] keeps exact values
//! and rounds each result the same way; the measurement bounds keep every
//! result far inside the context's exponent limits and the float range.

use std::cmp::Ordering;

/// Significant digits of the default decimal context.
const PRECISION: usize = 28;
/// Largest accepted decimal exponent of a measurement's leading digit.
const EXPONENT: i64 = 99;
/// Longest accepted exponent text, without sign and leading zeros.
const EXPONENT_DIGITS: usize = 6;
/// Decimal digits of one limb.
const LIMB_DIGITS: usize = 9;
/// The limb base.
const BASE: u64 = 1_000_000_000;

/// A nonnegative integer in little-endian base-10⁹ limbs, without leading zero limbs.
#[derive(Clone, Debug, PartialEq, Eq)]
struct Big(Vec<u32>);

impl Big {
    /// Zero.
    fn zero() -> Self {
        Self(Vec::new())
    }

    /// A small value.
    fn small(value: u64) -> Self {
        let mut limbs = Vec::new();
        let mut rest = value;
        while rest != 0 {
            limbs.push(u32::try_from(rest % BASE).expect("limb"));
            rest /= BASE;
        }
        Self(limbs)
    }

    /// The value of a nonempty ASCII digit string.
    fn digits(text: &str) -> Self {
        let mut limbs: Vec<u32> = text
            .as_bytes()
            .rchunks(LIMB_DIGITS)
            .map(|chunk| {
                chunk
                    .iter()
                    .fold(0, |limb, &digit| limb * 10 + u32::from(digit - b'0'))
            })
            .collect();
        trim(&mut limbs);
        Self(limbs)
    }

    /// Whether the value is zero.
    fn is_zero(&self) -> bool {
        self.0.is_empty()
    }

    /// Decimal digits of the value; zero has none.
    fn digit_count(&self) -> usize {
        self.0.last().map_or(0, |&top| {
            (self.0.len() - 1) * LIMB_DIGITS + top.to_string().len()
        })
    }

    /// Value times 10^`power`.
    fn scale(&self, power: usize) -> Self {
        if self.is_zero() {
            return Self::zero();
        }
        let mut limbs = vec![0; power / LIMB_DIGITS];
        limbs.extend_from_slice(&self.0);
        let factor = 10_u64.pow(u32::try_from(power % LIMB_DIGITS).expect("small power"));
        let mut carry = 0;
        for limb in &mut limbs {
            let product = u64::from(*limb) * factor + carry;
            *limb = u32::try_from(product % BASE).expect("limb");
            carry = product / BASE;
        }
        if carry != 0 {
            limbs.push(u32::try_from(carry).expect("limb"));
        }
        Self(limbs)
    }

    /// Sum.
    fn add(&self, other: &Self) -> Self {
        let mut limbs = Vec::with_capacity(self.0.len().max(other.0.len()) + 1);
        let mut carry = 0;
        for index in 0..self.0.len().max(other.0.len()) {
            let total = u64::from(self.0.get(index).copied().unwrap_or(0))
                + u64::from(other.0.get(index).copied().unwrap_or(0))
                + carry;
            limbs.push(u32::try_from(total % BASE).expect("limb"));
            carry = total / BASE;
        }
        if carry != 0 {
            limbs.push(1);
        }
        Self(limbs)
    }

    /// Difference of a value not below `other`.
    fn sub(&self, other: &Self) -> Self {
        let mut limbs = Vec::with_capacity(self.0.len());
        let mut borrow = 0;
        for (index, &limb) in self.0.iter().enumerate() {
            let subtrahend = u64::from(other.0.get(index).copied().unwrap_or(0)) + borrow;
            let minuend = u64::from(limb);
            let (digit, next) = if minuend >= subtrahend {
                (minuend - subtrahend, 0)
            } else {
                (minuend + BASE - subtrahend, 1)
            };
            limbs.push(u32::try_from(digit).expect("limb"));
            borrow = next;
        }
        trim(&mut limbs);
        Self(limbs)
    }

    /// Product.
    fn mul(&self, other: &Self) -> Self {
        let mut wide = vec![0_u64; self.0.len() + other.0.len()];
        for (left_index, &left) in self.0.iter().enumerate() {
            let mut carry = 0;
            for (right_index, &right) in other.0.iter().enumerate() {
                let slot = &mut wide[left_index + right_index];
                let total = *slot + u64::from(left) * u64::from(right) + carry;
                *slot = total % BASE;
                carry = total / BASE;
            }
            wide[left_index + other.0.len()] += carry;
        }
        let mut limbs: Vec<u32> = wide
            .into_iter()
            .map(|limb| u32::try_from(limb).expect("limb"))
            .collect();
        trim(&mut limbs);
        Self(limbs)
    }

    /// Quotient and remainder by a nonzero divisor.
    fn divide(&self, divisor: u64) -> (Self, u64) {
        let mut limbs = vec![0; self.0.len()];
        let mut remainder: u128 = 0;
        for (index, &limb) in self.0.iter().enumerate().rev() {
            let current = remainder * u128::from(BASE) + u128::from(limb);
            limbs[index] = u32::try_from(current / u128::from(divisor)).expect("limb");
            remainder = current % u128::from(divisor);
        }
        trim(&mut limbs);
        (Self(limbs), u64::try_from(remainder).expect("remainder"))
    }

    /// Quotient and remainder by 10^`power`.
    fn split(&self, power: usize) -> (Self, Self) {
        let whole = power / LIMB_DIGITS;
        let factor = 10_u64.pow(u32::try_from(power % LIMB_DIGITS).expect("small power"));
        let shifted = Self(self.0.get(whole..).unwrap_or_default().to_vec());
        let (quotient, low) = shifted.divide(factor);
        let mut rest = self.0[..whole.min(self.0.len())].to_vec();
        rest.push(u32::try_from(low).expect("limb"));
        trim(&mut rest);
        (quotient, Self(rest))
    }

    /// Whether the value is odd.
    fn odd(&self) -> bool {
        self.0.first().is_some_and(|&low| low % 2 == 1)
    }
}

impl Ord for Big {
    fn cmp(&self, other: &Self) -> Ordering {
        self.0
            .len()
            .cmp(&other.0.len())
            .then_with(|| self.0.iter().rev().cmp(other.0.iter().rev()))
    }
}

impl PartialOrd for Big {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

/// Drop leading zero limbs.
fn trim(limbs: &mut Vec<u32>) {
    while limbs.last() == Some(&0) {
        limbs.pop();
    }
}

/// An exact decimal value: (−1)^negative × coefficient × 10^exponent.
#[derive(Clone, Debug)]
pub(crate) struct Decimal {
    negative: bool,
    coefficient: Big,
    exponent: i64,
}

impl Decimal {
    /// Zero.
    pub(crate) fn zero() -> Self {
        Self {
            negative: false,
            coefficient: Big::zero(),
            exponent: 0,
        }
    }

    /// Build a value, with zero always positive: its sign never reaches a result.
    fn new(negative: bool, coefficient: Big, exponent: i64) -> Self {
        Self {
            negative: negative && !coefficient.is_zero(),
            coefficient,
            exponent,
        }
    }

    /// Round to the context precision, half to even.
    fn rounded(self) -> Self {
        let digits = self.coefficient.digit_count();
        if digits <= PRECISION {
            return self;
        }
        let drop = digits - PRECISION;
        let (high, low) = self.coefficient.split(drop);
        let half = Big::small(5).scale(drop - 1);
        let up = match low.cmp(&half) {
            Ordering::Greater => true,
            Ordering::Less => false,
            Ordering::Equal => high.odd(),
        };
        let coefficient = if up { high.add(&Big::small(1)) } else { high };
        Self::new(
            self.negative,
            coefficient,
            self.exponent + i64::try_from(drop).expect("digit count"),
        )
    }

    /// The two coefficients scaled to the smaller exponent, and that exponent.
    fn aligned(&self, other: &Self) -> (Big, Big, i64) {
        let exponent = self.exponent.min(other.exponent);
        let left = self
            .coefficient
            .scale(usize::try_from(self.exponent - exponent).expect("alignment"));
        let right = other
            .coefficient
            .scale(usize::try_from(other.exponent - exponent).expect("alignment"));
        (left, right, exponent)
    }

    /// Correctly rounded sum.
    pub(crate) fn add(&self, other: &Self) -> Self {
        let (left, right, exponent) = self.aligned(other);
        let exact = if self.negative == other.negative {
            Self::new(self.negative, left.add(&right), exponent)
        } else if left >= right {
            Self::new(self.negative, left.sub(&right), exponent)
        } else {
            Self::new(other.negative, right.sub(&left), exponent)
        };
        exact.rounded()
    }

    /// Correctly rounded difference.
    pub(crate) fn sub(&self, other: &Self) -> Self {
        self.add(&Self::new(
            !other.negative,
            other.coefficient.clone(),
            other.exponent,
        ))
    }

    /// Correctly rounded product.
    pub(crate) fn mul(&self, other: &Self) -> Self {
        Self::new(
            self.negative != other.negative,
            self.coefficient.mul(&other.coefficient),
            self.exponent + other.exponent,
        )
        .rounded()
    }

    /// Correctly rounded quotient by a positive count.
    pub(crate) fn divide(&self, count: u64) -> Self {
        // Enough extra digits that the integer quotient has more than the
        // precision; a nonzero remainder then only breaks an exact half tie.
        let extra = PRECISION + 1 + count.to_string().len();
        let (quotient, remainder) = self.coefficient.scale(extra).divide(count);
        let digits = quotient.digit_count();
        if digits <= PRECISION {
            // Only zero has a quotient this short.
            return Self::zero();
        }
        let drop = digits - PRECISION;
        let (high, low) = quotient.split(drop);
        let half = Big::small(5).scale(drop - 1);
        let up = match low.cmp(&half) {
            Ordering::Greater => true,
            Ordering::Less => false,
            Ordering::Equal => remainder != 0 || high.odd(),
        };
        let coefficient = if up { high.add(&Big::small(1)) } else { high };
        Self::new(
            self.negative,
            coefficient,
            self.exponent - i64::try_from(extra).expect("digits")
                + i64::try_from(drop).expect("digits"),
        )
        .rounded()
    }

    /// Absolute value.
    pub(crate) fn abs(&self) -> Self {
        Self::new(false, self.coefficient.clone(), self.exponent)
    }

    /// Whether the value is below zero.
    pub(crate) fn is_negative(&self) -> bool {
        self.negative
    }

    /// The correctly rounded float of a value that is not negative, as Python's
    /// `float(Decimal)`; the series only convert squares, magnitudes and energy.
    pub(crate) fn float(&self) -> f64 {
        if self.coefficient.is_zero() {
            return 0.0;
        }
        let mut text = self.coefficient.0.last().expect("nonzero").to_string();
        for limb in self.coefficient.0.iter().rev().skip(1) {
            text.push_str(&format!("{limb:09}"));
        }
        text.push_str(&format!("e{}", self.exponent));
        text.parse().expect("finite decimal text")
    }
}

impl PartialEq for Decimal {
    fn eq(&self, other: &Self) -> bool {
        self.cmp(other) == Ordering::Equal
    }
}

impl Eq for Decimal {}

impl Ord for Decimal {
    fn cmp(&self, other: &Self) -> Ordering {
        let (left, right, _) = self.aligned(other);
        match (self.negative, other.negative) {
            (false, false) => left.cmp(&right),
            (true, true) => right.cmp(&left),
            (false, true) => Ordering::Greater,
            (true, false) => Ordering::Less,
        }
    }
}

impl PartialOrd for Decimal {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

/// Whether a text is a non-finite decimal word: infinity or a quiet or signalling NaN.
fn non_finite(text: &str) -> bool {
    let word = text
        .strip_prefix(['+', '-'])
        .unwrap_or(text)
        .to_ascii_lowercase();
    let nan = word
        .strip_prefix("snan")
        .or_else(|| word.strip_prefix("nan"));
    word == "inf"
        || word == "infinity"
        || nan.is_some_and(|rest| rest.bytes().all(|byte| byte.is_ascii_digit()))
}

/// The parts of a plain decimal text: sign, whole digits, fraction digits and exponent text.
fn plain(text: &str) -> Option<(bool, &str, &str, &str)> {
    let negative = text.starts_with('-');
    let unsigned = text.strip_prefix(['+', '-']).unwrap_or(text);
    let (mantissa, exponent) = match unsigned.find(['e', 'E']) {
        Some(index) => (&unsigned[..index], &unsigned[index + 1..]),
        None => (unsigned, "0"),
    };
    let (whole, fraction) = mantissa.split_once('.').unwrap_or((mantissa, ""));
    let power = exponent.strip_prefix(['+', '-']).unwrap_or(exponent);
    let digits = |part: &str| part.bytes().all(|byte| byte.is_ascii_digit());
    let valid = digits(whole)
        && digits(fraction)
        && !(whole.is_empty() && fraction.is_empty())
        && !power.is_empty()
        && digits(power);
    valid.then_some((negative, whole, fraction, exponent))
}

/// Parse one finite decimal measurement within the supported range, as
/// Python's `run_series.measurement` does.
pub(crate) fn measurement(value: &str, field: &str) -> Result<Decimal, String> {
    if non_finite(value) {
        return Err(format!("{field} must be finite"));
    }
    let Some((negative, whole, fraction, exponent)) = plain(value) else {
        return Err(format!("{field} is not a decimal"));
    };
    let outside = || format!("{field} is outside the supported decimal range");
    let whole = whole.trim_start_matches('0');
    let all = format!("{whole}{fraction}");
    let digits = all.trim_start_matches('0').trim_end_matches('0');
    if digits.is_empty() {
        return Ok(Decimal::zero());
    }
    let power = exponent
        .trim_start_matches(['+', '-'])
        .trim_start_matches('0');
    if power.len() > EXPONENT_DIGITS {
        return Err(outside());
    }
    let magnitude: i64 = if power.is_empty() {
        0
    } else {
        power.parse().expect("six digits")
    };
    let shift = if exponent.starts_with('-') {
        -magnitude
    } else {
        magnitude
    };
    let width = |text: &str| i64::try_from(text.len()).expect("field length");
    let leading = if whole.is_empty() {
        width(fraction.trim_start_matches('0')) - width(fraction) - 1
    } else {
        width(whole) - 1
    };
    if digits.len() > PRECISION || (shift + leading).abs() > EXPONENT {
        return Err(outside());
    }
    let trailing = width(&all) - width(all.trim_end_matches('0'));
    Ok(Decimal::new(
        negative,
        Big::digits(digits),
        shift - width(fraction) + trailing,
    ))
}

/// Parse one canonical nonnegative decimal integer below 2⁶⁴, as Python's
/// `run_series.count` does.
pub(crate) fn count(value: &str, field: &str) -> Result<u64, String> {
    if value.is_empty() || !value.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(format!("{field} must be a nonnegative decimal integer"));
    }
    let digits = value.trim_start_matches('0');
    let wide: Option<u128> = if digits.len() > 20 {
        None
    } else if digits.is_empty() {
        Some(0)
    } else {
        digits.parse().ok()
    };
    wide.and_then(|number| u64::try_from(number).ok())
        .ok_or_else(|| format!("{field} must be below 2**64"))
}

#[cfg(test)]
#[path = "../tests/unit/control_decimal.rs"]
mod tests;
