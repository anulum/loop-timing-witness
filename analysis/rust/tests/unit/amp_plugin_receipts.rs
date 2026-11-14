// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — plugin receipt decoding and snapshot checks held to Python's corpus

//! Hold the plugin build receipt decoder and the plugin snapshot check to
//! Python's outcome for every case of the shared corpus.
//!
//! `tests/test_amp_plugin_receipt_corpus.py` builds the corpus from Python's
//! decoder and check and requires the committed file to equal it; these tests
//! rebuild the same receipt bytes and capture trees and require the same
//! values, refusals and read errors here.

use super::validate_plugin_snapshot;
use crate::amp_failure::AmpFailure;
use crate::amp_plugin_receipt::decode_plugin_receipt;
use crate::control_json_text::canonical_json;
use crate::unit_files::{Scratch, materialise, write_entry};
use serde_json::{Map, Value, json};
use std::path::Path;

/// The shared corpus of Python's outcomes.
const CORPUS: &str = include_str!("../data/amp-plugin-receipt-cases.json");

/// Apply a corpus patch to the base receipt: member paths set or removed.
fn patched(base: &Value, patch: &Value) -> Value {
    let mut document = base.clone();
    for operation in patch.as_array().expect("patch") {
        let path = operation["path"].as_array().expect("path");
        let (last, parents) = path.split_last().expect("a member path");
        let mut node = &mut document;
        for part in parents {
            node = &mut node[part.as_str().expect("member")];
        }
        let members = node.as_object_mut().expect("object");
        let name = last.as_str().expect("member");
        if operation.get("remove").is_some() {
            members.remove(name);
        } else {
            members.insert(name.to_owned(), operation["set"].clone());
        }
    }
    document
}

/// The receipt bytes of one decoding case.
fn receipt(base: &Value, case: &Value) -> Vec<u8> {
    case["text"].as_str().map_or_else(
        || canonical_json(&patched(base, &case["patch"])),
        |text| text.as_bytes().to_vec(),
    )
}

/// One call's outcome as the corpus writes it, the case directory written `<root>`.
fn outcome(directory: &Path, result: Result<(), AmpFailure>) -> Value {
    let root = directory.to_str().expect("UTF-8 case directory");
    match result {
        Ok(()) => json!({"value": true}),
        Err(AmpFailure::Refused(text)) => json!({"refusal": text.replace(root, "<root>")}),
        Err(AmpFailure::Os(text)) => json!({"os_error": text.replace(root, "<root>")}),
    }
}

/// Write the complete capture and a snapshot case's edits under a case folder.
fn capture(directory: &Path, template: &Map<String, Value>, edits: &Value) {
    materialise(directory, template);
    for name in edits["remove"].as_array().expect("removed entries") {
        let path = directory.join(name.as_str().expect("entry"));
        if path.is_dir() && !path.is_symlink() {
            std::fs::remove_dir(&path).expect("removed folder");
        } else {
            std::fs::remove_file(&path).expect("removed entry");
        }
    }
    for (name, entry) in edits["write"].as_object().expect("written entries") {
        write_entry(directory, name, entry);
    }
}

#[test]
fn plugin_receipts_and_snapshots_equal_python() {
    let corpus: Value = serde_json::from_str(CORPUS).expect("corpus");
    let template = corpus["capture"].as_object().expect("capture");
    let scratch = Scratch::new("amp-plugin-receipts");
    for (index, case) in corpus["cases"]
        .as_array()
        .expect("cases")
        .iter()
        .enumerate()
    {
        let directory = scratch.0.join(format!("case-{index}"));
        std::fs::create_dir(&directory).expect("case directory");
        let result = if case["function"] == "decode" {
            let content = receipt(&corpus["base"], case);
            decode_plugin_receipt(&content).map(|data| {
                let parsed: Value = serde_json::from_slice(&content).expect("admitted JSON");
                assert_eq!(Value::Object(data), parsed, "{}", case["name"]);
            })
        } else {
            capture(&directory, template, &case["edits"]);
            let argument = &case["argument"];
            let plugin = argument["plugin"].as_str().expect("library digest");
            let thermal = argument["thermal"].as_bool().expect("plant");
            validate_plugin_snapshot(&directory.join("capture"), plugin, thermal)
        };
        let expected: Map<String, Value> = case
            .as_object()
            .expect("case")
            .iter()
            .filter(|(key, _)| matches!(key.as_str(), "value" | "refusal" | "os_error"))
            .map(|(key, value)| (key.clone(), value.clone()))
            .collect();
        let name = &case["name"];
        assert_eq!(
            outcome(&directory, result),
            Value::Object(expected),
            "{name}"
        );
    }
}
