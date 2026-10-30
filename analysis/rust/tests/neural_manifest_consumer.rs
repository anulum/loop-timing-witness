// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — actual Rust public manifest and command controls

//! Exercise closed declarations without manufacturing source-policy admission.

mod support;

use serde_json::{Value, json};
use std::process::Command;
use support::Declaration;
use witness_analysis::{load_neural_manifest, load_neural_run};

#[test]
fn original_declarations_and_complete_source_population() {
    let fixture = Declaration::recorded();
    let path = fixture.write("original.json", Declaration::raw());
    let original = load_neural_manifest(&path).expect("exact captured declarations");
    assert_eq!(
        original["schema_id"],
        "loop-timing-witness.neural-step-run.v1"
    );
    assert_eq!(
        original["source_files"]
            .as_array()
            .expect("complete source declarations")
            .len(),
        57
    );
    let mut larger = fixture.value();
    let mut reference = larger["source_files"][0].clone();
    for index in 0..8 {
        reference["path"] = json!(format!("source/extra-source-{index}.py"));
        larger["source_files"]
            .as_array_mut()
            .expect("source declarations")
            .push(reference.clone());
    }
    let path = fixture.write(
        "sixty-five.json",
        &serde_json::to_vec(&larger).expect("complete JSON"),
    );
    let declared = load_neural_manifest(&path).expect("no arbitrary 64-source shape cap");
    assert_eq!(
        declared["source_files"]
            .as_array()
            .expect("all declarations")
            .len(),
        65
    );
    assert!(
        load_neural_run(&path).is_err(),
        "declarations cannot manufacture source admission"
    );
}

#[test]
fn malformed_bytes_and_non_object_roots_have_no_carrier_identity() {
    let fixture = Declaration::recorded();
    for raw in [
        b"".as_slice(),
        b"{",
        b"\xff",
        b"NaN",
        b"null",
        b"true",
        b"1",
        b"[]",
        b"{}",
        br#"{"run_id":"\uD800"}"#,
    ] {
        let path = fixture.write("invalid-root.json", raw);
        assert!(load_neural_manifest(&path).is_err());
        assert!(load_neural_run(&path).is_err());
    }
}

#[test]
fn closed_manifest_grammar_refuses_actual_input_contradictions() {
    let fixture = Declaration::recorded();
    let mut cases: Vec<(&str, Value)> = Vec::new();
    for (field, value) in [
        ("schema_id", json!("unsupported")),
        ("native_source_cohort", Value::Null),
        ("native_source_cohort", json!("unsupported")),
        ("profile", json!("unsupported")),
        ("evidence_class", json!("physical-timing")),
        ("source_files", Value::Null),
        ("channels", Value::Null),
        ("epoch", json!(2)),
        ("step_count", json!(1000.0)),
        ("step_count", json!(999)),
        ("counter_bits", json!(true)),
        ("counter_bits", json!(32)),
        ("encoder_timestamp_bits", json!(15)),
        ("encoder_id_width", json!(0)),
        ("fifo_capacity_records", json!(7)),
        ("capture_horizon_edges", json!(0)),
        ("capture_horizon_edges", json!(65536)),
        ("encoder_tail_edges", json!(3)),
        ("run_id", json!("")),
        ("run_id", json!("a".repeat(129))),
        ("run_id", json!("-leading")),
        ("run_id", json!("invalid name")),
        ("accepted_oracle_commit", json!("0".repeat(40))),
    ] {
        let mut control = fixture.value();
        control[field] = value;
        cases.push((field, control));
    }
    let mut control = fixture.value();
    control["unexpected"] = json!(0);
    cases.push(("unknown-root", control));
    let mut control = fixture.value();
    control
        .as_object_mut()
        .expect("original object")
        .remove("source_contract_ref");
    cases.push(("missing-contract-role", control));
    let mut control = fixture.value();
    control["source_files"][1] = control["source_files"][0].clone();
    cases.push(("duplicate-source-path", control));
    for path in [
        "/absolute",
        "../escape",
        "source/../escape",
        "source\\escape",
        "source/\0escape",
    ] {
        let mut control = fixture.value();
        control["input_trace"]["path"] = json!(path);
        cases.push(("nonportable-reference", control));
    }
    for (label, value) in cases {
        let raw = serde_json::to_vec(&value).expect("whole input control");
        let path = fixture.write("contradiction.json", &raw);
        assert!(load_neural_manifest(&path).is_err(), "{label}");
        assert!(load_neural_run(&path).is_err(), "{label}");
    }
    let duplicate = [
        b"{\"schema_id\":\"unsupported\",".as_slice(),
        &Declaration::raw()[1..],
    ]
    .concat();
    let path = fixture.write("duplicate.json", &duplicate);
    assert!(load_neural_manifest(&path).is_err());
    let mut oversized = Declaration::raw().to_vec();
    oversized.extend(vec![b' '; 65536]);
    let path = fixture.write("oversized.json", &oversized);
    assert!(load_neural_manifest(&path).is_err());
}

