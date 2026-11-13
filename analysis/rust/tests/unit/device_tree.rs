// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — device-tree readers held to Python's corpus

//! Hold the device-tree readers to Python's outcome for every blob of the shared corpus.
//!
//! `tests/test_device_tree_corpus.py` builds the corpus from real `dtc` output
//! and Python's readers and requires the committed file to equal it; these
//! tests require the same trees, reader values and refusals here.

use super::{
    DeviceTree, PlicBinding, PlicSelection, bind_plic, decode_device_tree, phandle_nodes,
    register_regions, single_cell, string_list,
};
use crate::files::{digest, hex};
use crate::unit_files::hex_bytes;
use serde_json::{Map, Value, json};
use std::collections::{BTreeMap, HashMap};

/// The shared corpus of blobs and Python's outcomes.
const CORPUS: &str = include_str!("../data/device-tree-cases.json");
/// Single-cell properties read on every node that declares them.
const CELLS: [&str; 7] = [
    "#address-cells",
    "#size-cells",
    "#interrupt-cells",
    "phandle",
    "linux,phandle",
    "interrupt-parent",
    "riscv,ndev",
];
/// Harts and sources asked of every PLIC node, in and around the admitted bounds.
const PLIC_HARTS: [i128; 6] = [-1, 0, 1, 2, 4, 5];
const PLIC_SOURCES: [i128; 8] = [-1, 0, 1, 2, 31, 32, 1023, 1024];
/// Paths the corpus asks of every tree without the tree holding them.
const ABSENT_PLIC: &str = "/soc/plic@absent";
const ABSENT_NODE: &str = "/absent";
/// The one value above 64 bits a reader can return: the end of the RV64 space.
const ADDRESS_END: u128 = 1 << 64;

/// A corpus integer as a size or offset.
fn index(value: &Value) -> usize {
    usize::try_from(value.as_u64().expect("integer")).expect("index")
}

/// The committed corpus with its chunks decoded.
struct Corpus {
    document: Value,
    texts: Vec<String>,
    chunks: BTreeMap<String, Vec<u8>>,
}

impl Corpus {
    /// Parse the committed corpus.
    fn load() -> Self {
        let document: Value = serde_json::from_str(CORPUS).expect("corpus");
        assert_eq!(
            document["schema"],
            "loop-timing-witness.device-tree-cases.v1"
        );
        let texts = document["texts"]
            .as_array()
            .expect("texts")
            .iter()
            .map(|text| text.as_str().expect("text").to_owned())
            .collect();
        let chunks = document["chunks"]
            .as_object()
            .expect("chunks")
            .iter()
            .map(|(name, text)| (name.clone(), hex_bytes(text.as_str().expect("chunk"))))
            .collect();
        Self {
            document,
            texts,
            chunks,
        }
    }

    /// Build one case's blob from a chunk, a cut chunk or segments.
    fn blob(&self, spec: &Value) -> Vec<u8> {
        if let Some(segments) = spec.get("segments") {
            return segments
                .as_array()
                .expect("segments")
                .iter()
                .flat_map(|segment| {
                    let part = match &segment[0] {
                        Value::String(text) => hex_bytes(text),
                        reference => {
                            let chunk = &self.chunks[reference["chunk"].as_str().expect("chunk")];
                            let start = reference.get("start").map_or(0, index);
                            let end = reference.get("end").map_or(chunk.len(), index);
                            chunk[start..end].to_vec()
                        }
                    };
                    part.repeat(index(&segment[1]))
                })
                .collect();
        }
        let mut raw = self.chunks[spec["chunk"].as_str().expect("chunk")].clone();
        if let Some(length) = spec.get("length") {
            raw.truncate(index(length));
        }
        raw
    }

    /// Replace every refusal index of an expected value by its text.
    fn with_texts(&self, value: &Value) -> Value {
        match value {
            Value::Object(members) => Value::Object(
                members
                    .iter()
                    .map(|(key, item)| {
                        let item = match item.as_u64().filter(|_| key == "refusal") {
                            Some(number) => Value::from(
                                self.texts[usize::try_from(number).expect("index")].as_str(),
                            ),
                            None => self.with_texts(item),
                        };
                        (key.clone(), item)
                    })
                    .collect(),
            ),
            Value::Array(items) => {
                Value::Array(items.iter().map(|item| self.with_texts(item)).collect())
            }
            other => other.clone(),
        }
    }
}

