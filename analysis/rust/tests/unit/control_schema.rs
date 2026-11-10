// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — schema locations, crate-internal controls

//! Hold the interpreter to the locations Python reports for the shared corpus.
//!
//! `tests/test_control_schema_corpus.py` builds the corpus from Python's
//! validator and requires the committed file to equal it; these tests require
//! the same file here, so both languages report identical refusals.

use super::{Numeric, Schema, compare, float_against, has_type};
use crate::corpus::changed;
use serde_json::{Value, json};
use std::cmp::Ordering;

/// The committed run manifest schema.
const RUN: &str = include_str!("../../run-manifest.schema.json");
/// The committed measurement-domain schema.
const DOMAIN: &str = include_str!("../../measurement-domain.schema.json");
/// The shared corpus of mutated documents and Python's locations.
const CORPUS: &str = include_str!("../data/control-schema-locations.json");
/// The committed neural carrier schema.
const NEURAL: &str = include_str!("../../neural-step-run.schema.json");
/// The shared neural corpus; each change carries Python's locations and refusal.
const NEURAL_CORPUS: &str = include_str!("../data/neural-manifest-refusals.json");

#[test]
fn every_corpus_case_reports_the_python_locations() {
    let corpus: Value = serde_json::from_str(CORPUS).expect("corpus");
    let bases = &corpus["bases"];
    for (kind, text) in [("run", RUN), ("domain", DOMAIN)] {
        let schema = Schema::load(text).expect("committed schema");
        let mut count = 0;
        for group in corpus[kind].as_array().expect("groups") {
            let base = &bases[group["base"].as_str().expect("base")];
            let path = group["path"].as_array().expect("path");
            for pair in group["changes"].as_array().expect("changes") {
                let document = if pair[0].is_null() {
                    base.clone()
                } else {
                    changed(base, path, &pair[0])
                };
                let expected: Vec<String> =
                    serde_json::from_value(pair[1].clone()).expect("locations");
                assert_eq!(
                    schema.locations(&document),
                    expected,
                    "{kind} {path:?} {}",
                    pair[0]
                );
                count += 1;
            }
        }
        assert!(count > 1000, "{kind}");
    }
}

#[test]
fn every_neural_change_reports_the_python_locations() {
    let corpus: Value = serde_json::from_str(NEURAL_CORPUS).expect("corpus");
    let schema = Schema::load(NEURAL).expect("committed schema");
    let base = &corpus["base"];
    let mut count = 0;
    for group in corpus["groups"].as_array().expect("groups") {
        let path = group["path"].as_array().expect("path");
        for triple in group["changes"].as_array().expect("changes") {
            let document = if triple[0].is_null() {
                base.clone()
            } else {
                changed(base, path, &triple[0])
            };
            let expected: Vec<String> =
                serde_json::from_value(triple[1].clone()).expect("locations");
            assert_eq!(
                schema.locations(&document),
                expected,
                "{path:?} {}",
                triple[0]
            );
            count += 1;
        }
    }
    assert!(count > 1000);
}

