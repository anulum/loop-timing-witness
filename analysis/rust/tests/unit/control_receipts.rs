// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — receipt validation, crate-internal controls

//! Hold receipt validation to Python: schema locations for the shared corpus,
//! Python's equality, and every configuration and counter check.

use super::{
    HOST_LOAD_SCHEMA, NATIVE_SCHEMA, completion_statistics, host_load, lines, python_equal,
};
use crate::control_number::Num;
use serde_json::{Map, Value, json};

/// The shared corpus of receipt schema locations.
const CORPUS: &str = include_str!("../data/control-receipt-schema-locations.json");

/// Apply one corpus change at a path of a base document.
fn changed(base: &Value, path: &[Value], change: &Value) -> Value {
    if let Some(value) = change.get("set").filter(|_| path.is_empty()) {
        return value.clone();
    }
    let mut document = base.clone();
    let keep = if change.get("set").is_some() {
        path.len() - 1
    } else {
        path.len()
    };
    let mut node = &mut document;
    for part in &path[..keep] {
        node = match part {
            Value::String(name) => &mut node[name.as_str()],
            index => &mut node[usize::try_from(index.as_u64().expect("index")).expect("index")],
        };
    }
    if let Some(value) = change.get("set") {
        match &path[keep] {
            Value::String(name) => node[name.as_str()] = value.clone(),
            index => {
                node[usize::try_from(index.as_u64().expect("index")).expect("index")] =
                    value.clone();
            }
        }
    } else if let Some(name) = change.get("remove") {
        node.as_object_mut()
            .expect("object")
            .remove(name.as_str().expect("member"));
    } else {
        node[change["add"].as_str().expect("member")] = json!(1);
    }
    document
}

#[test]
fn every_receipt_change_reports_the_python_locations() {
    let corpus: Value = serde_json::from_str(CORPUS).expect("corpus");
    for (kind, schema) in [
        ("native", &*NATIVE_SCHEMA),
        ("host_load", &*HOST_LOAD_SCHEMA),
    ] {
        let base = &corpus["bases"][kind];
        let mut count = 0;
        for group in corpus[kind].as_array().expect("groups") {
            let path = group["path"].as_array().expect("path");
            for pair in group["changes"].as_array().expect("changes") {
                let document = if pair[0].is_null() {
                    base.clone()
                } else {
                    changed(base, path, &pair[0])
                };
                let expected: Vec<String> =
                    serde_json::from_value(pair[1].clone()).expect("locations");
                assert_eq!(
                    schema.locations(&document),
                    expected,
                    "{kind} {path:?} {}",
                    pair[0]
                );
                count += 1;
            }
        }
        assert!(count > 300, "{kind}");
    }
}

#[test]
fn equality_follows_python() {
    assert!(python_equal(&json!(1), &json!(1.0)));
    assert!(python_equal(&json!(true), &json!(1)));
    assert!(!python_equal(&json!(false), &json!("")));
    assert!(python_equal(
        &json!([1, {"a": 2}]),
        &json!([1.0, {"a": 2.0}])
    ));
    assert!(!python_equal(&json!([1]), &json!([1, 2])));
    assert!(!python_equal(&json!({"a": 1}), &json!({"b": 1})));
    assert!(!python_equal(&json!({"a": 1}), &json!({"a": 1, "b": 2})));
    assert!(python_equal(&json!(null), &json!(null)));
    assert!(!python_equal(&json!("1"), &json!(1)));
    assert_eq!(lines(Num::Int(4097)).json(), json!(65));
    assert_eq!(lines(Num::Float(4097.0)).json(), json!(65.0));
}

/// A valid native metadata document from the corpus, with run-matching values.
fn native() -> Value {
    let corpus: Value = serde_json::from_str(CORPUS).expect("corpus");
    let mut native = corpus["bases"]["native"].clone();
    native["cycles"] = json!(3);
    native["period_ticks"] = json!(100);
    native["artifacts"]["events"] = json!({"sha256": "e".repeat(64), "bytes": 160});
    native["artifacts"]["configuration"]["sha256"] = json!("c".repeat(64));
    native["result"] =
        json!({"misses": 1, "overflow": 0, "records": 10, "safe": true, "samples": 3});
    native
}

