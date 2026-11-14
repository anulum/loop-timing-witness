// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — AMP image receipt check held to Python's corpus

//! Hold the image receipt check to Python's outcome for every case of the
//! shared corpus.
//!
//! `tests/test_amp_image_receipt_corpus.py` writes each case as a real ISA
//! image folder, checks it with Python's `validate_image_receipt` and
//! requires the committed file to equal it; this test writes the same folders
//! and documents and requires the same value, refusal or read error.

use super::validate_image_receipt;
use crate::amp_failure::AmpFailure;
use crate::unit_files::{Scratch, edited_tree, hex_bytes, patched};
use serde_json::{Value, json};

/// The ELF corpus holding the firmware.
const IMAGES: &str = include_str!("../data/amp-elf-cases.json");
/// The shared corpus of Python's outcomes.
const CORPUS: &str = include_str!("../data/amp-image-receipt-cases.json");

/// The firmware with a case's `[offset, hex]` edits, as hexadecimal text.
fn firmware_hex(firmware: &[u8], edits: &Value) -> String {
    let mut content = firmware.to_vec();
    for edit in edits.as_array().expect("edits") {
        let offset = usize::try_from(edit[0].as_u64().expect("offset")).expect("an offset");
        let bytes = hex_bytes(edit[1].as_str().expect("hex"));
        content[offset..offset + bytes.len()].copy_from_slice(&bytes);
    }
    content.iter().map(|byte| format!("{byte:02x}")).collect()
}

#[test]
fn image_receipts_equal_python() {
    let images: Value = serde_json::from_str(IMAGES).expect("ELF corpus");
    let corpus: Value = serde_json::from_str(CORPUS).expect("corpus");
    let firmware = hex_bytes(
        images["images"]["firmware"]["hex"]
            .as_str()
            .expect("firmware"),
    );
    let cases = corpus["cases"].as_array().expect("cases");
    assert_eq!(cases.len(), 63);
    let scratch = Scratch::new("amp-image-receipt");
    for (index, case) in cases.iter().enumerate() {
        let name = case["name"].as_str().expect("name");
        let directory = scratch.0.join(format!("case-{index}"));
        std::fs::create_dir(&directory).expect("case folder");
        let mut tree = corpus["tree"].as_object().expect("tree").clone();
        let firmware = firmware_hex(&firmware, &case["firmware"]);
        tree.insert("firmware.elf".into(), json!({"hex": firmware}));
        edited_tree(&directory, &tree, &case["tree"]);
        let image = patched(&corpus["image"], &case["image"]);
        let preparation = patched(&corpus["preparation"], &case["preparation"]);
        let root = directory.to_str().expect("UTF-8 folder");
        let outcome = match validate_image_receipt(
            &directory,
            image.as_object().expect("image"),
            preparation.as_object().expect("preparation"),
        ) {
            Ok(()) => json!({"value": true}),
            Err(AmpFailure::Refused(text)) => json!({"refusal": text.replace(root, "<root>")}),
            Err(AmpFailure::Os(text)) => json!({"os_error": text.replace(root, "<root>")}),
        };
        let mut expected = case.as_object().expect("case").clone();
        for part in ["name", "tree", "firmware", "image", "preparation"] {
            expected.remove(part);
        }
        assert_eq!(outcome, Value::Object(expected), "{name}");
    }
}
