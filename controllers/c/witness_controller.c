// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — controllers/c/witness_controller.c

#include "witness_controller.h"

#include <limits.h>

/* GNU C on the target RV64 ABI provides exact wide accumulation. Products and
 * sums here fit in 67 signed bits; no signed overflow or negative shift occurs. */
__extension__ typedef __int128 witness_wide;
#define WITNESS_SCALE INT64_C(16777216)

/** Floor a wide Q16.48 accumulator to raw Q8.24 without signed shift assumptions. */
static int64_t floor_scaled(witness_wide value) {
    witness_wide quotient = value / WITNESS_SCALE;
    if (value < 0 && value % WITNESS_SCALE != 0) {
        quotient -= 1;
    }
    return (int64_t)quotient;
}

/** Saturate an exact raw value into a validated signed 32-bit interval. */
static int32_t clamp(int64_t value, int32_t lower, int32_t upper) {
    if (value < lower) {
        return lower;
    }
    if (value > upper) {
        return upper;
    }
    return (int32_t)value;
}

bool witness_coefficients_valid(const witness_coefficients *coefficients) {
    return coefficients->output_min <= coefficients->output_max &&
           coefficients->integral_min <= coefficients->integral_max &&
           coefficients->output_min <= 0 && coefficients->output_max >= 0 &&
           coefficients->integral_min <= 0 && coefficients->integral_max >= 0 &&
           coefficients->kp >= 0 && coefficients->ki_period >= 0 &&
           coefficients->derivative_gain >= 0 &&
           coefficients->derivative_decay >= 0 &&
           coefficients->derivative_decay <= WITNESS_SCALE;
}

void witness_pid_reset(witness_pid_state *state) {
    *state = (witness_pid_state){0, 0, 0, false};
}

bool witness_pid_step(const witness_coefficients *coefficients,
                      witness_pid_state *state, uint32_t cycle,
                      int32_t reference, int32_t position,
                      witness_command *command) {
    if (!witness_coefficients_valid(coefficients)) {
        return false;
    }
    const int64_t error = (int64_t)reference - position;
    const int64_t difference = (int64_t)position - state->previous_position;
    const int32_t derivative = state->initialized
        ? clamp(floor_scaled((witness_wide)coefficients->derivative_decay * state->derivative -
                            (witness_wide)coefficients->derivative_gain * difference),
                INT32_MIN, INT32_MAX)
        : 0;
    const int32_t proposed_integral = clamp(
        floor_scaled((witness_wide)state->integral * WITNESS_SCALE +
                     (witness_wide)coefficients->ki_period * error),
        coefficients->integral_min, coefficients->integral_max);
    int64_t raw = floor_scaled((witness_wide)coefficients->kp * error +
                              (witness_wide)state->integral * WITNESS_SCALE +
                              (witness_wide)derivative * WITNESS_SCALE);
    const bool held = (raw >= coefficients->output_max && error > 0) ||
                      (raw <= coefficients->output_min && error < 0);
    const int32_t integral = held ? state->integral : proposed_integral;
    raw = floor_scaled((witness_wide)coefficients->kp * error +
                           (witness_wide)integral * WITNESS_SCALE +
                           (witness_wide)derivative * WITNESS_SCALE);
    *state = (witness_pid_state){integral, derivative, position, true};
    *command = (witness_command){cycle,
        clamp(raw, coefficients->output_min, coefficients->output_max),
        integral, derivative,
        raw < coefficients->output_min || raw > coefficients->output_max, held};
    return true;
}

bool witness_lqr_step(const witness_coefficients *coefficients, uint32_t cycle,
                      int32_t reference, int32_t position, int32_t velocity,
                      witness_command *command) {
    if (!witness_coefficients_valid(coefficients)) {
        return false;
    }
    const int64_t raw = floor_scaled((witness_wide)coefficients->reference_gain * reference -
                                    (witness_wide)coefficients->position_gain * position -
                                    (witness_wide)coefficients->velocity_gain * velocity);
    *command = (witness_command){cycle,
        clamp(raw, coefficients->output_min, coefficients->output_max), 0, 0,
        raw < coefficients->output_min || raw > coefficients->output_max, false};
    return true;
}
