// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — public state reset and invalid-coefficient atomicity

//! Exercise production public APIs at refusal and integral saturation boundaries.

use witness_controller::{Coefficients, PidState, lqr_step};

const SCALE: i32 = 1 << 24;

/// Construct the pure-integral rail and recovery configuration.
fn configuration() -> Coefficients {
    Coefficients {
        kp: 0,
        ki_period: SCALE,
        derivative_decay: 0,
        derivative_gain: 0,
        position_gain: SCALE,
        velocity_gain: SCALE,
        reference_gain: SCALE,
        output_min: -SCALE,
        output_max: SCALE,
        integral_min: -10 * SCALE,
        integral_max: 10 * SCALE,
    }
}

/// Verify actual rail crossing, conditional hold, recovery and reset.
#[test]
fn conditional_integration_reaches_rail_and_recovers() {
    let coefficients = configuration();
    let mut state = PidState::default();
    let first = state
        .step(&coefficients, 0, 2 * SCALE, 0)
        .expect("valid coefficients");
    assert_eq!(first.command, SCALE);
    assert_eq!(first.integral, 2 * SCALE);
    assert!(first.clipped);
    assert!(!first.integral_held);
    let second = state
        .step(&coefficients, 1, 2 * SCALE, 0)
        .expect("valid coefficients");
    assert_eq!(second.integral, first.integral);
    assert!(second.integral_held);
    let recovery = state
        .step(&coefficients, 2, -2 * SCALE, 0)
        .expect("valid coefficients");
    assert_eq!(recovery.command, 0);
    assert_eq!(recovery.integral, 0);
    assert!(!recovery.integral_held);
    state.reset();
    assert_eq!(state, PidState::default());
}

/// Refuse every invalid coefficient boundary without mutating live PID state.
#[test]
fn invalid_configuration_leaves_pid_state_unchanged() {
    let valid = configuration();
    let mut state = PidState::default();
    state.step(&valid, 0, SCALE, 0).expect("valid coefficients");
    let before = state;
    let invalid = [
        Coefficients {
            output_min: 1,
            ..valid
        },
        Coefficients {
            output_max: -1,
            ..valid
        },
        Coefficients {
            output_min: 1,
            output_max: 0,
            ..valid
        },
        Coefficients {
            integral_min: 1,
            integral_max: 0,
            ..valid
        },
        Coefficients {
            integral_min: 1,
            ..valid
        },
        Coefficients {
            integral_max: -1,
            ..valid
        },
        Coefficients { kp: -1, ..valid },
        Coefficients {
            ki_period: -1,
            ..valid
        },
        Coefficients {
            derivative_decay: -1,
            ..valid
        },
        Coefficients {
            derivative_decay: SCALE + 1,
            ..valid
        },
        Coefficients {
            derivative_gain: -1,
            ..valid
        },
    ];
    for coefficients in invalid {
        assert!(state.step(&coefficients, 1, SCALE, 0).is_err());
        assert!(lqr_step(&coefficients, 1, SCALE, 0, 0).is_err());
        assert_eq!(state, before);
    }
}
