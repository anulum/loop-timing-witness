// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — AMP snapshot checks held to Python's corpus

//! Hold the runtime and firmware dependency snapshot checks to Python's
//! outcome for every case of the shared corpus.
//!
//! `tests/test_amp_snapshot_corpus.py` builds each case tree with Python's own
//! snapshot writers, runs Python's checks and requires the committed file to
//! equal it; these tests write the same trees and require the same values,
//! refusals and read errors here.

use crate::amp_failure::AmpFailure;
use crate::amp_image_dependencies::{
    image_dependency_record_count, validate_image_dependency_snapshot,
};
use crate::amp_runtime_snapshot::validate_runtime_snapshot;
use crate::unit_files::{Scratch, hex_bytes};
use serde_json::{Map, Value, json};
use std::path::Path;

/// The shared corpus of Python's outcomes.
const CORPUS: &str = include_str!("../data/amp-snapshot-cases.json");

/// A corpus value with `{root}` replaced by the case directory in every
/// string and member name.
fn rooted(value: &Value, root: &str) -> Value {
    match value {
        Value::String(text) => Value::String(text.replace("{root}", root)),
        Value::Array(items) => Value::Array(items.iter().map(|item| rooted(item, root)).collect()),
        Value::Object(members) => Value::Object(
            members
                .iter()
                .map(|(name, item)| (name.replace("{root}", root), rooted(item, root)))
                .collect(),
        ),
        other => other.clone(),
    }
}

/// Write one case tree: text files, bytes, symbolic links and empty folders.
fn materialise(directory: &Path, tree: &Map<String, Value>) {
    let root = directory.to_str().expect("UTF-8 case directory");
    for (name, entry) in tree {
        let path = directory.join(name);
        std::fs::create_dir_all(path.parent().expect("parent")).expect("tree folder");
        if let Some(text) = entry.as_str() {
            std::fs::write(&path, text.replace("{root}", root)).expect("text file");
        } else if let Some(target) = entry["symlink"].as_str() {
            std::os::unix::fs::symlink(target.replace("{root}", root), &path).expect("link");
        } else if let Some(hex) = entry["hex"].as_str() {
            std::fs::write(&path, hex_bytes(hex)).expect("byte file");
        } else {
            std::fs::create_dir(&path).expect("empty folder");
        }
    }
}

/// One check's outcome as the corpus writes it, the case directory written `<root>`.
fn outcome(directory: &Path, function: &str, argument: &Value) -> Value {
    let root = directory.to_str().expect("UTF-8 case directory");
    let result = match function {
        "runtime" => {
            validate_runtime_snapshot(&directory.join("capture"), argument).map(|()| Value::Null)
        }
        "image" => validate_image_dependency_snapshot(&directory.join("image"), argument)
            .map(|()| Value::Null),
        _ => image_dependency_record_count(argument.as_object().expect("receipt"))
            .map(|count| json!(count)),
    };
    match result {
        Ok(value) => json!({"value": value}),
        Err(AmpFailure::Refused(text)) => json!({"refusal": text.replace(root, "<root>")}),
        Err(AmpFailure::Os(text)) => json!({"os_error": text.replace(root, "<root>")}),
    }
}

#[test]
fn snapshot_checks_equal_python() {
    let corpus: Value = serde_json::from_str(CORPUS).expect("corpus");
    let scratch = Scratch::new("amp-snapshots");
    for (index, case) in corpus["cases"]
        .as_array()
        .expect("cases")
        .iter()
        .enumerate()
    {
        let function = case["function"].as_str().expect("function");
        let directory = scratch.0.join(format!("{function}-{index}"));
        std::fs::create_dir(&directory).expect("case directory");
        materialise(&directory, case["tree"].as_object().expect("tree"));
        let root = directory.to_str().expect("UTF-8 case directory");
        let argument = rooted(&case["argument"], root);
        let expected: Map<String, Value> = case
            .as_object()
            .expect("case")
            .iter()
            .filter(|(key, _)| matches!(key.as_str(), "value" | "refusal" | "os_error"))
            .map(|(key, value)| (key.clone(), value.clone()))
            .collect();
        let name = &case["name"];
        assert_eq!(
            outcome(&directory, function, &argument),
            Value::Object(expected),
            "{name}"
        );
    }
}
