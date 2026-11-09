// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — control_outputs, crate-internal controls

//! Edge cases of `control_outputs` that the command parity runs do not reach.

use super::{canonical_json, cell, general, jitter_pairs, plots};
use crate::control_analysis::Row;
use serde_json::{Value, json};

/// Finite values that are not negative with CPython 3.13 `format(value, ".6g")`.
const GENERAL: &[(f64, &str)] = &[
    (0.0, "0"),
    (123_456.0, "123456"),
    (999_995.0, "999995"),
    (999_999.5, "1e+06"),
    (99_999.5, "99999.5"),
    (15_000_000.0, "1.5e+07"),
    (2.5e-07, "2.5e-07"),
    (1e-05, "1e-05"),
    (0.0001, "0.0001"),
    (9.999_999_5e-05, "0.0001"),
    (0.000_123_456_78, "0.000123457"),
    (12.345_678_9, "12.3457"),
    (0.300_000_000_000_000_04, "0.3"),
    (100.0, "100"),
    (1e+16, "1e+16"),
    (5e-324, "4.94066e-324"),
    (f64::MAX, "1.79769e+308"),
];

#[test]
fn general_format_matches_python() {
    for &(value, expected) in GENERAL {
        assert_eq!(general(value), expected, "{value:e}");
    }
}

#[test]
fn canonical_json_matches_python() {
    let value = json!({
        "flag": false, "on": true, "none": null, "empty_list": [], "empty_map": {},
        "list": [1, 2.5, "x"],
        "text": "q\"b\\s\nn\rr\tt\u{8}b\u{c}f\u{1}\u{7f}\u{e9}\u{2028}",
        "big": 1e16, "small": 2.5e-7, "nested": {"a": [{}]},
    });
    let expected = "{\n  \"big\": 1e+16,\n  \"empty_list\": [],\n  \"empty_map\": {},\n  \
                    \"flag\": false,\n  \"list\": [\n    1,\n    2.5,\n    \"x\"\n  ],\n  \
                    \"nested\": {\n    \"a\": [\n      {}\n    ]\n  },\n  \"none\": null,\n  \
                    \"on\": true,\n  \"small\": 2.5e-07,\n  \
                    \"text\": \"q\\\"b\\\\s\\nn\\rr\\tt\\bb\\ff\\u0001\u{7f}\u{e9}\u{2028}\"\n}\n";
    assert_eq!(
        String::from_utf8(canonical_json(&value)),
        Ok(expected.to_owned())
    );
}

#[test]
fn cells_are_python_str_of_their_value() {
    assert_eq!(cell(None), "");
    assert_eq!(cell(Some(&Value::Null)), "");
    assert_eq!(cell(Some(&json!("a,b"))), "a,b");
    assert_eq!(cell(Some(&json!(7))), "7");
    assert_eq!(cell(Some(&json!(0.1))), "0.1");
    assert_eq!(cell(Some(&json!(1e16))), "1e+16");
}

/// One interval row.
fn row(cycle: u32, interval: &str, ticks: u64) -> Row {
    Row {
        cycle,
        interval: interval.to_owned(),
        ticks,
    }
}

#[test]
fn jitter_pairs_join_only_adjacent_cycles_of_one_interval() {
    let rows = [
        row(0, "a", 10),
        row(0, "b", 5),
        row(1, "a", 7),
        row(2, "b", 6),
        row(3, "a", u64::MAX),
        row(4, "a", 0),
    ];
    let pairs: Vec<Value> = jitter_pairs(&rows).into_iter().map(Value::Object).collect();
    assert_eq!(
        pairs,
        [
            json!({"interval": "a", "previous_cycle": 0, "cycle": 1, "previous_ticks": 10,
                   "ticks": 7, "delta_ticks": "-3", "absolute_delta_ticks": "3"}),
            json!({"interval": "a", "previous_cycle": 3, "cycle": 4,
                   "previous_ticks": u64::MAX, "ticks": 0,
                   "delta_ticks": "-18446744073709551615",
                   "absolute_delta_ticks": "18446744073709551615"}),
        ]
    );
}

#[test]
fn an_unavailable_energy_series_has_no_energy_plot() {
    let report = json!({
        "evidence_status": "simulation",
        "events": {
            "intervals": {"a": {"p99_ticks": 4}, "b": {"p99_ticks": null}},
            "jitter": {"a": {"p99_ticks": 0}},
        },
        "energy": {"status": "unavailable"},
    });
    let files = plots(&report);
    let names: Vec<&str> = files.iter().map(|(name, _)| name.as_str()).collect();
    assert_eq!(names, ["interval_p99.svg", "jitter_p99.svg"]);
    let interval = String::from_utf8(files[0].1.clone()).expect("UTF-8 plot");
    assert!(interval.contains(">a</text>") && !interval.contains(">b</text>"));
}
