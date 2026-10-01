// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — controllers/c/witness_controller.h

/** @file witness_controller.h
 * controllers/c/witness_controller.h.
 */

#ifndef WITNESS_CONTROLLER_H
#define WITNESS_CONTROLLER_H

#include <stdbool.h>
#include <stdint.h>

/** Signed raw Q8.24 constants, held stable between controller reset boundaries. */
typedef struct {
    int32_t kp, ki_period, derivative_decay, derivative_gain;
    int32_t position_gain, velocity_gain, reference_gain;
    int32_t output_min, output_max, integral_min, integral_max;
} witness_coefficients;

/** PID memory; zero initialization establishes the first-sample derivative boundary. */
typedef struct {
    int32_t integral, derivative, previous_position;
    bool initialized;
} witness_pid_state;

/** One command and observable state, tagged with the input cycle. */
typedef struct {
    uint32_t cycle;
    int32_t command, integral, derivative;
    bool clipped, integral_held;
} witness_command;

/** Refuse reversed bounds, bounds excluding zero, negative PID gains or decay outside [0,1]. */
bool witness_coefficients_valid(const witness_coefficients *coefficients);

/** Reset all PID state, including derivative-on-measurement initialization. */
void witness_pid_reset(witness_pid_state *state);

/**
 * Compute conditional-integration PID; return false without mutation for invalid
 * coefficients. Error and measurement differences retain their signed 33-bit
 * range. Products accumulate before floor division by 2^24. Output saturation
 * with the prior integral freezes integration if the error would worsen it.
 * Otherwise accept the bounded integral proposal before computing output.
 * The first sample has zero derivative; subsequent samples use a filtered
 * derivative on measurement. No setpoint derivative kick is introduced.
 */
bool witness_pid_step(const witness_coefficients *coefficients,
                      witness_pid_state *state, uint32_t cycle,
                      int32_t reference, int32_t position,
                      witness_command *command);

/**
 * Compute u=floor((reference_gain*r-position_gain*y-velocity_gain*v)/2^24)
 * followed by configured output saturation. Gains are supplied from a discrete
 * Riccati design; this kernel does not solve or certify the Riccati equation.
 * Invalid coefficients leave the command unchanged.
 */
bool witness_lqr_step(const witness_coefficients *coefficients, uint32_t cycle,
                      int32_t reference, int32_t position, int32_t velocity,
                      witness_command *command);

/** @var witness_coefficients::kp
 * Nonnegative proportional error gain in signed raw Q8.24.
 */
/** @var witness_coefficients::ki_period
 * Nonnegative integral gain multiplied by the sample period, in raw Q8.24.
 */
/** @var witness_coefficients::derivative_decay
 * Filtered derivative decay in the inclusive raw interval zero through 2^24.
 */
/** @var witness_coefficients::derivative_gain
 * Nonnegative derivative-on-measurement gain in raw Q8.24.
 */
/** @var witness_coefficients::position_gain
 * Discrete LQR position feedback gain in raw Q8.24.
 */
/** @var witness_coefficients::velocity_gain
 * Discrete LQR velocity feedback gain in raw Q8.24.
 */
/** @var witness_coefficients::reference_gain
 * Discrete LQR reference prefilter gain in raw Q8.24.
 */
/** @var witness_coefficients::output_min
 * Minimum permitted actuator command in raw Q8.24.
 */
/** @var witness_coefficients::output_max
 * Maximum permitted actuator command in raw Q8.24.
 */
/** @var witness_coefficients::integral_min
 * Minimum PID integral state in raw Q8.24.
 */
/** @var witness_coefficients::integral_max
 * Maximum PID integral state in raw Q8.24.
 */
/** @var witness_command::cycle
 * Original input cycle identifier retained through computation.
 */
/** @var witness_command::command
 * Saturated actuator command in raw Q8.24.
 */
/** @var witness_command::integral
 * PID integral state after the sample; zero for LQR.
 */
/** @var witness_command::derivative
 * PID derivative state after the sample; zero for LQR.
 */
/** @var witness_command::clipped
 * Whether the unsaturated command exceeds a configured limit.
 */
/** @var witness_command::integral_held
 * Whether saturation and error direction prevent integral accumulation.
 */
/** @var witness_pid_state::integral
 * Current bounded integral state in raw Q8.24.
 */
/** @var witness_pid_state::derivative
 * Current filtered derivative state in raw Q8.24.
 */
/** @var witness_pid_state::previous_position
 * Previous raw Q8.24 measurement used for derivative-on-measurement.
 */
/** @var witness_pid_state::initialized
 * Whether a previous measurement exists since the last reset.
 */

#endif
