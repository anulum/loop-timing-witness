// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — Rust dependency record reader held to Python's corpus

//! Hold the shell lexer and the Rust dependency record reader to Python's
//! outcome for every text and case of the shared corpus.
//!
//! `tests/test_amp_rust_dependency_corpus.py` builds the corpus from CPython's
//! `shlex.split` and Python's reader and requires the committed file to equal
//! it; these tests rebuild the same texts and case trees and require the same
//! words, digests, refusals and read errors here.

use super::{AmpFailure, rust_dependency_hashes};
use crate::amp_shell_words::{NO_CLOSING_QUOTATION, NO_ESCAPED_CHARACTER, split};
use crate::unit_files::{Scratch, hex_bytes};
use serde_json::{Map, Value, json};
use std::path::{Path, PathBuf};

/// The shared corpus of Python's outcomes.
const CORPUS: &str = include_str!("../data/amp-rust-dependency-cases.json");

/// The decoded corpus.
fn corpus() -> Value {
    serde_json::from_str(CORPUS).expect("corpus")
}

/// A corpus array of strings.
fn strings(value: &Value) -> Vec<String> {
    let items = value.as_array().expect("array");
    items
        .iter()
        .map(|item| item.as_str().expect("string").to_owned())
        .collect()
}

/// Every text of one length over an alphabet, in `itertools.product` order.
fn texts(alphabet: &[String], length: u32) -> Vec<String> {
    let base = alphabet.len();
    (0..base.pow(length))
        .map(|mut index| {
            let mut picks = vec![""; usize::try_from(length).expect("length")];
            for pick in picks.iter_mut().rev() {
                *pick = &alphabet[index % base];
                index /= base;
            }
            picks.concat()
        })
        .collect()
}

#[test]
fn shell_words_equal_python() {
    let corpus = corpus();
    let shlex = &corpus["shlex"];
    let errors = strings(&shlex["errors"]);
    assert_eq!(errors, [NO_CLOSING_QUOTATION, NO_ESCAPED_CHARACTER]);
    let (alphabet, core) = (strings(&shlex["alphabet"]), strings(&shlex["core"]));
    let mut all = Vec::new();
    for length in 0..4 {
        all.extend(texts(&alphabet, length));
    }
    for length in 4..6 {
        all.extend(texts(&core, length));
    }
    let outcomes = shlex["outcomes"].as_array().expect("outcomes");
    assert_eq!(all.len(), outcomes.len());
    for (text, outcome) in all.iter().zip(outcomes) {
        let found = match split(text) {
            Ok(words) => json!(words),
            Err(error) => json!(errors.iter().position(|known| known == error)),
        };
        assert_eq!(&found, outcome, "{text:?}");
    }
}

/// Write one case's tree and records under its directory and return the record paths.
fn materialise(directory: &Path, case: &Value) -> Vec<PathBuf> {
    for (name, content) in case["tree"].as_object().expect("tree") {
        let path = directory.join(name);
        std::fs::create_dir_all(path.parent().expect("parent")).expect("tree directory");
        match content.as_str() {
            Some(text) => std::fs::write(&path, text).expect("tree file"),
            None => {
                let target = content["symlink"].as_str().expect("link target");
                std::os::unix::fs::symlink(target, &path).expect("tree link");
            }
        }
    }
    let records = directory.join("records");
    std::fs::create_dir(&records).expect("records");
    let items = case["records"].as_array().expect("records");
    let mut paths = Vec::new();
    for (index, record) in items.iter().enumerate() {
        let path = records.join(format!("{index}.d"));
        if let Some(text) = record["text"].as_str() {
            std::fs::write(&path, text).expect("text record");
        } else if let Some(hex) = record["hex"].as_str() {
            std::fs::write(&path, hex_bytes(hex)).expect("byte record");
        }
        paths.push(path);
    }
    paths
}

/// The reader's outcome as the corpus writes it, the case directory written `<root>`.
fn outcome(directory: &Path, records: &[PathBuf]) -> Value {
    let root = directory.to_str().expect("UTF-8 case directory");
    match rust_dependency_hashes(records, directory) {
        Ok(hashes) => json!({"hashes": hashes}),
        Err(AmpFailure::Refused(text)) => json!({"refusal": text.replace(root, "<root>")}),
        Err(AmpFailure::Os(text)) => json!({"os_error": text.replace(root, "<root>")}),
    }
}

#[test]
fn reader_equals_python() {
    let corpus = corpus();
    let scratch = Scratch::new("amp-rust-dependencies");
    let cases = corpus["cases"].as_array().expect("cases");
    for (index, case) in cases.iter().enumerate() {
        let directory = scratch.0.join(format!("case-{index}"));
        std::fs::create_dir(&directory).expect("case directory");
        let records = materialise(&directory, case);
        let expected: Map<String, Value> = case
            .as_object()
            .expect("case")
            .iter()
            .filter(|(key, _)| matches!(key.as_str(), "hashes" | "refusal" | "os_error"))
            .map(|(key, value)| (key.clone(), value.clone()))
            .collect();
        let name = &case["name"];
        assert_eq!(
            outcome(&directory, &records),
            Value::Object(expected),
            "{name}"
        );
    }
}
