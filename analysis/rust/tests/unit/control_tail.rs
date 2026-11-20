// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — tail quantile and weakly-hard metric unit tests

use super::*;
use serde_json::json;

#[test]
fn splitmix64_reproduces_the_published_sequence() {
    let mut generator = SplitMix64 { state: 0 };
    let outputs: Vec<u64> = (0..3).map(|_| generator.next()).collect();
    assert_eq!(
        outputs,
        [
            0xE220_A839_7B1D_CDAF,
            0x6E78_9E6A_A1B9_65F4,
            0x06C4_5D18_8009_454F
        ]
    );
}

#[test]
fn block_length_is_the_integer_fourth_root_ceiling() {
    let lengths: Vec<usize> = [1, 2, 16, 17, 81, 82, 64_000].map(block_length).to_vec();
    assert_eq!(lengths, [1, 2, 2, 3, 3, 4, 16]);
}

#[test]
fn short_series_keep_estimates_without_intervals() {
    let result = tail_quantiles(&[5, 3, 4]);
    assert_eq!(result["resamples"], 0);
    assert_eq!(result["block_length"], 2);
    assert_eq!(
        result["quantiles"]["p95_ticks"],
        json!({"estimate": 4.9, "reportable": false, "lower": null, "upper": null})
    );
    let empty = tail_quantiles(&[]);
    assert_eq!(empty["block_length"], 0);
    assert_eq!(empty["quantiles"]["p999_ticks"]["estimate"], Value::Null);
}

#[test]
fn reportable_quantiles_follow_the_minimum_sample_rule() {
    let values: Vec<u64> = (0..1_000).map(|index| 100 + (index * 37) % 101).collect();
    let result = tail_quantiles(&values);
    assert_eq!(result["resamples"], RESAMPLES);
    let quantiles = &result["quantiles"];
    for name in ["p95_ticks", "p99_ticks"] {
        assert_eq!(quantiles[name]["reportable"], true);
        let (lower, upper) = (
            quantiles[name]["lower"].as_f64().expect("lower"),
            quantiles[name]["upper"].as_f64().expect("upper"),
        );
        let estimate = quantiles[name]["estimate"].as_f64().expect("estimate");
        assert!(lower <= estimate && estimate <= upper, "{name}");
    }
    assert_eq!(quantiles["p999_ticks"]["reportable"], false);
    assert_eq!(quantiles["p999_ticks"]["lower"], Value::Null);
}

#[test]
fn weakly_hard_windows_count_the_largest_miss_cluster() {
    let misses = [
        false, true, true, false, true, false, false, false, false, false, true,
    ];
    assert_eq!(
        weakly_hard(&misses),
        json!({
            "observed_deadlines": 11,
            "longest_miss_run": 2,
            "maximum_misses_in_window": {
                "2": 2, "3": 2, "5": 3, "10": 4, "20": null, "50": null, "100": null, "1000": null
            }
        })
    );
    assert_eq!(weakly_hard(&[])["longest_miss_run"], 0);
}

/// The shared corpus of interval series and miss sequences with Python's results.
const CORPUS: &str = include_str!("../data/control-tail-cases.json");

#[test]
fn every_corpus_case_has_the_python_result() {
    let (corpus, _) =
        crate::control_json::decode_object(CORPUS.as_bytes(), "corpus").expect("corpus");
    let tails = corpus["tail_cases"].as_array().expect("tail cases");
    assert_eq!(tails.len(), 6);
    for case in tails {
        let values: Vec<u64> = case["values"]
            .as_array()
            .expect("values")
            .iter()
            .map(|value| value.as_u64().expect("ticks"))
            .collect();
        assert_eq!(tail_quantiles(&values), case["result"], "{}", case["name"]);
    }
    let windows = corpus["weakly_hard_cases"]
        .as_array()
        .expect("weakly-hard cases");
    assert_eq!(windows.len(), 3);
    for case in windows {
        let misses: Vec<bool> = case["misses"]
            .as_array()
            .expect("misses")
            .iter()
            .map(|flag| flag.as_bool().expect("flag"))
            .collect();
        assert_eq!(weakly_hard(&misses), case["result"], "{}", case["name"]);
    }
}
