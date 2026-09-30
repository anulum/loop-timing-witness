// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — controllers/rust/src/lib.rs

//! Bit-exact Q8.24 controllers. Coefficients are held stable until reset.
//! Products accumulate in i128; division floors negative fractional values.
//! These kernels do not establish physical timing or controller stability.
//! The library uses only core arithmetic and requires neither an allocator nor an OS.

#![no_std]

const SCALE: i128 = 1 << 24;

/// C-layout signed Q8.24 coefficients and output/integral bounds.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(C)]
pub struct Coefficients {
    /// Proportional error gain, nonnegative.
    pub kp: i32,
    /// Integral gain times sample period, nonnegative.
    pub ki_period: i32,
    /// Filter decay in the inclusive interval [0, 2^24].
    pub derivative_decay: i32,
    /// Filtered derivative gain on the measurement difference, nonnegative.
    pub derivative_gain: i32,
    /// Discrete LQR position state feedback.
    pub position_gain: i32,
    /// Discrete LQR velocity state feedback; zero for the scalar thermal model.
    pub velocity_gain: i32,
    /// Steady-state reference prefilter gain.
    pub reference_gain: i32,
    /// Minimum actuator command.
    pub output_min: i32,
    /// Maximum actuator command.
    pub output_max: i32,
    /// Minimum PID integral state.
    pub integral_min: i32,
    /// Maximum PID integral state.
    pub integral_max: i32,
}

/// Refused coefficient range; kernels return before changing any state.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct InvalidCoefficients;

impl Coefficients {
    /// Check bounds, nonnegative PID gains and stable derivative filter decay.
    pub fn validate(&self) -> Result<(), InvalidCoefficients> {
        if self.output_min > self.output_max
            || self.integral_min > self.integral_max
            || self.output_min > 0
            || self.output_max < 0
            || self.integral_min > 0
            || self.integral_max < 0
            || self.kp < 0
            || self.ki_period < 0
            || self.derivative_gain < 0
            || self.derivative_decay < 0
            || i128::from(self.derivative_decay) > SCALE
        {
            return Err(InvalidCoefficients);
        }
        Ok(())
    }
}

/// C-layout cycle-tagged command plus the observable PID state and clipping decisions.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(C)]
pub struct Command {
    /// Original input cycle, unchanged by arithmetic latency.
    pub cycle: u32,
    /// Saturated actuator command.
    pub command: i32,
    /// PID integral state after this sample; zero for LQR.
    pub integral: i32,
    /// PID derivative state after this sample; zero for LQR.
    pub derivative: i32,
    /// Final unsaturated actuator value exceeded a configured limit.
    pub clipped: bool,
    /// Conditional integration refused a step that would worsen saturation.
    pub integral_held: bool,
}

/// C-layout PID memory, with reset marking the next measurement as the derivative origin.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
#[repr(C)]
pub struct PidState {
    /// Current bounded integral.
    pub integral: i32,
    /// Current bounded filtered derivative on measurement.
    pub derivative: i32,
    previous_position: i32,
    initialized: bool,
}

/// Saturate a complete wide result into the validated signed raw interval.
fn clamp(value: i128, lower: i32, upper: i32) -> i32 {
    value.clamp(i128::from(lower), i128::from(upper)) as i32
}

impl PidState {
    /// Clear all memory and establish a zero-derivative first sample.
    pub fn reset(&mut self) {
        *self = Self::default();
    }

    /// Update a conditional-integration PID with derivative on measurement.
    ///
    /// The prior integral is used to detect output saturation. If saturation
    /// and error have the same direction, retain that integral; otherwise accept
    /// the proposed integral before computing the command. First-sample derivative
    /// is zero. Invalid coefficients leave state unchanged. Gains remain stable
    /// until reset.
    pub fn step(
        &mut self,
        coefficients: &Coefficients,
        cycle: u32,
        reference: i32,
        position: i32,
    ) -> Result<Command, InvalidCoefficients> {
        coefficients.validate()?;
        let error = i128::from(reference) - i128::from(position);
        let difference = i128::from(position) - i128::from(self.previous_position);
        let derivative = if self.initialized {
            clamp(
                (i128::from(coefficients.derivative_decay) * i128::from(self.derivative)
                    - i128::from(coefficients.derivative_gain) * difference)
                    .div_euclid(SCALE),
                i32::MIN,
                i32::MAX,
            )
        } else {
            0
        };
        let proposed_integral = clamp(
            (i128::from(self.integral) * SCALE + i128::from(coefficients.ki_period) * error)
                .div_euclid(SCALE),
            coefficients.integral_min,
            coefficients.integral_max,
        );
        let proportional = i128::from(coefficients.kp) * error;
        let output = |integral| {
            (proportional + i128::from(integral) * SCALE + i128::from(derivative) * SCALE)
                .div_euclid(SCALE)
        };
        let provisional = output(self.integral);
        let held = (provisional >= i128::from(coefficients.output_max) && error > 0)
            || (provisional <= i128::from(coefficients.output_min) && error < 0);
        let integral = if held {
            self.integral
        } else {
            proposed_integral
        };
        let raw = output(integral);
        self.integral = integral;
        self.derivative = derivative;
        self.previous_position = position;
        self.initialized = true;
        Ok(Command {
            cycle,
            command: clamp(raw, coefficients.output_min, coefficients.output_max),
            integral,
            derivative,
            clipped: raw < i128::from(coefficients.output_min)
                || raw > i128::from(coefficients.output_max),
            integral_held: held,
        })
    }
}

/// Apply full-state discrete LQR and a reference prefilter, then saturate output.
///
/// The kernel computes floor((nr*r-kx*y-kv*v)/2^24). Supplied gains need an
/// independently recorded Riccati design and quantized closed-loop stability
/// check. Invalid coefficients do not yield a command.
pub fn lqr_step(
    coefficients: &Coefficients,
    cycle: u32,
    reference: i32,
    position: i32,
    velocity: i32,
) -> Result<Command, InvalidCoefficients> {
    coefficients.validate()?;
    let raw = (i128::from(coefficients.reference_gain) * i128::from(reference)
        - i128::from(coefficients.position_gain) * i128::from(position)
        - i128::from(coefficients.velocity_gain) * i128::from(velocity))
    .div_euclid(SCALE);
    Ok(Command {
        cycle,
        command: clamp(raw, coefficients.output_min, coefficients.output_max),
        integral: 0,
        derivative: 0,
        clipped: raw < i128::from(coefficients.output_min)
            || raw > i128::from(coefficients.output_max),
        integral_held: false,
    })
}
