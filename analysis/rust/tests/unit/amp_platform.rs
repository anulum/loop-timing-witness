// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — AMP platform binding held to Python's corpus

//! Hold the platform binding to Python's outcome for every case of the shared
//! corpus.
//!
//! `tests/test_amp_platform_corpus.py` compiles each case with the real `dtc`,
//! binds it with Python's `bind_platform` and requires the committed file to
//! equal it; this test rebuilds the same blobs and selections and requires the
//! same platform, as `dataclasses.asdict` writes it, or the same refusal.

use super::{AmpPlatform, MemorySelection, bind_platform};
use crate::device_tree::{PlicBinding, PlicSelection, Region, decode_device_tree};
use crate::unit_files::hex_bytes;
use serde_json::{Map, Value, json};

/// The shared corpus of Python's outcomes.
const CORPUS: &str = include_str!("../data/amp-platform-cases.json");

/// A case's blob: the base with `[start, end, hex]` byte ranges replaced.
fn blob(base: &[u8], ranges: &Value) -> Vec<u8> {
    let mut built = Vec::new();
    let mut position = 0;
    for range in ranges.as_array().expect("ranges") {
        let start = usize::try_from(range[0].as_u64().expect("start")).expect("offset");
        built.extend_from_slice(&base[position..start]);
        built.extend(hex_bytes(range[2].as_str().expect("bytes")));
        position = usize::try_from(range[1].as_u64().expect("end")).expect("offset");
    }
    built.extend_from_slice(&base[position..]);
    built
}

/// One extent as `asdict` writes it.
fn region(region: Region) -> Value {
    let number = |value: u128| u64::try_from(value).expect("a 64-bit value");
    json!({"address": number(region.address), "size": number(region.size)})
}

/// The admitted platform as `dataclasses.asdict` writes it.
fn platform(platform: &AmpPlatform) -> Value {
    let plic = platform.device.plic;
    let word = |value: u128| u64::try_from(value).expect("a 64-bit address");
    json!({
        "memory": {"firmware": region(platform.memory.firmware), "shared": region(platform.memory.shared)},
        "device": {
            "aperture": region(platform.device.aperture),
            "plic": {
                "context": plic.context,
                "priority": word(plic.priority),
                "enable_word": word(plic.enable_word),
                "threshold": word(plic.threshold),
                "claim": word(plic.claim),
            },
        },
        "hart": i64::try_from(platform.hart).expect("a hart"),
        "source": i64::try_from(platform.source).expect("a source"),
    })
}

#[test]
fn platform_bindings_equal_python() {
    let corpus: Value = serde_json::from_str(CORPUS).expect("corpus");
    let base = hex_bytes(corpus["base"].as_str().expect("base"));
    for case in corpus["cases"].as_array().expect("cases") {
        let mut chosen = corpus["selection"].as_object().expect("selection").clone();
        chosen.extend(case["selection"].as_object().expect("overrides").clone());
        let text = |name: &str| chosen[name].as_str().expect("text").to_owned();
        let integer = |name: &str| i128::from(chosen[name].as_i64().expect("integer"));
        let memory = MemorySelection {
            ram_path: text("ram"),
            firmware_path: text("firmware"),
            shared_path: text("shared"),
            mailbox_bytes: integer("mailbox"),
            stack_bytes: integer("stack"),
        };
        let binding = if text("layout") == "spike" {
            PlicBinding::Spike
        } else {
            PlicBinding::Sifive
        };
        let plic = PlicSelection {
            path: text("plic"),
            hart: integer("hart"),
            source: integer("source"),
            binding,
        };
        let tree = decode_device_tree(&blob(&base, &case["blob"])).expect("a compiled platform");
        let found = match bind_platform(&tree, &memory, &text("device"), &plic) {
            Ok(admitted) => json!({"platform": platform(&admitted)}),
            Err(refusal) => json!({"refusal": refusal}),
        };
        let expected: Map<String, Value> = case
            .as_object()
            .expect("case")
            .iter()
            .filter(|(key, _)| matches!(key.as_str(), "platform" | "refusal"))
            .map(|(key, value)| (key.clone(), value.clone()))
            .collect();
        assert_eq!(found, Value::Object(expected), "{}", case["name"]);
    }
}
