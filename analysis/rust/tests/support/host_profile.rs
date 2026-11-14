// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — hang guards of the integration tests on the executing host

//! Scale a hang guard written for the reference profile by the timeout scale
//! the executing host declares, as the Python `loop_timing_witness.host_profile`
//! module scales the Python tests' guards.

use std::env::{self, VarError};

/// The environment variable in which a host declares its timeout scale.
pub const SCALE_VARIABLE: &str = "WITNESS_HOST_TIMEOUT_SCALE";

/// The characters of a plain decimal declaration.
const DECIMAL_CHARACTERS: &[u8] = b"0123456789.eE+-";

/// Return the scale a declaration names: 1 when none is declared, else a
/// positive finite plain decimal number, or the Python module's refusal.
pub fn scale_of(declared: Option<&str>) -> Result<f64, String> {
    let Some(text) = declared else {
        return Ok(1.0);
    };
    let decimal = text.bytes().all(|byte| DECIMAL_CHARACTERS.contains(&byte));
    match text.parse::<f64>() {
        Ok(scale) if decimal && scale.is_finite() && scale > 0.0 => Ok(scale),
        _ => Err(format!("{SCALE_VARIABLE} must be a positive finite number")),
    }
}

/// Return a guard of `seconds` on the reference profile, multiplied by
/// `scale` and rounded up to whole seconds.
pub fn whole_seconds(seconds: u32, scale: f64) -> f64 {
    (f64::from(seconds) * scale).ceil()
}

/// Return one hang guard for `timeout(1)` on the executing host, in whole
/// seconds: the declared scale applied to `seconds` on the reference profile.
///
/// A declaration that is not Unicode is refused, as Python refuses its
/// surrogate-escaped text.
pub fn guard(seconds: u32) -> String {
    let declared = match env::var(SCALE_VARIABLE) {
        Ok(text) => Some(text),
        Err(VarError::NotPresent) => None,
        Err(VarError::NotUnicode(_)) => Some(String::new()),
    };
    let scale = scale_of(declared.as_deref()).expect("the executing host's timeout scale");
    format!("{}s", whole_seconds(seconds, scale))
}

/// Return the `timeout(1)` options and duration that end one child after a
/// hang guard of `seconds` on the reference profile, killing it one second
/// later, both scaled for the executing host.
pub fn timeout_arguments(seconds: u32) -> [String; 3] {
    [
        "--signal=TERM".to_owned(),
        format!("--kill-after={}", guard(1)),
        guard(seconds),
    ]
}
