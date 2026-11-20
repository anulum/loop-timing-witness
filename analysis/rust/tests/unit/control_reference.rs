// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — pulse-per-second timebase unit tests

use super::*;

/// The shared corpus of edge series with Python's blocks.
const CORPUS: &str = include_str!("../data/control-reference-cases.json");

/// One edge of the PPS code.
fn pulse(sequence: u32, ticks: u64) -> Edge {
    Edge {
        code: 18,
        sequence,
        ticks,
    }
}

#[test]
fn no_pulse_gives_no_block_and_one_pulse_no_fit() {
    assert_eq!(reference_timebase(&[], 1e8), Value::Null);
    let block = reference_timebase(&[pulse(3, 900)], 1e8);
    assert_eq!(block["edges"], 1);
    assert_eq!(block["first_sequence"], 3);
    assert_eq!(block["missing_edges"], 0);
    assert_eq!(block["ticks_per_second"], Value::Null);
    assert_eq!(block["max_abs_residual_ticks"], Value::Null);
}

#[test]
fn an_exact_fast_counter_is_half_a_part_per_million_fast() {
    let pulses: Vec<Edge> = (0..60)
        .map(|second| pulse(second, 1000 + u64::from(second) * 100_000_050))
        .collect();
    let block = reference_timebase(&pulses, 1e8);
    assert_eq!(block["ticks_per_second"], 100_000_050.0);
    assert_eq!(block["scale_error_ppm"], 0.5);
    assert_eq!(block["scale_standard_error_ppm"], 0.0);
    assert_eq!(block["residual_rms_ticks"], 0.0);
}

#[test]
fn every_corpus_case_has_the_python_result() {
    let (corpus, _) =
        crate::control_json::decode_object(CORPUS.as_bytes(), "corpus").expect("corpus");
    let clock = corpus["clock_hz"].as_f64().expect("clock");
    let cases = corpus["cases"].as_array().expect("cases");
    assert_eq!(cases.len(), 7);
    for case in cases {
        let pulses: Vec<Edge> = case["edges"]
            .as_array()
            .expect("edges")
            .iter()
            .filter(|edge| edge[0] == "PPS")
            .map(|edge| {
                let sequence = edge[1].as_u64().expect("sequence");
                pulse(
                    u32::try_from(sequence).expect("sequence width"),
                    edge[2].as_u64().expect("ticks"),
                )
            })
            .collect();
        assert_eq!(
            reference_timebase(&pulses, clock),
            case["result"],
            "{}",
            case["name"]
        );
    }
}
