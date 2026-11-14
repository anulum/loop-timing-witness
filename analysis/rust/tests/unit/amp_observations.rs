// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — AMP tracking CSV and fault schedule held to Python's corpus

//! Hold the Q8.24 decimal text, the tracking CSV and the fault schedule to
//! Python's outcome for every case of the shared corpus.
//!
//! `tests/test_amp_observations_corpus.py` runs Python's
//! `str(Decimal(raw) / 2**24)`, `tracking_csv` and `fault_schedule` on each
//! case and requires the committed file to equal their outcomes; these tests
//! require the same text, CSV bytes, schedule or refusal.

use super::{fault_schedule, q24_text, tracking_csv};
use serde_json::{Value, json};

/// The shared corpus of Python's outcomes.
const CORPUS: &str = include_str!("../data/amp-observations-cases.json");

/// A case's bytes: its Latin-1 text, one character per byte.
fn latin1(text: &str) -> Vec<u8> {
    text.chars()
        .map(|character| u8::try_from(u32::from(character)).expect("a Latin-1 character"))
        .collect()
}

/// The corpus cases of one section.
fn section(name: &str) -> Vec<Value> {
    let corpus: Value = serde_json::from_str(CORPUS).expect("corpus");
    corpus[name].as_array().expect("cases").clone()
}

/// The outcome a case expects: its value or refusal.
fn expected(case: &Value) -> Value {
    case.get("value").map_or_else(
        || json!({"refusal": case["refusal"]}),
        |value| json!({"value": value}),
    )
}

#[test]
fn q24_texts_equal_python() {
    let decimals = section("decimals");
    assert_eq!(decimals.len(), 1103);
    for pair in &decimals {
        let raw = i32::try_from(pair[0].as_i64().expect("raw")).expect("32 bits");
        assert_eq!(q24_text(raw), pair[1].as_str().expect("text"), "{raw}");
    }
}

#[test]
fn tracking_tables_equal_python() {
    let cases = section("tables");
    assert_eq!(cases.len(), 6);
    for case in &cases {
        let content = latin1(case["content"].as_str().expect("content"));
        let cycles = u32::try_from(case["cycles"].as_u64().expect("cycles")).expect("32 bits");
        let samples = case["samples"].as_u64().expect("samples");
        let outcome = match tracking_csv(&content, cycles, samples) {
            Ok(csv) => json!({"value": String::from_utf8(csv).expect("ASCII CSV")}),
            Err(refusal) => json!({"refusal": refusal}),
        };
        assert_eq!(outcome, expected(case), "{}", case["name"]);
    }
}

#[test]
fn fault_schedules_equal_python() {
    let cases = section("schedules");
    assert_eq!(cases.len(), 120);
    for case in &cases {
        let content = latin1(case["content"].as_str().expect("content"));
        let outcome = match fault_schedule(&content) {
            Ok(schedule) => json!({"value": schedule}),
            Err(refusal) => json!({"refusal": refusal}),
        };
        assert_eq!(outcome, expected(case), "{}", case["name"]);
    }
}