/// A reader's integer as a JSON number; only the end of the RV64 space exceeds 64 bits.
fn number(value: u128) -> Value {
    u64::try_from(value).map_or_else(
        |_| {
            assert_eq!(
                value, ADDRESS_END,
                "a reader value beyond the RV64 address space"
            );
            Value::from(2f64.powi(64))
        },
        Value::from,
    )
}

/// A reader outcome as Python's `{"value": ...}` or `{"refusal": text}`.
fn attempt<T>(result: Result<T, String>, value: impl FnOnce(T) -> Value) -> Value {
    match result {
        Ok(found) => json!({"value": value(found)}),
        Err(refusal) => json!({"refusal": refusal}),
    }
}

/// A decoded tree as plain data in document order, as Python's corpus holds it.
fn tree_value(tree: &DeviceTree) -> Value {
    json!({
        "nodes": tree.nodes().iter().map(|node| json!([
            node.path(),
            node.properties().iter().map(|(name, value)| json!([name, hex(value)])).collect::<Vec<_>>(),
        ])).collect::<Vec<_>>(),
        "reservations": tree.reservations().iter().map(|&(address, size)| json!([address, size])).collect::<Vec<_>>(),
        "boot_cpu": tree.boot_cpu(),
    })
}

/// The SHA-256 of a tree's binary form, as Python's `_tree_digest` defines it.
fn tree_digest(tree: &DeviceTree) -> String {
    let length = |count: usize| u32::try_from(count).expect("length").to_be_bytes();
    let mut form = Vec::new();
    form.extend(tree.boot_cpu().to_be_bytes());
    form.extend(length(tree.reservations().len()));
    for &(address, size) in tree.reservations() {
        form.extend(address.to_be_bytes());
        form.extend(size.to_be_bytes());
    }
    form.extend(length(tree.nodes().len()));
    for node in tree.nodes() {
        form.extend(length(node.path().len()));
        form.extend(node.path().as_bytes());
        form.extend(length(node.properties().len()));
        for (name, value) in node.properties() {
            form.extend(length(name.len()));
            form.extend(name.as_bytes());
            form.extend(length(value.len()));
            form.extend(value);
        }
    }
    digest(&form)
}

/// One PLIC binding's context and register addresses.
fn plic_value(tree: &DeviceTree, selection: &PlicSelection) -> Value {
    attempt(bind_plic(tree, selection), |registers| {
        json!([
            registers.context,
            number(registers.priority),
            number(registers.enable_word),
            number(registers.threshold),
            number(registers.claim),
        ])
    })
}

/// Every reader outcome of one tree under the corpus's flat keys.
fn readers(tree: &DeviceTree) -> Map<String, Value> {
    let regions = |path: &str| {
        attempt(register_regions(tree, path), |regions| {
            Value::Array(
                regions
                    .iter()
                    .map(|region| json!([number(region.address), number(region.size)]))
                    .collect(),
            )
        })
    };
    let mut outcomes = Map::new();
    for node in tree.nodes() {
        let path = node.path();
        outcomes.insert(format!("regions {path}"), regions(path));
        if node.property("compatible").is_some() {
            let strings = attempt(string_list(node, "compatible"), Value::from);
            outcomes.insert(format!("compatible {path}"), strings);
        }
        for name in CELLS
            .into_iter()
            .filter(|name| node.property(name).is_some())
        {
            outcomes.insert(
                format!("{name} {path}"),
                attempt(single_cell(node, name), Value::from),
            );
        }
    }
    outcomes.insert(format!("regions {ABSENT_NODE}"), regions(ABSENT_NODE));
    let handles = attempt(phandle_nodes(tree), |handles| {
        handles
            .iter()
            .map(|(handle, node)| (handle.to_string(), Value::from(node.path())))
            .collect::<Map<_, _>>()
            .into()
    });
    outcomes.insert("phandles".to_owned(), handles);
    let paths = tree
        .nodes()
        .iter()
        .map(|node| node.path())
        .filter(|path| path.contains("plic"));
    for path in paths {
        for (binding, name) in [
            (PlicBinding::Sifive, "sifive"),
            (PlicBinding::Spike, "spike"),
        ] {
            for hart in PLIC_HARTS {
                for source in PLIC_SOURCES {
                    let selection = PlicSelection {
                        path: path.to_owned(),
                        hart,
                        source,
                        binding,
                    };
                    let key = format!("plic {path} {name} {hart} {source}");
                    outcomes.insert(key, plic_value(tree, &selection));
                }
            }
        }
    }
    let absent = PlicSelection {
        path: ABSENT_PLIC.to_owned(),
        hart: 1,
        source: 1,
        binding: PlicBinding::Spike,
    };
    outcomes.insert(
        format!("plic {ABSENT_PLIC} spike 1 1"),
        plic_value(tree, &absent),
    );
    outcomes
}

