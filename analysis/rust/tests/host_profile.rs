// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — host timeout scales alike in the native and Python tests

//! Hold the integration tests' reading of the declared host timeout scale to
//! the Python module's outcomes in the shared corpus.

#[path = "support/host_profile.rs"]
mod host_profile;

use host_profile::{SCALE_VARIABLE, guard, scale_of, timeout_arguments, whole_seconds};
use serde_json::Value;

/// The declarations and the Python module's outcomes.
const CORPUS: &str = include_str!("data/host-timeout-scales.json");

#[test]
fn every_declaration_has_the_python_outcome() {
    let corpus: Value = serde_json::from_str(CORPUS).expect("the shared corpus");
    let cases = corpus["cases"].as_array().expect("the corpus cases");
    assert_eq!(cases.len(), 37);
    for case in cases {
        let declared = case["declared"].as_str();
        let outcome = scale_of(declared);
        if let Some(refusal) = case["refusal"].as_str() {
            assert_eq!(outcome, Err(refusal.to_owned()), "{declared:?}");
            continue;
        }
        let expected: f64 = case["scale"]
            .as_str()
            .and_then(|text| text.parse().ok())
            .expect("Python's repr of the scale");
        let scale = outcome.expect("an admitted declaration");
        assert_eq!(scale.to_bits(), expected.to_bits(), "{declared:?}");
        let ten = case["ten_seconds"].as_u64().expect("whole seconds");
        assert_eq!(whole_seconds(10, scale).to_string(), ten.to_string());
    }
}

#[test]
fn the_guard_follows_the_executing_host() {
    let declared = std::env::var(SCALE_VARIABLE).ok();
    let scale = scale_of(declared.as_deref()).expect("the executing host's timeout scale");
    assert_eq!(guard(5), format!("{}s", whole_seconds(5, scale)));
    assert_eq!(
        timeout_arguments(5),
        [
            "--signal=TERM".to_owned(),
            format!("--kill-after={}s", whole_seconds(1, scale)),
            format!("{}s", whole_seconds(5, scale)),
        ]
    );
}
