// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — traced open records, shared with the Python verifier

//! Read every case of the shared trace corpus exactly as the Python test does.

use super::opened;
use serde_json::Value;
use std::collections::BTreeSet;
use std::sync::atomic::{AtomicU64, Ordering};

const CORPUS: &str = include_str!("../data/neural-checker-traces.json");

#[test]
fn the_shared_trace_corpus_reads_alike() {
    static NEXT: AtomicU64 = AtomicU64::new(0);
    let corpus: Value = serde_json::from_str(CORPUS).expect("shared trace corpus");
    for case in corpus["cases"].as_array().expect("cases") {
        let root = std::env::temp_dir().join(format!(
            "witness-trace-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        std::fs::create_dir(&root).expect("owned working directory");
        let root = root.canonicalize().expect("resolved working directory");
        for name in corpus["files"].as_array().expect("files") {
            let path = root.join(name.as_str().expect("file name"));
            std::fs::create_dir_all(path.parent().expect("parent")).expect("parent directory");
            std::fs::write(path, b"").expect("corpus file");
        }
        let text = root.to_str().expect("UTF-8 working directory");
        let escaped: String = text.bytes().map(|byte| format!("\\x{byte:02x}")).collect();
        let mut raw = Vec::new();
        for line in case["lines"].as_array().expect("lines") {
            let line = line.as_str().expect("line");
            raw.extend_from_slice(
                line.replace("{root_hex}", &escaped)
                    .replace("{root}", text)
                    .as_bytes(),
            );
            raw.push(b'\n');
        }
        if case["invalid_utf8"] == true {
            raw.extend_from_slice(b"\xff\n");
        }
        let result = opened(&raw, &root);
        std::fs::remove_dir_all(&root).expect("remove only this case's directory");
        let name = &case["name"];
        match case["refusal"].as_str() {
            Some(refusal) => assert_eq!(result, Err(refusal.to_owned()), "{name}"),
            None => {
                let expected: BTreeSet<_> = case["opened"]
                    .as_array()
                    .expect("opened files")
                    .iter()
                    .map(|name| root.join(name.as_str().expect("opened name")))
                    .collect();
                assert_eq!(result, Ok(expected), "{name}");
            }
        }
    }
}
