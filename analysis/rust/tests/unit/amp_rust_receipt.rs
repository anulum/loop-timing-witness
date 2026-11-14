// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — Rust kernel image checks held to Python's corpus

//! Hold the Rust kernel image check to Python's outcome for every case of the
//! shared corpus.
//!
//! `tests/test_amp_rust_receipt_corpus.py` builds the corpus from Python's
//! check and requires the committed file to equal it; this test writes the
//! same image trees and receipts and requires the same values, refusals and
//! read errors here.

use super::validate_rust_image_receipt;
use crate::amp_failure::AmpFailure;
use crate::unit_files::{Scratch, edited_tree, patched};
use serde_json::{Map, Value, json};

/// The shared corpus of Python's outcomes.
const CORPUS: &str = include_str!("../data/amp-rust-receipt-cases.json");

#[test]
fn rust_image_receipts_equal_python() {
    let corpus: Value = serde_json::from_str(CORPUS).expect("corpus");
    let tree = corpus["tree"].as_object().expect("tree");
    let scratch = Scratch::new("amp-rust-receipt");
    for (index, case) in corpus["cases"]
        .as_array()
        .expect("cases")
        .iter()
        .enumerate()
    {
        let directory = scratch.0.join(format!("case-{index}"));
        std::fs::create_dir(&directory).expect("case directory");
        edited_tree(&directory, tree, &case["edits"]);
        let receipts = patched(&corpus["receipts"], &case["patch"]);
        let object = |name: &str| receipts[name].as_object().expect("receipt").clone();
        let result = validate_rust_image_receipt(
            &directory.join("image"),
            &object("image"),
            &object("preparation"),
        );
        let root = directory.to_str().expect("UTF-8 case directory");
        let found = match result {
            Ok(()) => json!({"value": true}),
            Err(AmpFailure::Refused(text)) => json!({"refusal": text.replace(root, "<root>")}),
            Err(AmpFailure::Os(text)) => json!({"os_error": text.replace(root, "<root>")}),
        };
        let expected: Map<String, Value> = case
            .as_object()
            .expect("case")
            .iter()
            .filter(|(key, _)| matches!(key.as_str(), "value" | "refusal" | "os_error"))
            .map(|(key, value)| (key.clone(), value.clone()))
            .collect();
        assert_eq!(found, Value::Object(expected), "{}", case["name"]);
    }
}