/// A run declaration matching [`native`].
fn manifest() -> Map<String, Value> {
    let coefficients = native()["coefficients"].clone();
    json!({
        "fault_schedule": [],
        "source": {"kind": "rtl_simulation", "files": [{"path": "x", "sha256": "c".repeat(64)}]},
        "cycle_count": 3,
        "sample_period_ticks": 100,
        "controller": {"name": "pid", "coefficients": coefficients},
        "plant": {"name": "mechanical"},
        "files": {"events": {"sha256": "e".repeat(64)}},
        "instrument": {"fifo_overflow_count": 0},
    })
    .as_object()
    .cloned()
    .expect("object")
}

/// Control counts matching [`native`].
fn control() -> Value {
    json!({"deadline_misses": 1, "observed_deadlines": 3, "safe_state_events": 2})
}

/// The outcome of the completion check after one change to the receipt or run.
fn completion(
    native: &Value,
    manifest: &Map<String, Value>,
    control: &Value,
) -> Result<Value, String> {
    let content = serde_json::to_vec(native).expect("JSON");
    completion_statistics(&content, manifest, 10, control, 3)
}

#[test]
fn completion_checks_every_declared_fact() {
    let (native, manifest, control) = (native(), manifest(), control());
    assert_eq!(
        completion(&native, &manifest, &control),
        Ok(native["result"].clone())
    );
    let configuration = "native metadata configuration does not match the run declaration";
    let mut changes: Vec<(Value, Map<String, Value>)> = Vec::new();
    let mut amp = native.clone();
    amp["source_kind"] = json!("amp_uio_unqualified");
    amp["artifacts"]["amp_resources"] = json!({"sha256": "a".repeat(64), "bytes": 1});
    changes.push((amp, manifest.clone()));
    for (pointer, value) in [
        ("/cycles", json!(4)),
        ("/period_ticks", json!(5)),
        ("/controller", json!("lqr")),
        ("/coefficients/kp", json!(1)),
        ("/thermal", json!(true)),
        ("/result/samples", json!(9)),
        ("/artifacts/events/sha256", json!("f".repeat(64))),
        ("/artifacts/events/bytes", json!(16)),
        ("/artifacts/configuration/sha256", json!("d".repeat(64))),
    ] {
        let mut changed = native.clone();
        *changed.pointer_mut(pointer).expect("pointer") = value;
        changes.push((changed, manifest.clone()));
    }
    let mut run = manifest.clone();
    run["source"]["kind"] = json!("board");
    changes.push((native.clone(), run));
    for (changed, run) in &changes {
        assert_eq!(
            completion(changed, run, &control).err().as_deref(),
            Some(configuration)
        );
    }
    let mut fault = native.clone();
    fault["fault"] = json!({"kind": "delay", "cycle": 1, "duration_periods": 2});
    let mut scheduled = manifest.clone();
    scheduled["fault_schedule"] = json!([{"cycle": 1, "kind": "delay", "delay_periods": 2}]);
    assert!(completion(&fault, &scheduled, &control).is_ok());
    fault["fault"] = json!({"kind": "drop", "cycle": 1, "duration_periods": 2});
    scheduled["fault_schedule"] = json!([{"cycle": 1, "kind": "drop", "delay_periods": 0}]);
    assert!(completion(&fault, &scheduled, &control).is_ok());
    assert_eq!(
        completion(&fault, &manifest, &control).err().as_deref(),
        Some("native metadata fault schedule does not match the run declaration")
    );
    let counters = "native completion counters do not match captured events";
    for (pointer, value) in [
        ("/result/records", json!(11)),
        ("/result/overflow", json!(1)),
        ("/result/misses", json!(0)),
        ("/result/samples", json!(2)),
        ("/result/safe", json!(false)),
    ] {
        let mut changed = native.clone();
        *changed.pointer_mut(pointer).expect("pointer") = value;
        assert_eq!(
            completion(&changed, &manifest, &control).err().as_deref(),
            Some(counters)
        );
    }
    let mut cycles = control.clone();
    cycles["observed_deadlines"] = json!(2);
    assert_eq!(
        completion(&native, &manifest, &cycles).err().as_deref(),
        Some(counters)
    );
    let mut overflowed = native.clone();
    overflowed["result"]["overflow"] = json!(2);
    overflowed["result"]["misses"] = json!(0);
    let mut lossy = manifest.clone();
    lossy["instrument"]["fifo_overflow_count"] = json!(2);
    assert!(completion(&overflowed, &lossy, &control).is_ok());
    assert_eq!(
        completion(&json!({}), &manifest, &control).err().as_deref(),
        Some("native metadata (root): does not satisfy the native run schema")
    );
}

