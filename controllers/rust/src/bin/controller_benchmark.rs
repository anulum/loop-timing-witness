// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — native fixed-point kernel regression measurement

//! Measure public kernels; unisolated runs establish regression evidence only.

use std::time::Instant;
use witness_controller::{Coefficients, PidState, lqr_step};

const SCALE: i32 = 1 << 24;
const ITERATIONS: u32 = 1_000_000;

/// Time matching deterministic public-kernel workloads and retain command checksums.
fn main() -> Result<(), String> {
    let coefficients = Coefficients {
        kp: 2 * SCALE,
        ki_period: 16777,
        derivative_decay: SCALE / 2,
        derivative_gain: SCALE / 4,
        position_gain: 38822697,
        velocity_gain: 26419076,
        reference_gain: 55599913,
        output_min: -4 * SCALE,
        output_max: 4 * SCALE,
        integral_min: -2 * SCALE,
        integral_max: 2 * SCALE,
    };
    for mode in ["pid", "lqr"] {
        let mut state = PidState::default();
        let mut random_state = 1729_u32;
        let mut checksum = 0_u64;
        let begin = Instant::now();
        for cycle in 0..ITERATIONS {
            random_state = random_state.wrapping_mul(1664525).wrapping_add(1013904223);
            let position = ((i64::from(random_state) - 2147483648) / 128) as i32;
            random_state = random_state.wrapping_mul(1664525).wrapping_add(1013904223);
            let velocity = ((i64::from(random_state) - 2147483648) / 128) as i32;
            let command = if mode == "pid" {
                state.step(&coefficients, cycle, SCALE, position)
            } else {
                lqr_step(&coefficients, cycle, SCALE, position, velocity)
            }
            .map_err(|_| "invalid coefficients")?;
            checksum += u64::from(command.command as u32);
        }
        println!(
            "{mode},{ITERATIONS},{},{checksum}",
            begin.elapsed().as_nanos()
        );
    }
    Ok(())
}