/// Reader outcomes that differ from a reference tree's, as Python's `_changes` lists them.
fn changes(reference: &Map<String, Value>, current: &Map<String, Value>) -> Value {
    let set: Map<String, Value> = current
        .iter()
        .filter(|(key, value)| reference.get(*key) != Some(*value))
        .map(|(key, value)| (key.clone(), value.clone()))
        .collect();
    let drop: Vec<&String> = reference
        .keys()
        .filter(|key| !current.contains_key(*key))
        .collect();
    json!({"set": set, "drop": drop})
}

#[test]
fn every_named_blob_decodes_and_reads_as_python() {
    let corpus = Corpus::load();
    let cases = corpus.document["cases"].as_array().expect("cases");
    assert!(cases.len() > 100);
    let mut outcomes: HashMap<String, Map<String, Value>> = HashMap::new();
    for case in cases {
        let expected = corpus.with_texts(case);
        let name = expected["name"].as_str().expect("name");
        let tree = match decode_device_tree(&corpus.blob(&expected["blob"])) {
            Ok(tree) => tree,
            Err(refusal) => {
                assert_eq!(
                    Some(&Value::from(refusal)),
                    expected.get("refusal"),
                    "{name}"
                );
                continue;
            }
        };
        assert!(
            expected.get("refusal").is_none(),
            "{name}: decoded where Python refused"
        );
        match expected.get("tree") {
            Some(whole) => assert_eq!(&tree_value(&tree), whole, "{name}"),
            None => assert_eq!(tree_digest(&tree), expected["tree_sha256"], "{name}"),
        }
        if let Some(whole) = expected.get("readers") {
            let found = readers(&tree);
            assert_eq!(&Value::Object(found.clone()), whole, "{name}");
            outcomes.insert(name.to_owned(), found);
        }
        if let Some(change) = expected.get("readers_change") {
            let reference = &outcomes[change["from"].as_str().expect("reference")];
            let found = changes(reference, &readers(&tree));
            assert_eq!(found["set"], change["set"], "{name}");
            assert_eq!(found["drop"], change["drop"], "{name}");
        }
    }
}

#[test]
fn every_byte_change_of_the_small_tree_decodes_as_python() {
    let corpus = Corpus::load();
    let base = &corpus.chunks["reservations"];
    let rows = corpus.document["sweep"].as_array().expect("sweep");
    assert!(rows.len() > 800);
    for row in rows {
        let row = corpus.with_texts(row);
        let (offset, change) = (index(&row[0]), hex_bytes(row[1].as_str().expect("hex")));
        let mut raw = base.clone();
        raw[offset..offset + change.len()].copy_from_slice(&change);
        let found = match decode_device_tree(&raw) {
            Ok(tree) => json!({"tree_sha256": tree_digest(&tree)}),
            Err(refusal) => json!({"refusal": refusal}),
        };
        assert_eq!(found, row[2], "change at {offset}: {}", row[1]);
    }
}

#[test]
fn the_only_number_beyond_64_bits_is_the_end_of_the_address_space() {
    // Python writes the end of the RV64 space as an exact integer that the JSON
    // reader holds as a float; count that literal in the text and every float
    // in the document, so no other value beyond 64 bits can hide behind it.
    fn floats(value: &Value) -> usize {
        match value {
            Value::Number(number) if number.is_f64() => {
                assert_eq!(number.as_f64(), Some(2f64.powi(64)));
                1
            }
            Value::Array(items) => items.iter().map(floats).sum(),
            Value::Object(members) => members.values().map(floats).sum(),
            _ => 0,
        }
    }
    let literal = ADDRESS_END.to_string();
    let written = CORPUS
        .match_indices(&literal)
        .filter(|&(at, _)| {
            CORPUS[..at].ends_with([',', '[', ':'])
                && CORPUS[at + literal.len()..].starts_with([',', ']', '}'])
        })
        .count();
    assert!(written > 0);
    assert_eq!(floats(&Corpus::load().document), written);
}