/// A valid host load receipt from the corpus for one profile.
fn receipt(profile: &str) -> Value {
    let corpus: Value = serde_json::from_str(CORPUS).expect("corpus");
    let mut receipt = corpus["bases"]["host_load"].clone();
    receipt["profile"] = json!(profile);
    receipt["started_ns"] = json!(1);
    receipt["native_started_ns"] = json!(2);
    receipt["native_finished_ns"] = json!(3);
    receipt["finished_ns"] = json!(4);
    receipt["native_pid"] = json!(2);
    receipt["counters"]["chunks"] = json!(2);
    let size = 4096;
    let counters = &mut receipt["counters"];
    match profile {
        "cpu" => counters["arithmetic_operations"] = json!(2 * 4096),
        "memory" => counters["memory_touches"] = json!(2 * size / 64),
        "network" => {
            counters["datagrams"] = json!(2);
            counters["bytes_sent"] = json!(2 * size);
            counters["bytes_received"] = json!(2 * size);
        }
        "storage" => {
            counters["fsyncs"] = json!(2);
            counters["bytes_written"] = json!(2 * size);
            counters["bytes_read"] = json!(2 * size);
        }
        _ => counters["idle_waits"] = json!(2),
    }
    receipt["network_scope"] = if profile == "network" {
        json!("loopback_udp")
    } else {
        Value::Null
    };
    receipt["storage_scope"] = if profile == "storage" {
        json!("owned_file_fsync")
    } else {
        Value::Null
    };
    receipt
}

/// The outcome of the host load check for one receipt.
fn checked(receipt: &Value) -> Result<Value, String> {
    host_load(&serde_json::to_vec(receipt).expect("JSON"))
}

#[test]
fn host_load_checks_policy_scope_bracket_and_counters() {
    for profile in ["idle", "cpu", "memory", "network", "storage"] {
        let valid = receipt(profile);
        assert_eq!(checked(&valid), Ok(valid.clone()), "{profile}");
        let mut wrong = valid.clone();
        wrong["counters"]["chunks"] = json!(3);
        assert_eq!(
            checked(&wrong).err().as_deref(),
            Some("host load counters differ from complete workload chunks"),
            "{profile}"
        );
    }
    let policy = "host load policy, scope or native time bracket differs";
    let mut changes = Vec::new();
    for (pointer, value) in [
        ("/native_pid", json!(1)),
        ("/requested_cpu", json!(1)),
        ("/started_ns", json!(3)),
        ("/native_finished_ns", json!(2)),
        ("/finished_ns", json!(2)),
        ("/network_scope", json!("loopback_udp")),
        ("/storage_scope", json!("owned_file_fsync")),
    ] {
        let mut changed = receipt("idle");
        *changed.pointer_mut(pointer).expect("pointer") = value;
        changes.push(changed);
    }
    let mut wide = receipt("network");
    wide["working_set_bytes"] = json!(65536);
    wide["counters"]["bytes_sent"] = json!(2 * 65536);
    wide["counters"]["bytes_received"] = json!(2 * 65536);
    changes.push(wide);
    for changed in &changes {
        assert_eq!(checked(changed).err().as_deref(), Some(policy), "{changed}");
    }
    assert_eq!(
        checked(&json!({})).err().as_deref(),
        Some("host load receipt (root): does not satisfy the host load schema")
    );
}
