// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — measurement-domain rules, crate-internal controls

//! Hold the cross-field rules to Python's findings for the shared corpus.
//!
//! `tests/test_control_domain_corpus.py` builds the corpus from Python's
//! `semantic_findings` over schema-valid changes, including integral floats,
//! and requires the committed file to equal it.

use super::semantic_findings;
use serde_json::Value;

/// The shared corpus of changed domains and Python's findings.
const CORPUS: &str = include_str!("../data/control-domain-findings.json");

#[test]
fn every_corpus_domain_has_the_python_findings() {
    let corpus: Value = serde_json::from_str(CORPUS).expect("corpus");
    let cases = corpus["cases"].as_array().expect("cases");
    assert!(cases.len() > 30);
    for case in cases {
        let expected: Vec<String> =
            serde_json::from_value(case["findings"].clone()).expect("findings");
        assert_eq!(
            semantic_findings(&case["document"]),
            expected,
            "{}",
            case["name"]
        );
    }
}
