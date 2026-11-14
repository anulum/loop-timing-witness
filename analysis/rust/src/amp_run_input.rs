// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — complete native run configuration of an AMP image

//! Read an AMP image's run configuration as the Python modules
//! `amp_run_input` and `amp_contract` do.
//!
//! [`read_amp_run`] splits the configuration where the native stream reader
//! does, admits every field's whole decimal syntax and bound, a fault
//! schedule inside the run without modeled latency, and the run's integer
//! contract and controller invariants. Every refusal is Python's text for the
//! same first defect.
//!
//! [`read_amp_run`]: crate::amp_run_input::read_amp_run

/// Fields of a complete configuration.
const TOKEN_COUNT: usize = 24;
/// Digits of the widest bound, `u32::MAX` and the magnitude of `i32::MIN`; a
/// longer magnitude exceeds every bound.
const SIGNIFICANT_DIGITS: usize = 10;
/// Largest reference mode.
const MAX_REFERENCE_MODE: i64 = 2;
/// Largest reference phase.
const MAX_PHASE: i64 = 15;
/// Largest actual overload workload.
const MAX_OVERLOAD_ITERATIONS: u32 = 10_000_000;
/// Largest run duration in 10 ns ticks that the nanosecond run timer holds.
const MAX_DURATION_TICKS: u64 = (u64::MAX - 1_000_000_000) / 10;
/// One in Q8.24.
const SCALE: i32 = 1 << 24;

/// Python's `AmpRun`: the controller inputs compiled into one firmware image.
///
/// The native fields hold Python's bounds by type, and the controller is a
/// flag, so Python's checks that the scalars are `int` within 32 bits and
/// that the selector is zero or one always hold here.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct AmpRun {
    /// Complete run cycle count.
    pub cycles: u32,
    /// Fabric period in 10 ns ticks.
    pub period_ticks: u32,
    /// The LQR controller, rather than PID.
    pub lqr: bool,
    /// Actual target instruction workload of an overload fault.
    pub overload_iterations: u32,
    /// Raw signed Q8.24 coefficients in `witness_coefficients` order.
    pub coefficients: [i32; 11],
}

impl AmpRun {
    /// Python's `AmpRun.__post_init__`: the run's integer contract, then the
    /// controller invariants.
    fn admitted(self) -> Result<Self, String> {
        let ticks = u64::from(self.cycles) * u64::from(self.period_ticks);
        if self.cycles == 0
            || self.period_ticks == 0
            || self.overload_iterations > MAX_OVERLOAD_ITERATIONS
            || ticks > MAX_DURATION_TICKS
        {
            return Err("AMP run inputs violate the native integer contract".into());
        }
        let [
            kp,
            ki,
            decay,
            derivative,
            _,
            _,
            _,
            lower,
            upper,
            integral_lower,
            integral_upper,
        ] = self.coefficients;
        if lower > 0
            || upper < 0
            || integral_lower > 0
            || integral_upper < 0
            || kp < 0
            || ki < 0
            || derivative < 0
            || !(0..=SCALE).contains(&decay)
        {
            return Err("AMP run coefficients violate the native controller invariants".into());
        }
        Ok(self)
    }
}

/// Python's `native_words`: the ASCII fields between runs of the C locale's
/// whitespace, which the native stream reader skips.
fn native_words(content: &[u8]) -> Result<Vec<&str>, String> {
    if !content.is_ascii() {
        return Err("AMP native configuration must be ASCII".into());
    }
    Ok(content
        .split(|byte| matches!(byte, b' ' | b'\t' | b'\n' | b'\r' | b'\x0b' | b'\x0c'))
        .filter(|word| !word.is_empty())
        .map(|word| std::str::from_utf8(word).expect("ASCII field"))
        .collect())
}

/// Python's `native_integer`: whole decimal syntax with any count of leading
/// zeros, then the inclusive bounds.
fn native_integer(token: &str, minimum: i64, maximum: i64) -> Result<i64, String> {
    let unsigned = token.strip_prefix(['+', '-']).unwrap_or(token);
    if unsigned.is_empty() || !unsigned.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err("AMP native configuration integer syntax is invalid".into());
    }
    let digits = unsigned.trim_start_matches('0');
    if digits.len() <= SIGNIFICANT_DIGITS {
        let magnitude = digits
            .bytes()
            .fold(0, |value, digit| value * 10 + i64::from(digit - b'0'));
        let value = if token.starts_with('-') {
            -magnitude
        } else {
            magnitude
        };
        if (minimum..=maximum).contains(&value) {
            return Ok(value);
        }
    }
    Err("AMP native configuration integer is outside bounds".into())
}

/// A field within the unsigned 32-bit range.
fn unsigned(token: &str) -> Result<u32, String> {
    native_integer(token, 0, i64::from(u32::MAX))
        .map(|value| u32::try_from(value).expect("an admitted unsigned field"))
}

/// A field within the signed 32-bit range.
fn signed(token: &str) -> Result<i32, String> {
    native_integer(token, i64::from(i32::MIN), i64::from(i32::MAX))
        .map(|value| i32::try_from(value).expect("an admitted signed field"))
}

/// Read one complete native run configuration.
///
/// # Errors
///
/// Python's refusal text for the first defect: a byte outside ASCII, a field
/// count or controller other than the native one, a field's syntax or bound
/// in field order, an unknown fault kind, a fault schedule outside the run or
/// a modeled latency, the run's integer contract, then its controller
/// invariants.
pub fn read_amp_run(content: &[u8]) -> Result<AmpRun, String> {
    let tokens = native_words(content)?;
    if tokens.len() != TOKEN_COUNT || !matches!(tokens[0], "pid" | "lqr") {
        return Err("AMP requires the complete original native run configuration".into());
    }
    let cycles = unsigned(tokens[1])?;
    let period_ticks = unsigned(tokens[2])?;
    let mut coefficients = [0; 11];
    for (coefficient, token) in coefficients.iter_mut().zip(&tokens[3..14]) {
        *coefficient = signed(token)?;
    }
    native_integer(tokens[14], 0, MAX_REFERENCE_MODE)?;
    for token in &tokens[15..18] {
        signed(token)?;
    }
    native_integer(tokens[18], 0, MAX_PHASE)?;
    let fault = tokens[19];
    if !matches!(fault, "none" | "drop" | "delay" | "freeze" | "overload") {
        return Err("AMP native fault kind is invalid".into());
    }
    let mut schedule = [0; 4];
    for (field, token) in schedule.iter_mut().zip(&tokens[20..24]) {
        *field = unsigned(token)?;
    }
    let [fault_cycle, fault_periods, overload, modeled_ns] = schedule;
    if (fault == "none" && (fault_cycle != 0 || fault_periods != 0))
        || (fault != "none" && (fault_cycle >= cycles || fault_periods == 0))
        || (fault != "overload" && overload != 0)
        || modeled_ns != 0
    {
        return Err("AMP native fault schedule or modeled latency is invalid".into());
    }
    AmpRun {
        cycles,
        period_ticks,
        lqr: tokens[0] == "lqr",
        overload_iterations: overload,
        coefficients,
    }
    .admitted()
}

#[cfg(test)]
#[path = "../tests/unit/amp_run_input.rs"]
mod tests;
