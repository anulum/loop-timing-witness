// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — original release Rust API state reset consumer

//! Verify state clearing and the next measurement through the compiled public Rust API.

use witness_controller::{Coefficients, PidState};

const SCALE: i32 = 1 << 24;

fn main() {
    let coefficients = Coefficients {
        kp: 0,
        ki_period: SCALE,
        derivative_decay: 0,
        derivative_gain: SCALE,
        position_gain: 0,
        velocity_gain: 0,
        reference_gain: SCALE,
        output_min: -4 * SCALE,
        output_max: 4 * SCALE,
        integral_min: -4 * SCALE,
        integral_max: 4 * SCALE,
    };
    let mut state = PidState::default();
    let first = state
        .step(&coefficients, 0, SCALE, 0)
        .expect("valid coefficients");
    assert_eq!(first.command, SCALE);
    assert_eq!(first.integral, SCALE);
    assert_eq!(first.derivative, 0);
    let second = state
        .step(&coefficients, 1, SCALE, SCALE / 2)
        .expect("valid coefficients");
    assert_eq!(second.cycle, 1);
    assert_eq!(second.command, SCALE);
    assert_eq!(second.integral, 3 * SCALE / 2);
    assert_eq!(second.derivative, -SCALE / 2);
    state.reset();
    assert_eq!(state, PidState::default());
    let restart = state
        .step(&coefficients, 2, SCALE, -SCALE / 2)
        .expect("valid coefficients");
    assert_eq!(restart.cycle, 2);
    assert_eq!(restart.integral, 3 * SCALE / 2);
    assert_eq!(restart.derivative, 0);
    assert_eq!(restart.command, 3 * SCALE / 2);
    println!("original release Rust API reset verified");
}