#[test]
fn declaration_boundaries_do_not_admit_absent_sources() {
    let fixture = Declaration::recorded();
    for (field, values) in [
        ("epoch", vec![json!(0), json!(1)]),
        (
            "run_id",
            vec![json!("a"), json!("a".repeat(128)), json!("a_.-Z9")],
        ),
        ("fifo_capacity_records", vec![json!(8), json!(1024)]),
        ("capture_horizon_edges", vec![json!(1), json!(65535)]),
    ] {
        for value in values {
            let mut control = fixture.value();
            control[field] = value;
            let path = fixture.write(
                "boundary.json",
                &serde_json::to_vec(&control).expect("complete declaration"),
            );
            assert_eq!(
                load_neural_manifest(&path).expect("valid carrier boundary"),
                control
            );
        }
    }
    let mut control = fixture.value();
    control["source_files"][0]["path"] = json!("a".repeat(4096));
    control["source_files"][0]["byte_length"] = json!(1048576);
    let path = fixture.write(
        "source-boundary.json",
        &serde_json::to_vec(&control).expect("complete declaration"),
    );
    assert_eq!(
        load_neural_manifest(&path).expect("bounded declarations only"),
        control
    );
    assert!(
        load_neural_run(&path).is_err(),
        "a declaration never supplies original sources"
    );
}

#[test]
fn source_channel_and_completion_declarations_retain_their_exact_contracts() {
    let fixture = Declaration::recorded();
    let original = fixture.value();
    let mut cases: Vec<Value> = Vec::new();
    for pin in original["sc_body_pins"]
        .as_object()
        .expect("original seven pins")
        .keys()
    {
        let mut control = original.clone();
        control["sc_body_pins"][pin] = json!("A".repeat(64));
        cases.push(control);
    }
    let mut control = original.clone();
    control["source_files"] = json!([]);
    cases.push(control);
    for (field, value) in [
        ("path", json!("")),
        ("path", json!("a".repeat(4097))),
        ("path", json!("source//input.py")),
        ("path", json!("source/./input.py")),
        ("sha256", json!("0".repeat(63))),
        ("sha256", json!("g".repeat(64))),
        ("byte_length", json!(1048577)),
    ] {
        let mut control = original.clone();
        control["source_files"][0][field] = value;
        cases.push(control);
    }
    for role in [
        "tool_receipt",
        "input_trace",
        "numerical_trace",
        "numerical_projection",
        "reference_projection",
        "service_trace",
        "clock_schedule_ref",
        "source_contract_ref",
    ] {
        let mut control = original.clone();
        control[role]["byte_length"] = json!(65537);
        cases.push(control);
    }
    for field in [
        "requested_steps",
        "observed_states",
        "raw_spikes",
        "observed_service_packets",
    ] {
        let mut control = original.clone();
        control["completion"][field] = json!(65536);
        cases.push(control);
    }
    for field in original["event_codes"]
        .as_object()
        .expect("original event vocabulary")
        .keys()
    {
        let mut control = original.clone();
        control["event_codes"][field] = json!(0);
        cases.push(control);
    }
    for index in 0..3 {
        let mut control = original.clone();
        control["channels"][index]["role"] = json!(if index == 0 { "state" } else { "input" });
        cases.push(control);
        let mut control = original.clone();
        control["channels"][index]["marker_records"] = json!(3);
        cases.push(control);
        for field in [
            "attempts",
            "accepted",
            "dropped",
            "drained",
            "payload_records",
        ] {
            let mut control = original.clone();
            control["channels"][index][field] = json!(65536);
            cases.push(control);
        }
        for role in ["capture", "payload", "markers"] {
            let mut control = original.clone();
            control["channels"][index][role]["byte_length"] = json!(65537);
            cases.push(control);
        }
    }
    for control in cases {
        let path = fixture.write(
            "contradiction.json",
            &serde_json::to_vec(&control).expect("actual declaration contradiction"),
        );
        assert!(
            load_neural_manifest(&path).is_err(),
            "unsupported carrier declaration was accepted"
        );
    }
}

#[test]
fn nested_duplicates_are_not_erased_by_object_kind_inspection() {
    let fixture = Declaration::recorded();
    let original = fixture.value();
    let root = serde_json::to_string(&original).expect("original JSON object");
    for (pointer, key, value) in [
        ("/tool_receipt", "path", json!("substituted.json")),
        ("/channels/0", "role", json!("state")),
        ("/completion", "finalized", json!(false)),
        (
            "/sc_body_pins",
            "hdl/sc_lif_neuron.v",
            json!("0".repeat(64)),
        ),
    ] {
        let object =
            serde_json::to_string(original.pointer(pointer).expect("actual schema object"))
                .expect("original object JSON");
        let duplicate = format!(
            "{{{}:{},{}",
            serde_json::to_string(key).expect("original key JSON"),
            value,
            &object[1..]
        );
        let raw = root.replacen(&object, &duplicate, 1);
        assert_eq!(
            serde_json::from_str::<Value>(&raw).expect("syntactically valid duplicate"),
            original
        );
        let path = fixture.write("duplicate-nested.json", raw.as_bytes());
        assert!(
            load_neural_manifest(&path).is_err(),
            "duplicate at {pointer} was erased before typed decoding"
        );
    }
}

