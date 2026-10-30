// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — public integer encoding and original-byte preservation

//! Exercise integer-zero lexical parity through the public manifest reader.

use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};
use witness_analysis::load_neural_manifest;

const ORIGINAL: &str = include_str!("data/neural-selected-original.run.json");

struct Declaration {
    root: PathBuf,
}

impl Declaration {
    fn create(raw: &str) -> Self {
        static NEXT: AtomicU64 = AtomicU64::new(0);
        let instant = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("current clock")
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "witness-integer-{}-{instant}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        std::fs::create_dir(&root).expect("exclusive integer declaration allocation");
        std::fs::write(root.join("run.json"), raw).expect("actual declaration bytes");
        Self { root }
    }

    fn read(&self) -> Result<serde_json::Value, String> {
        load_neural_manifest(&self.root.join("run.json"))
    }
}

impl Drop for Declaration {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.root).expect("remove only own integer allocation");
    }
}

#[test]
fn complete_integer_zero_spellings_share_the_original_value() {
    for token in ["0", "-0", " -0 ", "\t-0\r\n"] {
        let raw = ORIGINAL.replacen("\"epoch\": 0", &format!("\"epoch\": {token}"), 1);
        let original_bytes = raw.as_bytes();
        let declaration = Declaration::create(&raw);
        let value = declaration
            .read()
            .expect("complete integer-zero declaration");
        assert_eq!(value["epoch"].as_u64(), Some(0));
        assert_eq!(
            std::fs::read(declaration.root.join("run.json")).unwrap(),
            original_bytes
        );
    }
    let declaration = Declaration::create(&ORIGINAL.replace(": 0", ": -0"));
    assert_eq!(declaration.read().unwrap()["epoch"].as_u64(), Some(0));
}

#[test]
fn string_escapes_and_integer_tokens_have_independent_meanings() {
    let mut value: serde_json::Value = serde_json::from_str(ORIGINAL).unwrap();
    let text = "literal-0";
    value["run_id"] = text.into();
    let encoded = serde_json::to_string(&value)
        .unwrap()
        .replace("\"literal-0\"", "\"\\u006citeral-0\"");
    for raw in [
        encoded.clone(),
        encoded.replacen("\"epoch\":0", "\"epoch\":-0", 1),
    ] {
        let declaration = Declaration::create(&raw);
        let parsed = declaration.read().unwrap();
        assert_eq!(parsed["epoch"].as_u64(), Some(0));
        assert_eq!(parsed["run_id"].as_str(), Some(text));
    }
    for invalid in ["literal-0\"x", "literal-0\\x"] {
        value["run_id"] = invalid.into();
        let declaration = Declaration::create(&serde_json::to_string(&value).unwrap());
        assert!(declaration.read().is_err());
    }
}

#[test]
fn decimal_exponent_boolean_and_malformed_number_aliases_stay_refused() {
    for token in [
        "0.0", "-0.0", "0e0", "-0e0", "1e-0", "-1", "true", "--0", "-00", "-0x", "+0",
    ] {
        let raw = ORIGINAL.replacen("\"epoch\": 0", &format!("\"epoch\": {token}"), 1);
        let declaration = Declaration::create(&raw);
        assert!(declaration.read().is_err(), "accepted {token}");
    }
}

#[test]
fn integer_token_handling_never_erases_duplicate_fields_or_object_kinds() {
    for raw in [
        ORIGINAL.replacen("\"epoch\": 0", "\"epoch\": -0, \"epoch\": 0", 1),
        ORIGINAL.replacen("\"epoch\": 0", "\"epoch\": 0, \"epoch\": -0", 1),
        "-0".into(),
        "[-0]".into(),
        "{\"epoch\":-0}".into(),
    ] {
        let declaration = Declaration::create(&raw);
        assert!(declaration.read().is_err());
    }
}
