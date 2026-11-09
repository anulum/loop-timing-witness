// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — bounded JSON objects, crate-internal controls

//! Hold the decoder to Python's outcome for every document of the shared corpus.
//!
//! `tests/test_control_json_corpus.py` builds the corpus from Python's bounded
//! and dispatch decoders and requires the committed file to equal it; these
//! tests require the same decoded objects, analysis choices and refusals here.

use super::{MAX_DEPTH, decode_dispatch_object, decode_object, nesting_depth};
use serde_json::Value;

/// The shared corpus of raw documents and Python's outcomes.
const CORPUS: &str = include_str!("../data/control-json-cases.json");

/// Decode a hexadecimal byte string of the corpus.
fn bytes(hex: &str) -> Vec<u8> {
    (0..hex.len())
        .step_by(2)
        .map(|index| u8::from_str_radix(&hex[index..index + 2], 16).expect("hex"))
        .collect()
}

#[test]
fn every_corpus_document_decodes_or_refuses_as_python() {
    let corpus: Value = serde_json::from_str(CORPUS).expect("corpus");
    assert_eq!(
        corpus["schema"],
        "loop-timing-witness.control-json-cases.v2"
    );
    let source = corpus["source"].as_str().expect("source");
    let cases = corpus["cases"].as_array().expect("cases");
    assert!(cases.len() > 60);
    for case in cases {
        let raw = bytes(case["raw_hex"].as_str().expect("raw"));
        let dispatch = match decode_dispatch_object(&raw, source) {
            Ok(object) => serde_json::json!({"neural": object.contains_key("schema_id")}),
            Err(refusal) => serde_json::json!({"refusal": refusal}),
        };
        assert_eq!(
            dispatch,
            case["dispatch"],
            "{}",
            String::from_utf8_lossy(&raw)
        );
        let outcome = decode_object(&raw, source).map(|(object, _)| Value::Object(object));
        match case.get("refusal") {
            Some(refusal) => assert_eq!(
                outcome.err().as_deref(),
                refusal.as_str(),
                "{}",
                String::from_utf8_lossy(&raw)
            ),
            None => assert_eq!(
                outcome.ok().as_ref(),
                Some(&case["value"]),
                "{}",
                String::from_utf8_lossy(&raw)
            ),
        }
    }
}

#[test]
fn nesting_depth_counts_only_structural_brackets() {
    assert_eq!(nesting_depth(r#"[{"a": "[[{{"}]"#), 2);
    assert_eq!(nesting_depth(r#"["\"[[", "\\", [1]]"#), 2);
    assert_eq!(nesting_depth("]]]["), 0);
    assert_eq!(nesting_depth(""), 0);
    assert_eq!(MAX_DEPTH, 64);
}

#[test]
fn incomplete_escapes_and_pairs_are_invalid() {
    for text in [
        r#"{"a": "\"#,
        r#"{"a": "\u12"#,
        r#"{"a": "\ud800\uZZZZ"}"#,
        r#"{"a": "\ud800\u12"#,
        "{\"a\": \"tab\there\"}",
        r#"{"a": "\ud800\udc00"#,
        "{\"a\"",
        "{\"a\":",
        "[1",
        "-",
        "{\"a\": 1",
    ] {
        assert_eq!(
            decode_object(text.as_bytes(), "case").err().as_deref(),
            Some("case: invalid JSON"),
            "{text}"
        );
    }
    let paired = decode_object(
        r#"{"a": "\ud800\u0041", "b": "\udbff\udfff"}"#.as_bytes(),
        "case",
    );
    assert_eq!(
        paired.err().as_deref(),
        Some("case: JSON text holds an unpaired surrogate escape")
    );
    let (joined, _) = decode_object(r#"{"b": "\udbff\udfff"}"#.as_bytes(), "case").expect("pair");
    assert_eq!(joined["b"], Value::String("\u{10ffff}".to_owned()));
}

#[test]
fn member_order_is_kept_for_every_object() {
    let (_, orders) = decode_object(
        br#"{"z": 1, "a": {"y": [{"q": 1, "p": 2}], "b": 2}}"#,
        "case",
    )
    .expect("object");
    assert_eq!(orders[&Vec::<String>::new()], ["z", "a"]);
    assert_eq!(orders[&vec!["a".to_owned()]], ["y", "b"]);
    assert_eq!(
        orders[&vec!["a".to_owned(), "y".to_owned(), "0".to_owned()]],
        ["q", "p"]
    );
}
