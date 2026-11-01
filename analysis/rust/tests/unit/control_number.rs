// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — Python numbers, crate-internal controls

//! Compare float text with CPython 3.13 `repr` and arithmetic with Python's rules.

use super::{Num, python_float, python_number};
use serde_json::json;
use std::cmp::Ordering;

/// Floats with their CPython 3.13 `repr`.
const PYTHON_REPR: &[(f64, &str)] = &[
    (1000000000000000.0_f64, "1000000000000000.0"),
    (1e+16_f64, "1e+16"),
    (1.5e+16_f64, "1.5e+16"),
    (0.0001_f64, "0.0001"),
    (1e-05_f64, "1e-05"),
    (1.5e-05_f64, "1.5e-05"),
    (123.0_f64, "123.0"),
    (-0.0_f64, "-0.0"),
    (0.0_f64, "0.0"),
    (5e-324_f64, "5e-324"),
    (1.7976931348623157e+308_f64, "1.7976931348623157e+308"),
    (0.1_f64, "0.1"),
    (1e+22_f64, "1e+22"),
    (1.2345678901234568e+16_f64, "1.2345678901234568e+16"),
    (-2.5_f64, "-2.5"),
    (100.0_f64, "100.0"),
    (1e+300_f64, "1e+300"),
    (1.8446744073709552e+19_f64, "1.8446744073709552e+19"),
    (0.30000000000000004_f64, "0.30000000000000004"),
    (-1e-07_f64, "-1e-07"),
    (999999999999999.9_f64, "999999999999999.9"),
    (0.00030000000000000003_f64, "0.00030000000000000003"),
];

#[test]
fn floats_print_as_python_repr() {
    for &(value, expected) in PYTHON_REPR {
        assert_eq!(python_float(value), expected);
    }
}

#[test]
fn decoded_numbers_print_as_python_str() {
    assert_eq!(python_number(&json!(-3)), "-3");
    assert_eq!(
        python_number(&json!(18_446_744_073_709_551_615_u64)),
        "18446744073709551615"
    );
    assert_eq!(python_number(&json!(16.0)), "16.0");
    assert_eq!(Num::Int(7).to_string(), "7");
    assert_eq!(Num::Float(1e16).to_string(), "1e+16");
}

#[test]
fn arithmetic_keeps_python_types() {
    let (four, half) = (Num::of(&json!(4)), Num::of(&json!(0.5)));
    assert_eq!(four.add(Num::Int(1)), Num::Int(5));
    assert_eq!(four.add(half), Num::Float(4.5));
    assert_eq!(half.mul(four), Num::Float(2.0));
    assert_eq!(
        four.mul(Num::Int(u128::from(u64::MAX))),
        Num::Int(4 * u128::from(u64::MAX))
    );
    assert_eq!(Num::Int(64).power_of_two(), Num::Int(1 << 64));
    assert_eq!(
        Num::Float(64.0).power_of_two(),
        Num::Float(18_446_744_073_709_551_616.0)
    );
}

#[test]
fn comparisons_are_exact_between_kinds() {
    assert!(Num::Float(16.0).same(Num::Int(16)));
    assert!(!Num::Float(16.5).same(Num::Int(16)));
    assert_eq!(Num::Float(16.5).compare(Num::Int(16)), Ordering::Greater);
    assert_eq!(Num::Int(17).compare(Num::Float(16.5)), Ordering::Greater);
    assert_eq!(Num::Float(15.5).compare(Num::Int(16)), Ordering::Less);
    assert_eq!(
        Num::Float(1e300).compare(Num::Int(u128::MAX)),
        Ordering::Greater
    );
    assert_eq!(Num::Float(0.25).compare(Num::Float(0.5)), Ordering::Less);
    assert_eq!(
        Num::Int(9_007_199_254_740_993).compare(Num::Float(9_007_199_254_740_992.0)),
        Ordering::Greater
    );
}
