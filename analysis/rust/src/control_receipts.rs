// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — native completion and host load receipts of a control run

//! Native completion counters and host load receipts, as Python's
//! `native_completion` and `host_load_receipt` validate them.
//!
//! Both receipts are bounded JSON documents checked against their committed
//! schemas, then against the run declaration and the captured events. Values
//! are compared as Python's `==` compares them: integers and floats by value,
//! `True` equal to 1 and `False` to 0.

use crate::control_json::decode_object;
use crate::control_number::Num;
use crate::control_schema::Schema;
use serde_json::{Map, Value, json};
use std::cmp::Ordering;
use std::collections::BTreeMap;
use std::sync::LazyLock;

/// The committed native-run metadata schema.
static NATIVE_SCHEMA: LazyLock<Schema> = LazyLock::new(|| {
    Schema::load(include_str!("../native-run.schema.json")).expect("committed schema")
});
/// The committed host load receipt schema.
static HOST_LOAD_SCHEMA: LazyLock<Schema> = LazyLock::new(|| {
    Schema::load(include_str!("../host-load.schema.json")).expect("committed schema")
});
/// Largest loopback datagram a network load may declare, in bytes.
const MAX_DATAGRAM_BYTES: u128 = 60_000;

/// A JSON scalar as Python compares it: an exact integer, or a float.
#[derive(Clone, Copy)]
enum Scalar {
    /// A Python `int`, booleans as 0 or 1.
    Int(i128),
    /// A Python `float`.
    Float(f64),
}

/// A JSON scalar as a Python number: numbers of either sign, and booleans as 0 or 1.
fn numeric(value: &Value) -> Option<Scalar> {
    match value {
        Value::Number(number) => Some(
            number
                .as_i64()
                .map(i128::from)
                .or_else(|| number.as_u64().map(i128::from))
                .map_or_else(
                    || Scalar::Float(number.as_f64().expect("finite decoded number")),
                    Scalar::Int,
                ),
        ),
        Value::Bool(flag) => Some(Scalar::Int(i128::from(*flag))),
        _ => None,
    }
}

/// Python's `==` between two numbers: exact across `int` and `float`.
///
/// An integer equals a float only when the float holds exactly its value: the
/// integer converts to that float and the float converts back to the integer.
fn same_number(left: Scalar, right: Scalar) -> bool {
    match (left, right) {
        (Scalar::Int(left), Scalar::Int(right)) => left == right,
        (Scalar::Float(left), Scalar::Float(right)) => left == right,
        (Scalar::Int(integer), Scalar::Float(float))
        | (Scalar::Float(float), Scalar::Int(integer)) => {
            integer as f64 == float && float as i128 == integer
        }
    }
}

/// Python's `==` between two decoded JSON values.
pub(crate) fn python_equal(left: &Value, right: &Value) -> bool {
    match (left, right) {
        (Value::Array(left), Value::Array(right)) => {
            left.len() == right.len()
                && left
                    .iter()
                    .zip(right)
                    .all(|(left, right)| python_equal(left, right))
        }
        (Value::Object(left), Value::Object(right)) => {
            left.len() == right.len()
                && left.iter().all(|(key, value)| {
                    right
                        .get(key)
                        .is_some_and(|other| python_equal(value, other))
                })
        }
        _ => match (numeric(left), numeric(right)) {
            (Some(left), Some(right)) => same_number(left, right),
            _ => left == right,
        },
    }
}

/// Decode a bounded receipt and refuse it at its first failing schema location.
fn receipt(content: &[u8], source: &str, schema: &Schema, name: &str) -> Result<Value, String> {
    let (document, _) = decode_object(content, source)?;
    let document = Value::Object(document);
    match schema.locations(&document).first() {
        Some(location) => Err(format!(
            "{source} {location}: does not satisfy the {name} schema"
        )),
        None => Ok(document),
    }
}

/// Decode the native metadata, as Python's `parse_bounded_json_object` does.
pub(crate) fn native_metadata(content: &[u8]) -> Result<Value, String> {
    Ok(Value::Object(decode_object(content, "native metadata")?.0))
}

