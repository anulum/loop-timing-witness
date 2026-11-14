// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — AMP completion, raw tracking and capture agreement held to Python's corpus

//! Hold the completion receipt, the raw tracking decoder and the capture
//! agreement to Python's outcome for every case of the shared corpus.
//!
//! `tests/test_amp_completion_corpus.py` runs Python's `completion_receipt`,
//! `decode_tracking` and `validate_capture` on each case and requires the
//! committed file to equal their outcomes; these tests run the native readers
//! on the same bytes and require the same completion, rows, value or refusal.

use super::{AmpCompletion, completion_receipt, validate_capture};
use crate::amp_tracking::decode_tracking;
use crate::unit_files::hex_bytes;
use serde_json::{Value, json};

/// The shared corpus of Python's outcomes.
const CORPUS: &str = include_str!("../data/amp-completion-cases.json");
/// The repository's measurement domain, the crate's checked copy.
const DOMAIN: &str = include_str!("../data/measurement-domain.json");

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

/// The outcome a case expects: every member but its inputs.
fn expected(case: &Value, inputs: &[&str]) -> Value {
    let mut outcome = case.as_object().expect("case").clone();
    for input in inputs {
        outcome.remove(*input);
    }
    Value::Object(outcome)
}

/// The completion as `dataclasses.asdict` writes it.
fn written(completion: &AmpCompletion) -> Value {
    json!({
        "samples": completion.samples,
        "events": completion.events,
        "misses": completion.misses,
        "overflow": completion.overflow,
        "safe": completion.safe,
        "thermal": completion.thermal,
    })
}

#[test]
fn completion_receipts_equal_python() {
    let cases = section("receipts");
    assert_eq!(cases.len(), 27);
    for case in &cases {
        let log = latin1(case["log"].as_str().expect("log"));
        let outcome = match completion_receipt(&log) {
            Ok(completion) => json!({"completion": written(&completion)}),
            Err(refusal) => json!({"refusal": refusal}),
        };
        assert_eq!(
            outcome,
            expected(case, &["name", "log"]),
            "{}",
            case["name"]
        );
    }
}

#[test]
fn raw_tracking_equals_python() {
    let cases = section("tracking");
    assert_eq!(cases.len(), 69);
    for case in &cases {
        let content = latin1(case["content"].as_str().expect("content"));
        let outcome = match decode_tracking(&content, 10, 10) {
            Ok(rows) => json!({
                "rows": rows
                    .iter()
                    .map(|row| json!([row.cycle, row.reference, row.output]))
                    .collect::<Vec<_>>()
            }),
            Err(refusal) => json!({"refusal": refusal}),
        };
        assert_eq!(
            outcome,
            expected(case, &["name", "content"]),
            "{}",
            case["name"]
        );
    }
}

#[test]
fn captures_equal_python() {
    let cases = section("captures");
    assert_eq!(cases.len(), 17);
    let base = completion_receipt(&latin1(
        section("receipts")[0]["log"].as_str().expect("logger line"),
    ))
    .expect("the ISA completion");
    for case in &cases {
        let mut completion = base;
        for (name, value) in case["completion"].as_object().expect("changes") {
            let value = value.as_u64().expect("a counter");
            match name.as_str() {
                "samples" => completion.samples = value,
                "events" => completion.events = value,
                "overflow" => completion.overflow = u32::try_from(value).expect("32 bits"),
                other => panic!("unexpected counter {other}"),
            }
        }
        let domain = case["domain"]
            .as_str()
            .map_or_else(|| DOMAIN.as_bytes().to_vec(), latin1);
        let outcome = match validate_capture(
            &completion,
            &hex_bytes(case["events"].as_str().expect("events")),
            &latin1(case["tracking"].as_str().expect("tracking")),
            &domain,
            10,
        ) {
            Ok(()) => json!({"value": true}),
            Err(refusal) => json!({"refusal": refusal}),
        };
        let inputs = ["name", "completion", "events", "tracking", "domain"];
        assert_eq!(outcome, expected(case, &inputs), "{}", case["name"]);
    }
}
