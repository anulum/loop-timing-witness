// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — AMP image contract and exit channel held to Python's corpus

//! Hold the image contract and ISA exit channel admission to Python's
//! outcome for every case of the shared corpus.
//!
//! `tests/test_amp_image_contract_corpus.py` changes the whole firmware of
//! `amp-elf-cases.json` and the inputs per case, admits each case as the
//! image receipt does and requires the committed file to equal it; this test
//! applies the same changes and requires the same segments and exit outcome,
//! or the same refusal.

use super::admit_image_contract;
use crate::amp_elf::LoadSegment;
use crate::amp_exit_channel::admit_exit_channel;
use crate::amp_platform::{AmpPlatform, ReservedMemory, WitnessDevice};
use crate::amp_run_input::AmpRun;
use crate::device_tree::{PlicRegisters, Region};
use crate::unit_files::hex_bytes;
use serde_json::{Value, json};

/// The ELF corpus holding the firmware.
const IMAGES: &str = include_str!("../data/amp-elf-cases.json");
/// The shared corpus of Python's outcomes.
const CORPUS: &str = include_str!("../data/amp-image-contract-cases.json");

/// A JSON number of the corpus as an unsigned integer.
fn number(value: &Value) -> u64 {
    value.as_u64().expect("an unsigned number")
}

/// An extent as `asdict` writes it.
fn region(value: &Value) -> Region {
    Region {
        address: u128::from(number(&value["address"])),
        size: u128::from(number(&value["size"])),
    }
}

/// The platform as `asdict` writes it.
fn platform(value: &Value) -> AmpPlatform {
    let plic = &value["device"]["plic"];
    let word = |name: &str| u128::from(number(&plic[name]));
    AmpPlatform {
        memory: ReservedMemory {
            firmware: region(&value["memory"]["firmware"]),
            shared: region(&value["memory"]["shared"]),
        },
        device: WitnessDevice {
            aperture: region(&value["device"]["aperture"]),
            plic: PlicRegisters {
                context: usize::try_from(number(&plic["context"])).expect("a context"),
                priority: word("priority"),
                enable_word: word("enable_word"),
                threshold: word("threshold"),
                claim: word("claim"),
            },
        },
        hart: i128::from(number(&value["hart"])),
        source: i128::from(number(&value["source"])),
    }
}

/// The run as `asdict` writes it.
fn run(value: &Value) -> AmpRun {
    let field = |name: &str| u32::try_from(number(&value[name])).expect("a 32-bit field");
    let coefficients: Vec<i32> = value["coefficients"]
        .as_array()
        .expect("coefficients")
        .iter()
        .map(|item| i32::try_from(item.as_i64().expect("a coefficient")).expect("32 bits"))
        .collect();
    AmpRun {
        cycles: field("cycles"),
        period_ticks: field("period_ticks"),
        lqr: field("lqr") == 1,
        overload_iterations: field("overload_iterations"),
        coefficients: coefficients.try_into().expect("eleven coefficients"),
    }
}

/// The base inputs with a case's `[path, value]` changes.
fn changed(inputs: &Value, changes: &Value) -> Value {
    let mut document = inputs.clone();
    for change in changes.as_array().expect("changes") {
        let mut node = &mut document;
        for key in change[0].as_array().expect("path") {
            node = match key {
                Value::String(name) => &mut node[name.as_str()],
                index => &mut node[usize::try_from(number(index)).expect("an index")],
            };
        }
        *node = change[1].clone();
    }
    document
}

/// The firmware with a case's `[offset, hex]` edits.
fn edited(firmware: &[u8], edits: &Value) -> Vec<u8> {
    let mut content = firmware.to_vec();
    for edit in edits.as_array().expect("edits") {
        let offset = usize::try_from(number(&edit[0])).expect("an offset");
        let bytes = hex_bytes(edit[1].as_str().expect("hex"));
        content[offset..offset + bytes.len()].copy_from_slice(&bytes);
    }
    content
}

/// The segments as `asdict` writes them.
fn segments(admitted: &[LoadSegment]) -> Value {
    admitted
        .iter()
        .map(|segment| {
            json!({
                "offset": segment.offset,
                "address": segment.address,
                "file_bytes": segment.file_bytes,
                "memory_bytes": segment.memory_bytes,
                "flags": segment.flags,
            })
        })
        .collect()
}

#[test]
fn image_contracts_equal_python() {
    let images: Value = serde_json::from_str(IMAGES).expect("ELF corpus");
    let corpus: Value = serde_json::from_str(CORPUS).expect("corpus");
    let firmware = hex_bytes(
        images["images"]["firmware"]["hex"]
            .as_str()
            .expect("firmware"),
    );
    assert_eq!(
        images["images"]["firmware"]["sha256"],
        corpus["firmware_sha256"]
    );
    let cases = corpus["cases"].as_array().expect("cases");
    assert_eq!(cases.len(), 106);
    for case in cases {
        let name = case["name"].as_str().expect("name");
        let inputs = changed(&corpus["inputs"], &case["changes"]);
        let content = edited(&firmware, &case["edits"]);
        let stack = i128::from(inputs["stack"].as_i64().expect("stack"));
        let outcome = match admit_image_contract(
            &content,
            &platform(&inputs["platform"]),
            &run(&inputs["run"]),
            stack,
        ) {
            Err(refusal) => json!({"contract": {"refusal": refusal}, "exit": null}),
            Ok(admitted) => {
                let exit = match admit_exit_channel(&content, &admitted) {
                    Ok(()) => json!("admitted"),
                    Err(refusal) => json!({"refusal": refusal}),
                };
                json!({"contract": {"segments": segments(&admitted)}, "exit": exit})
            }
        };
        let expected = json!({"contract": case["contract"], "exit": case["exit"]});
        assert_eq!(outcome, expected, "{name}");
    }
}