/// Validate the native completion facts against the run and its complete
/// captured events, as Python's `completion_statistics`; returns the
/// receipt's `result` counters.
pub(crate) fn completion_statistics(
    content: &[u8],
    manifest: &Map<String, Value>,
    event_count: usize,
    control: &Value,
    sample_reads: usize,
) -> Result<Value, String> {
    let native = receipt(content, "native metadata", &NATIVE_SCHEMA, "native run")?;
    let fault = &native["fault"];
    let kind = fault["kind"].as_str().expect("schema-checked kind");
    let schedule = if kind == "none" {
        json!([])
    } else {
        let delay = if kind == "delay" {
            fault["duration_periods"].clone()
        } else {
            json!(0)
        };
        json!([{"cycle": fault["cycle"], "kind": kind, "delay_periods": delay}])
    };
    if !python_equal(&schedule, &manifest["fault_schedule"]) {
        return Err("native metadata fault schedule does not match the run declaration".to_owned());
    }
    let artifacts = &native["artifacts"];
    let thermal = manifest["plant"]["name"] == "first_order_thermal";
    let differs = native["source_kind"] != "rtl_simulation"
        || manifest["source"]["kind"] != "rtl_simulation"
        || !python_equal(&native["cycles"], &manifest["cycle_count"])
        || !python_equal(&native["period_ticks"], &manifest["sample_period_ticks"])
        || native["controller"] != manifest["controller"]["name"]
        || !python_equal(
            &native["coefficients"],
            &manifest["controller"]["coefficients"],
        )
        || native["thermal"] != thermal
        || Num::of(&native["result"]["samples"]).compare(Num::of(&native["cycles"]))
            == Ordering::Greater
        || artifacts["events"]["sha256"] != manifest["files"]["events"]["sha256"]
        || !python_equal(&artifacts["events"]["bytes"], &json!(event_count * 16))
        || !manifest["source"]["files"]
            .as_array()
            .expect("schema-checked array")
            .iter()
            .any(|reference| reference["sha256"] == artifacts["configuration"]["sha256"]);
    if differs {
        return Err("native metadata configuration does not match the run declaration".to_owned());
    }
    let result = &native["result"];
    let complete = !Num::of(&result["overflow"]).truthy();
    let counters_differ = !python_equal(&result["records"], &json!(event_count))
        || !python_equal(
            &result["overflow"],
            &manifest["instrument"]["fifo_overflow_count"],
        )
        || (complete
            && (!python_equal(&result["misses"], &control["deadline_misses"])
                || !python_equal(&native["cycles"], &control["observed_deadlines"])
                || !python_equal(&result["samples"], &json!(sample_reads))
                || result["safe"] != Num::of(&control["safe_state_events"]).truthy()));
    if counters_differ {
        return Err("native completion counters do not match captured events".to_owned());
    }
    Ok(result.clone())
}

/// Validate a completed host load receipt and its native execution bracket,
/// as Python's `validate_host_load`.
pub(crate) fn host_load(content: &[u8]) -> Result<Value, String> {
    let receipt = receipt(content, "host load receipt", &HOST_LOAD_SCHEMA, "host load")?;
    let profile = receipt["profile"].as_str().expect("schema-checked profile");
    let size = Num::of(&receipt["working_set_bytes"]);
    let time = |name: &str| Num::of(&receipt[name]);
    let ordered =
        |first: &str, second: &str, order: Ordering| time(first).compare(time(second)) != order;
    let scope = |wanted: &str, value: &str| {
        if profile == wanted {
            json!(value)
        } else {
            Value::Null
        }
    };
    let differs = python_equal(&receipt["worker_pid"], &receipt["native_pid"])
        || !python_equal(
            &receipt["policy"]["affinity_cpus"],
            &json!([receipt["requested_cpu"]]),
        )
        || !(ordered("started_ns", "native_started_ns", Ordering::Greater)
            && time("native_started_ns").compare(time("native_finished_ns")) == Ordering::Less
            && ordered("native_finished_ns", "finished_ns", Ordering::Greater))
        || receipt["network_scope"] != scope("network", "loopback_udp")
        || receipt["storage_scope"] != scope("storage", "owned_file_fsync")
        || (profile == "network"
            && size.compare(Num::Int(MAX_DATAGRAM_BYTES)) == Ordering::Greater);
    if differs {
        return Err("host load policy, scope or native time bracket differs".to_owned());
    }
    let counters = receipt["counters"]
        .as_object()
        .expect("schema-checked counters");
    let chunks = Num::of(&counters["chunks"]);
    let mut expected: BTreeMap<&str, Num> = BTreeMap::from([("chunks", chunks)]);
    match profile {
        "cpu" => {
            expected.insert("arithmetic_operations", chunks.mul(Num::Int(4096)));
        }
        "memory" => {
            expected.insert("memory_touches", chunks.mul(lines(size)));
        }
        "network" => expected.extend([
            ("datagrams", chunks),
            ("bytes_sent", chunks.mul(size)),
            ("bytes_received", chunks.mul(size)),
        ]),
        "storage" => expected.extend([
            ("fsyncs", chunks),
            ("bytes_written", chunks.mul(size)),
            ("bytes_read", chunks.mul(size)),
        ]),
        _ => {
            expected.insert("idle_waits", chunks);
        }
    }
    // The schema requires every counter, so only the values can differ.
    let matches = counters.iter().all(|(name, value)| {
        Num::of(value).same(expected.get(name.as_str()).copied().unwrap_or(Num::Int(0)))
    });
    if !matches {
        return Err("host load counters differ from complete workload chunks".to_owned());
    }
    Ok(receipt)
}

/// Python's `(size + 63) // 64` for a schema-bounded working-set size.
fn lines(size: Num) -> Num {
    match size {
        Num::Int(bytes) => Num::Int(bytes.div_ceil(64)),
        Num::Float(bytes) => Num::Float(((bytes + 63.0) / 64.0).floor()),
    }
}

#[cfg(test)]
#[path = "../tests/unit/control_receipts.rs"]
mod tests;