#[test]
fn schemas_outside_the_subset_are_refused() {
    for (text, refusal) in [
        ("[", "Unsupported schema document."),
        ("1", "Unsupported schema document."),
        (
            r#"{"properties": {"a": 1}}"#,
            "Unsupported schema document.",
        ),
        (
            r#"{"maxLength": 1}"#,
            "Unsupported schema keyword maxLength.",
        ),
        (r#"{"allOf": {}}"#, "Unsupported schema keyword allOf."),
        (
            r#"{"properties": []}"#,
            "Unsupported schema keyword properties.",
        ),
        (
            r##"{"$ref": "#/$defs/absent"}"##,
            "Unsupported schema keyword $ref.",
        ),
        (
            r#"{"$ref": "elsewhere.json"}"#,
            "Unsupported schema keyword $ref.",
        ),
        (r#"{"pattern": 1}"#, "Unsupported schema keyword pattern."),
        (r#"{"pattern": "a|b"}"#, "Unsupported schema pattern a|b."),
    ] {
        assert_eq!(Schema::load(text).err().as_deref(), Some(refusal), "{text}");
    }
}

#[test]
fn boolean_schemas_and_selected_branches_report_where_they_apply() {
    let schema = Schema::load(
        r#"{"properties": {"never": false, "always": true, "kinds": {"type": ["integer", "null"]},
            "choice": {"if": {"const": 1}, "else": {"type": "string"}},
            "names": {"propertyNames": {"minLength": 2}},
            "codes": {"additionalProperties": {"maximum": 3}},
            "counted": {"minItems": 2, "uniqueItems": true}}}"#,
    )
    .expect("subset schema");
    let document = json!({
        "never": 0, "always": 0, "kinds": 1.5, "choice": 2, "names": {"a": 1},
        "codes": {"x": 4, "y": 2}, "counted": [1, 1.0]
    });
    assert_eq!(
        schema.locations(&document),
        ["(root)", "choice", "codes/x", "counted", "kinds", "names"]
    );
    let valid =
        json!({"kinds": null, "choice": 1, "names": {"ab": 1}, "codes": {}, "counted": [1, true]});
    assert!(schema.locations(&valid).is_empty());
    assert_eq!(
        schema.locations(&json!({"choice": "text", "kinds": 2.0})),
        Vec::<String>::new()
    );
}

#[test]
fn prefix_items_and_closed_tails_follow_jsonschema() {
    // The locations Python's `schema_locations` reports for these documents.
    // A closed tail reports at the array even where no item count bound applies.
    let schema = Schema::load(
        r#"{"properties": {
            "closed": {"prefixItems": [{"type": "integer"}, {"const": "b"}], "items": false},
            "open": {"prefixItems": [{"type": "integer"}], "items": {"type": "string"}},
            "tail": {"items": false}}}"#,
    )
    .expect("subset schema");
    for (document, expected) in [
        (
            json!({"closed": [1, "b", 3], "open": [1, "x", 2], "tail": [1]}),
            vec!["closed", "open/2", "tail"],
        ),
        (json!({"closed": [1], "open": [], "tail": []}), vec![]),
        (
            json!({"closed": ["a"], "open": ["a", "x"]}),
            vec!["closed/0", "open/0"],
        ),
        (
            json!({"closed": [1, "c"], "open": [1, "x", "y"]}),
            vec!["closed/1"],
        ),
        (json!({"closed": [], "open": [1.5]}), vec!["open/0"]),
        (json!({"closed": {"0": 1}, "tail": "x"}), vec![]),
    ] {
        assert_eq!(schema.locations(&document), expected, "{document}");
    }
}

#[test]
fn types_and_exact_comparisons_follow_python() {
    assert!(!has_type(&json!(1), "unknown"));
    assert!(!has_type(&json!(true), "integer"));
    assert!(has_type(&json!(2.0), "integer"));
    assert_eq!(float_against(1.0e300, 1), Ordering::Greater);
    assert_eq!(float_against(-1.0e300, 1), Ordering::Less);
    assert_eq!(float_against(2.5, 2), Ordering::Greater);
    assert_eq!(float_against(2.0, 2), Ordering::Equal);
    assert_eq!(float_against(1.5, 2), Ordering::Less);
    assert_eq!(
        compare(Numeric::Integer(3), Numeric::Float(2.5)),
        Ordering::Greater
    );
    assert_eq!(
        compare(Numeric::Float(0.5), Numeric::Float(0.25)),
        Ordering::Greater
    );
    assert_eq!(
        compare(
            Numeric::Integer(9_007_199_254_740_993),
            Numeric::Float(9_007_199_254_740_992.0)
        ),
        Ordering::Greater
    );
}

#[test]
fn rarely_used_keywords_follow_jsonschema() {
    let schema = Schema::load(
        r#"{"properties": {"never": {"allOf": [false]}, "other": {"not": {"type": "integer"}},
            "repeated": {"uniqueItems": false}, "fixed": {"const": [1, {"a": 1.0}]}}}"#,
    )
    .expect("subset schema");
    let document = json!({"never": 1, "other": 2, "repeated": [1, 1], "fixed": [1.0, {"a": 1}]});
    assert_eq!(schema.locations(&document), ["never", "other"]);
    for fixed in [
        json!([1]),
        json!([1, {"b": 1}]),
        json!([1, {"a": 2}]),
        json!([1, {"a": 1, "b": 2}]),
    ] {
        assert_eq!(schema.locations(&json!({ "fixed": fixed })), ["fixed"]);
    }
    assert_eq!(
        schema.locations(&json!({"other": "text"})),
        Vec::<String>::new()
    );
    assert!(has_type(&json!(u64::MAX), "integer"));
}
