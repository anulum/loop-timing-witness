// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — events-block statistics, crate-internal controls

//! Hold the events block to Python's `events_block` for the shared corpus.
//!
//! `tests/test_control_events_corpus.py` builds the corpus from Python and
//! requires the committed file to equal it; these tests require the same
//! blocks, interval rows and refusals here. The corpus is decoded with the
//! crate's own decoder, whose floats are correctly rounded as Python's are.

use super::{Row, events_block};
use crate::control_events::Event;
use crate::control_json::decode_object;
use serde_json::{Value, json};

/// The shared corpus of runs, events and Python's events blocks.
const CORPUS: &str = include_str!("../data/control-events-blocks.json");

#[test]
fn every_corpus_run_has_the_python_events_block() {
    let (corpus, _) = decode_object(CORPUS.as_bytes(), "corpus").expect("corpus");
    let contracts = &corpus["contracts"];
    let codes = contracts["event_codes"].as_object().expect("codes");
    let cases = corpus["cases"].as_array().expect("cases");
    assert!(cases.len() > 15);
    for case in cases {
        let events: Vec<Event> = case["events"]
            .as_array()
            .expect("events")
            .iter()
            .map(|event| Event {
                code: u8::try_from(
                    codes[event[0].as_str().expect("name")]
                        .as_u64()
                        .expect("code"),
                )
                .expect("byte code"),
                cycle: u32::try_from(event[1].as_u64().expect("cycle")).expect("cycle"),
                ticks: event[2].as_u64().expect("ticks"),
            })
            .collect();
        let manifest = case["run"].as_object().expect("run");
        let outcome = events_block(manifest, contracts, &events);
        match case.get("refusal") {
            Some(refusal) => assert_eq!(
                outcome.err().as_deref(),
                refusal.as_str(),
                "{}",
                case["name"]
            ),
            None => {
                let (block, rows) = outcome.expect("events block");
                assert_eq!(block, case["block"], "{}", case["name"]);
                let rows: Vec<Value> = rows
                    .iter()
                    .map(
                        |Row {
                             cycle,
                             interval,
                             ticks,
                         }| json!([cycle, interval, ticks]),
                    )
                    .collect();
                assert_eq!(Value::Array(rows), case["rows"], "{}", case["name"]);
            }
        }
    }
}
