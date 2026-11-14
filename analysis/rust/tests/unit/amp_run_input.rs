// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — AMP run configuration reading held to Python's corpus

//! Hold the run configuration reader to Python's outcome for every case of
//! the shared corpus.
//!
//! `tests/test_amp_run_input_corpus.py` reads each case with Python's
//! `read_amp_run` and requires the committed file to equal it; this test
//! reads the same bytes and requires the same run, as `dataclasses.asdict`
//! writes it, or the same refusal.

use super::{AmpRun, SIGNIFICANT_DIGITS, read_amp_run};
use serde_json::{Value, json};

/// The shared corpus of Python's outcomes.
const CORPUS: &str = include_str!("../data/amp-run-input-cases.json");

/// A case's bytes: its Latin-1 text, one character per byte.
fn latin1(text: &str) -> Vec<u8> {
    text.chars()
        .map(|character| u8::try_from(u32::from(character)).expect("a Latin-1 character"))
        .collect()
}

/// The run as `dataclasses.asdict` writes it, with the coefficients as a list.
fn written(run: &AmpRun) -> Value {
    json!({
        "cycles": run.cycles,
        "period_ticks": run.period_ticks,
        "lqr": u32::from(run.lqr),
        "overload_iterations": run.overload_iterations,
        "coefficients": run.coefficients,
    })
}

#[test]
fn run_configurations_equal_python() {
    let corpus: Value = serde_json::from_str(CORPUS).expect("corpus");
    let cases = corpus["cases"].as_array().expect("cases");
    assert_eq!(cases.len(), 116);
    for case in cases {
        let name = case["name"].as_str().expect("name");
        let content = latin1(case["content"].as_str().expect("content"));
        let outcome = match read_amp_run(&content) {
            Ok(run) => json!({"run": written(&run)}),
            Err(refusal) => json!({"refusal": refusal}),
        };
        let mut expected = case.as_object().expect("case").clone();
        expected.remove("name");
        expected.remove("content");
        assert_eq!(outcome, Value::Object(expected), "{name}");
    }
}

#[test]
fn significant_digits_hold_the_widest_bound() {
    assert_eq!(u32::MAX.to_string().len(), SIGNIFICANT_DIGITS);
    assert_eq!(
        i32::MIN.unsigned_abs().to_string().len(),
        SIGNIFICANT_DIGITS
    );
}
