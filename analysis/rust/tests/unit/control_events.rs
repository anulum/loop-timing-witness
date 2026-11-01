// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — fabric event records, crate-internal controls

//! Refuse every malformed record with the Python decoder's text and order.

use super::{Event, Names, decode};
use crate::control_number::Num;
use serde_json::{Value, json};

/// A measurement domain's contracts with two profiles and float and integer codes.
fn contracts() -> Value {
    json!({
        "event_codes": {"SAMPLE_READY": 1, "DEADLINE": 4.0, "INPUT_WRITE": 8},
        "event_profiles": {
            "CONTROL": {"periodic_events": ["SAMPLE_READY"], "occasional_events": ["DEADLINE"]},
            "COMPUTE": {"periodic_events": ["INPUT_WRITE"], "occasional_events": []}
        }
    })
}

/// One record.
fn record(code: u8, reserved: [u8; 3], cycle: u32, ticks: u64) -> Vec<u8> {
    let mut bytes = vec![code];
    bytes.extend(reserved);
    bytes.extend(cycle.to_le_bytes());
    bytes.extend(ticks.to_le_bytes());
    bytes
}

/// Decode records as a CONTROL run of three cycles.
fn control(records: &[Vec<u8>]) -> Result<Vec<Event>, String> {
    decode(&records.concat(), &contracts(), "CONTROL", Num::Float(3.0))
}

#[test]
fn valid_records_decode_with_float_codes() {
    let events = control(&[
        record(1, [0; 3], 0, 10),
        record(4, [0; 3], 0, 20),
        record(1, [0; 3], 2, 20),
    ])
    .expect("valid records");
    assert_eq!(events.len(), 3);
    assert_eq!(
        events[1],
        Event {
            code: 4,
            cycle: 0,
            ticks: 20
        }
    );
    assert_eq!(Names::of(&contracts()).get(4), Some("DEADLINE"));
    assert_eq!(Names::of(&contracts()).get(9), None);
}

#[test]
fn malformed_files_and_records_are_refused_in_order() {
    let base = record(1, [0; 3], 0, 10);
    assert_eq!(
        decode(&base[..15], &contracts(), "CONTROL", Num::Int(3))
            .err()
            .as_deref(),
        Some("event file is not a whole number of 16-byte records")
    );
    assert_eq!(
        decode(&[], &contracts(), "CONTROL", Num::Int(3))
            .err()
            .as_deref(),
        Some("event file is empty")
    );
    for (records, refusal) in [
        (
            vec![record(1, [0, 1, 0], 0, 1)],
            "event record 0: reserved bits must be zero",
        ),
        (
            vec![record(1, [1, 0, 0], 0, 1)],
            "event record 0: reserved bits must be zero",
        ),
        (
            vec![base.clone(), record(8, [0; 3], 0, 11)],
            "event record 1: code 8 is not in CONTROL",
        ),
        (
            vec![record(9, [0; 3], 0, 1)],
            "event record 0: code 9 is not in CONTROL",
        ),
        (
            vec![record(1, [0; 3], 3, 1)],
            "event record 0: cycle is outside the run",
        ),
        (
            vec![base.clone(), record(4, [0; 3], 0, 9)],
            "event record 1: order is not monotonic",
        ),
        (
            vec![record(1, [0; 3], 1, 10), record(4, [0; 3], 0, 11)],
            "event record 1: order is not monotonic",
        ),
        (
            vec![base.clone(), record(1, [0; 3], 0, 10)],
            "event record 1: duplicate SAMPLE_READY in cycle 0",
        ),
    ] {
        assert_eq!(
            control(&records).err().as_deref(),
            Some(refusal),
            "{refusal}"
        );
    }
}
