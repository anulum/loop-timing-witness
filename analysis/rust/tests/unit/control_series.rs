// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — tracking and energy series, crate-internal controls

//! Hold the tracking and energy series to Python for the shared corpus.
//!
//! `tests/test_control_series_corpus.py` writes Python's metrics and refusals;
//! these tests require the same results here, with bit-equal floats.

use super::{energy_per_cycle, observed_tracking_error, python_sum, tracking_error};
use crate::control_events::{Event, Names};
use crate::control_json::decode_object;
use serde_json::{Map, Value};

/// The shared corpus of decimal cases and series.
const CORPUS: &str = include_str!("../data/control-series-cases.json");
/// The repository's measurement domain, through its checked crate copy, for event codes.
const DOMAIN: &str = include_str!("../data/measurement-domain.json");

/// Series bytes of a case: UTF-8 text, or `{"hex": …}` for bytes that are not UTF-8.
fn content(case: &Value) -> Option<Vec<u8>> {
    match &case["content"] {
        Value::String(text) => Some(text.clone().into_bytes()),
        Value::Object(map) => Some(
            map["hex"]
                .as_str()
                .expect("hex")
                .as_bytes()
                .chunks(2)
                .map(|pair| {
                    u8::from_str_radix(std::str::from_utf8(pair).expect("hex"), 16).expect("hex")
                })
                .collect(),
        ),
        _ => None,
    }
}

/// Decoded events of a case.
fn events(case: &Value, contracts: &Value) -> Vec<Event> {
    let codes = contracts["event_codes"].as_object().expect("codes");
    case["events"]
        .as_array()
        .map(Vec::as_slice)
        .unwrap_or_default()
        .iter()
        .map(|event| Event {
            code: u8::try_from(
                codes[event[0].as_str().expect("name")]
                    .as_u64()
                    .expect("code"),
            )
            .expect("byte"),
            cycle: u32::try_from(event[1].as_u64().expect("cycle")).expect("cycle"),
            ticks: event[2].as_u64().expect("ticks"),
        })
        .collect()
}

#[test]
fn every_series_case_has_the_python_result() {
    let (corpus, _) = decode_object(CORPUS.as_bytes(), "corpus").expect("corpus");
    let (domain, _) = decode_object(DOMAIN.as_bytes(), "domain").expect("domain");
    let contracts = &domain["design_contracts"];
    let names = Names::of(contracts);
    let rails: Vec<&str> = corpus["rails"]
        .as_array()
        .expect("rails")
        .iter()
        .map(|rail| rail.as_str().expect("rail"))
        .collect();
    let cases = corpus["cases"].as_array().expect("cases");
    assert!(cases.len() > 80);
    for case in cases {
        let bytes = content(case);
        let events = events(case, contracts);
        let warmup = case["warmup_cycles"].as_u64().expect("warm-up");
        let outcome: Result<Map<String, Value>, String> = match case["kind"].as_str() {
            Some("tracking") => tracking_error(
                bytes.as_deref(),
                case["cycle_count"].as_u64().expect("cycles"),
                warmup,
                "rad",
            ),
            Some("observed") => observed_tracking_error(
                &bytes.expect("observed content"),
                &events,
                &names,
                case["cycle_count"].as_u64().expect("cycles"),
                warmup,
                "rad",
            ),
            _ => energy_per_cycle(
                bytes.as_deref(),
                &events,
                &names,
                case["profile"].as_str().expect("profile"),
                warmup,
                &rails,
            ),
        };
        match case.get("refusal") {
            Some(refusal) => assert_eq!(outcome.err().as_deref(), refusal.as_str(), "{case}"),
            None => assert_eq!(
                Value::Object(outcome.expect("result")),
                case["result"],
                "{case}"
            ),
        }
    }
}

#[test]
fn float_sums_follow_python() {
    assert_eq!(python_sum(&[]).to_bits(), 0.0_f64.to_bits());
    assert_eq!(python_sum(&[0.1, 0.2, 0.3]), 0.6);
    assert_eq!(python_sum(&[1e100, 1.0, -1e100]), 1.0);
    assert_eq!(python_sum(&[1.0, 1e100, 1.0, -1e100]), 2.0);
    assert!(python_sum(&[f64::MAX, f64::MAX]).is_infinite());
}
