// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — Python decimal arithmetic, crate-internal controls

//! Hold measurement parsing and decimal arithmetic to Python for the shared corpus.
//!
//! `tests/test_control_series_corpus.py` writes Python's values, refusals and
//! exact operation results; these tests require the same here.

use super::{Big, Decimal, count, measurement};
use crate::control_json::decode_object;
use serde_json::Value;
use std::cmp::Ordering;

/// The shared corpus of decimal cases and series.
const CORPUS: &str = include_str!("../data/control-series-cases.json");

/// The exact value of a corpus `[negative, digits, exponent]` triple.
fn value(triple: &Value) -> Decimal {
    Decimal::new(
        triple[0].as_bool().expect("sign"),
        Big::digits(triple[1].as_str().expect("digits")),
        triple[2].as_i64().expect("exponent"),
    )
}

/// A corpus cell: text, or a long run of one character written as
/// `{prefix, repeat, count, suffix}`.
fn cell_text(cell: &Value) -> String {
    match cell {
        Value::String(text) => text.clone(),
        packed => format!(
            "{}{}{}",
            packed["prefix"].as_str().expect("prefix"),
            packed["repeat"]
                .as_str()
                .expect("repeat")
                .repeat(usize::try_from(packed["count"].as_u64().expect("count")).expect("count")),
            packed["suffix"].as_str().expect("suffix")
        ),
    }
}

/// The decimal section of the corpus.
fn decimal() -> Value {
    let (corpus, _) = decode_object(CORPUS.as_bytes(), "corpus").expect("corpus");
    corpus["decimal"].clone()
}

#[test]
fn every_measurement_cell_has_the_python_value_or_refusal() {
    let decimal = decimal();
    let cases = decimal["measurements"].as_array().expect("measurements");
    assert!(cases.len() > 80);
    for case in cases {
        let cell = cell_text(&case["cell"]);
        match measurement(&cell, "value") {
            Ok(parsed) => assert!(parsed == value(&case["value"]), "{cell}"),
            Err(refusal) => assert_eq!(refusal, case["refusal"], "{cell}"),
        }
    }
}

#[test]
fn every_count_cell_has_the_python_value_or_refusal() {
    for case in decimal()["counts"].as_array().expect("counts") {
        let cell = case["cell"].as_str().expect("cell");
        match count(cell, "cycle") {
            Ok(parsed) => assert_eq!(Some(parsed), case["value"].as_u64(), "{cell}"),
            Err(refusal) => assert_eq!(refusal, case["refusal"], "{cell}"),
        }
    }
}

#[test]
fn every_operation_has_the_python_result() {
    let decimal = decimal();
    let cases = decimal["operations"].as_array().expect("operations");
    assert!(cases.len() > 40);
    for case in cases {
        let (left, right) = (value(&case["left"]), value(&case["right"]));
        let divisor = case["divisor"].as_u64().expect("divisor");
        assert!(left.add(&right) == value(&case["sum"]), "{case}");
        assert!(left.sub(&right) == value(&case["difference"]), "{case}");
        assert!(left.mul(&right) == value(&case["product"]), "{case}");
        let quotient = left.abs().divide(divisor);
        assert!(quotient == value(&case["quotient"]), "{case}");
        assert_eq!(
            quotient.float().to_bits(),
            case["float"].as_f64().expect("float").to_bits(),
            "{case}"
        );
    }
}

#[test]
fn every_division_has_the_python_quotient() {
    let divisions = decimal()["divisions"].clone();
    for case in divisions.as_array().expect("divisions") {
        let quotient = value(&case[0]).divide(case[1].as_u64().expect("divisor"));
        assert!(quotient == value(&case[2]), "{case}");
        assert_eq!(
            quotient.float().to_bits(),
            case[3].as_f64().expect("float").to_bits()
        );
    }
}

#[test]
fn rounding_ties_go_to_the_even_neighbour() {
    let digits = |text: &str| Decimal::new(false, Big::digits(text), 0);
    let half = Decimal::new(false, Big::digits("5"), -1);
    let even = digits("1234567890123456789012345678").add(&half);
    assert!(even == digits("1234567890123456789012345678"));
    let odd = digits("1234567890123456789012345677").add(&half);
    assert!(odd == digits("1234567890123456789012345678"));
    assert!(Decimal::new(false, Big::small(1), 0).divide(2) == half);
    assert!(Decimal::zero().divide(7) == Decimal::zero());
    assert!(digits("2").divide(3) > digits("0"));
    assert_eq!(
        digits("1").cmp(&digits("1").sub(&digits("2"))),
        Ordering::Greater
    );
    assert_eq!(
        digits("1").sub(&digits("2")).cmp(&digits("1")),
        Ordering::Less
    );
    let minus = |text: &str| Decimal::new(true, Big::digits(text), 0);
    assert_eq!(minus("2").cmp(&minus("1")), Ordering::Less);
    assert!(minus("2").is_negative() && !Decimal::zero().is_negative());
    assert_eq!(Decimal::zero().float().to_bits(), 0.0_f64.to_bits());
    assert_eq!(Big::small(0), Big::zero());
    assert_eq!(
        Big::small(999_999_999).add(&Big::small(1)),
        Big::small(1_000_000_000)
    );
    assert_eq!(Big::small(4_000_000_000).digit_count(), 10);
    assert!(Big::small(10).partial_cmp(&Big::small(9)) == Some(Ordering::Greater));
    assert!(
        Decimal::new(false, Big::small(3), 0).partial_cmp(&Decimal::new(false, Big::small(3), 0))
            == Some(Ordering::Equal)
    );
}