#[test]
fn unadmitted_source_identity_refuses_library_and_actual_command_without_publication() {
    let fixture = Declaration::recorded();
    let mut control = fixture.value();
    control["source_contract_ref"]["sha256"] = json!("0".repeat(64));
    let path = fixture.write(
        "unsupported-source.json",
        &serde_json::to_vec(&control).expect("JSON"),
    );
    let refusal = load_neural_run(&path)
        .err()
        .expect("exact source admission required");
    assert_eq!(
        refusal,
        "No reviewed source contract is admitted for this neural run."
    );
    let output = fixture.root().join("report");
    let actual = Command::new(env!("CARGO_BIN_EXE_loop-timing-witness-analyze-native"))
        .arg(path)
        .args(["--output-dir"])
        .arg(&output)
        .output()
        .expect("real public command");
    assert_eq!(actual.status.code(), Some(1));
    assert!(actual.stdout.is_empty());
    assert!(
        String::from_utf8(actual.stderr)
            .expect("authored UTF-8")
            .contains("No reviewed source contract is admitted")
    );
    assert!(!output.exists());
}

#[test]
fn positional_root_arrays_cannot_substitute_the_schema_object() {
    let fixture = Declaration::recorded();
    let original = fixture.value();
    let positional = Value::Array(
        [
            "schema_id",
            "native_source_cohort",
            "profile",
            "evidence_class",
            "run_id",
            "epoch",
            "step_count",
            "counter_bits",
            "encoder_timestamp_bits",
            "encoder_id_width",
            "fifo_capacity_records",
            "capture_horizon_edges",
            "encoder_tail_edges",
            "source_files",
            "accepted_oracle_commit",
            "sc_body_pins",
            "tool_receipt",
            "input_trace",
            "numerical_trace",
            "numerical_projection",
            "reference_projection",
            "service_trace",
            "channels",
            "completion",
            "event_codes",
            "clock_schedule_ref",
            "source_contract_ref",
        ]
        .iter()
        .map(|name| original[name].clone())
        .collect(),
    );
    let path = fixture.write(
        "positional-root.json",
        &serde_json::to_vec(&positional).expect("actual array JSON"),
    );
    assert!(
        load_neural_manifest(&path).is_err(),
        "the public JSON schema requires an object, not positional structure values"
    );
}

#[test]
fn positional_nested_arrays_cannot_substitute_schema_objects() {
    let fixture = Declaration::recorded();
    let original = fixture.value();
    let reference_fields = ["path", "sha256", "byte_length"];
    let mut replacements: Vec<(String, Vec<&str>)> = [
        "/tool_receipt",
        "/input_trace",
        "/numerical_trace",
        "/numerical_projection",
        "/reference_projection",
        "/service_trace",
        "/clock_schedule_ref",
        "/source_contract_ref",
        "/source_files/0",
    ]
    .iter()
    .map(|pointer| (String::from(*pointer), reference_fields.to_vec()))
    .collect();
    for index in 0..3 {
        replacements.push((
            format!("/channels/{index}"),
            vec![
                "role",
                "capture",
                "payload",
                "markers",
                "attempts",
                "accepted",
                "dropped",
                "drained",
                "payload_records",
                "marker_records",
                "overflowed",
                "drop_counter_saturated",
            ],
        ));
        for role in ["capture", "payload", "markers"] {
            replacements.push((
                format!("/channels/{index}/{role}"),
                reference_fields.to_vec(),
            ));
        }
    }
    replacements.extend([
        (
            "/sc_body_pins".into(),
            vec![
                "hdl/sc_lif_neuron.v",
                "hdl/tb_sc_lif_neuron.v",
                "hdl/sc_aer_encoder.v",
                "src/sc_neurocore/neurons/fixed_point_lif.py",
                "src/sc_neurocore/constants.py",
                "scripts/cosim_gen_and_check.py",
                "tests/test_cosim_gen_and_check.py",
            ],
        ),
        (
            "/event_codes".into(),
            vec![
                "input_step_applied",
                "state_and_raw_spike_observed",
                "encoder_packet_serviced",
                "alignment_marker",
            ],
        ),
        (
            "/completion".into(),
            vec![
                "requested_steps",
                "observed_states",
                "raw_spikes",
                "observed_service_packets",
                "pending_empty",
                "service_valid_quiescent",
                "pipeline_quiescent",
                "finalized",
            ],
        ),
    ]);
    for (pointer, fields) in replacements {
        let mut control = original.clone();
        let object = original.pointer(&pointer).expect("actual original object");
        let array = Value::Array(fields.iter().map(|field| object[field].clone()).collect());
        *control
            .pointer_mut(&pointer)
            .expect("actual original carrier location") = array;
        let path = fixture.write(
            "positional-nested.json",
            &serde_json::to_vec(&control).expect("actual nested array JSON"),
        );
        assert!(
            load_neural_manifest(&path).is_err(),
            "schema object at {pointer} was accepted as a positional array"
        );
    }
}
