// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — actual public Rust library snapshot and report parity

//! Verify original-file refusal and, with supplied acquisitions, full immutable snapshots.

use serde_json::Value;
use std::path::PathBuf;
use witness_analysis::public_api::{build_neural_run_report, load_neural_run};

/// Compare all original observations while preserving fresh invocation evidence separately.
fn original_observations(mut report: Value) -> Value {
    report["source_binding"]
        .as_object_mut()
        .expect("complete source report")
        .remove("checker_invocations");
    report["source_binding"]["original_inputs"]
        .as_object_mut()
        .expect("complete original bindings")
        .retain(|role, _| !role.starts_with("fresh_checker_"));
    report
}

#[test]
fn public_source_admission_and_snapshot() {
    if std::env::var_os("PUBLIC_NEURAL_MANIFEST").is_none() {
        let recorded = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("tests/data/neural-selected-original.run.json");
        let refusal = load_neural_run(&recorded)
            .err()
            .expect("the packaged entry needs an operator-selected descriptor");
        assert_eq!(
            refusal,
            "No reviewed checker installation descriptor is selected for this neural registration."
        );
        return;
    }
    let manifest = PathBuf::from(
        std::env::var("PUBLIC_NEURAL_MANIFEST").expect("actual original public acquisition"),
    );
    let expected = PathBuf::from(
        std::env::var("PUBLIC_NEURAL_PYTHON_REPORT").expect("actual complete public Python report"),
    );
    let inputs = load_neural_run(&manifest).expect("complete source-admitted library analysis");
    let original = build_neural_run_report(&inputs);
    let mut caller = build_neural_run_report(&inputs);
    caller["verification"]["whole"] = Value::String("caller mutation".into());
    assert_eq!(build_neural_run_report(&inputs), original);
    for operation in ["generate", "check"] {
        let invocation = &original["source_binding"]["checker_invocations"][operation];
        assert_eq!(invocation["native_returncode"], 0);
        assert_eq!(invocation["worker_observation"]["native_returncode"], 0);
        assert_eq!(invocation["worker_observation"]["phase"], "source");
        assert_eq!(invocation["interrupted"], false);
        assert!(
            invocation["elapsed_ns"]
                .as_u64()
                .expect("real elapsed time")
                > 0
        );
        assert!(
            invocation["worker_observation"]["modules"]
                .as_array()
                .expect("actual imported modules")
                .iter()
                .any(|module| module["name"]
                    .as_str()
                    .is_some_and(|name| name.starts_with("sc_neurocore")))
        );
    }
    let python: Value =
        serde_json::from_slice(&std::fs::read(expected).expect("complete original Python report"))
            .expect("original report JSON");
    assert_eq!(
        original_observations(original),
        original_observations(python)
    );
}
