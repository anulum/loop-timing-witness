// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — native public controller refusal and recovery test

#include "witness_controller.h"
#include <assert.h>

#define SCALE INT32_C(16777216)

/** Test invalid configuration as an atomic refusal on both public kernels. */
static void refusal(witness_coefficients coefficients) {
    witness_pid_state state = {SCALE, -SCALE, SCALE, true};
    witness_command command = {42, SCALE, SCALE, -SCALE, true, true};
    assert(!witness_coefficients_valid(&coefficients));
    assert(!witness_pid_step(&coefficients, &state, 1, SCALE, 0, &command));
    assert(!witness_lqr_step(&coefficients, 1, SCALE, 0, 0, &command));
    assert(state.integral == SCALE && state.derivative == -SCALE &&
           state.previous_position == SCALE && state.initialized);
    assert(command.cycle == 42 && command.command == SCALE && command.integral == SCALE &&
           command.derivative == -SCALE && command.clipped && command.integral_held);
}

/** Exercise actual integral dynamics, reset and every invalid coefficient boundary. */
int main(void) {
    const witness_coefficients valid = {0,     SCALE,  0,     0,           SCALE,     SCALE,
                                        SCALE, -SCALE, SCALE, -10 * SCALE, 10 * SCALE};
    witness_pid_state state;
    witness_pid_reset(&state);
    witness_command command;
    assert(witness_pid_step(&valid, &state, 0, 2 * SCALE, 0, &command));
    assert(command.command == SCALE && command.integral == 2 * SCALE && command.clipped &&
           !command.integral_held);
    assert(witness_pid_step(&valid, &state, 1, 2 * SCALE, 0, &command));
    assert(command.integral == 2 * SCALE && command.integral_held);
    assert(witness_pid_step(&valid, &state, 2, -2 * SCALE, 0, &command));
    assert(command.command == 0 && command.integral == 0 && !command.integral_held);
    witness_pid_reset(&state);
    assert(!state.initialized && !state.integral && !state.derivative && !state.previous_position);
    witness_coefficients invalid;
    invalid = valid;
    invalid.output_min = 1;
    refusal(invalid);
    invalid = valid;
    invalid.output_max = -1;
    refusal(invalid);
    invalid = valid;
    invalid.output_min = 1;
    invalid.output_max = 0;
    refusal(invalid);
    invalid = valid;
    invalid.integral_min = 1;
    invalid.integral_max = 0;
    refusal(invalid);
    invalid = valid;
    invalid.integral_min = 1;
    refusal(invalid);
    invalid = valid;
    invalid.integral_max = -1;
    refusal(invalid);
    invalid = valid;
    invalid.kp = -1;
    refusal(invalid);
    invalid = valid;
    invalid.ki_period = -1;
    refusal(invalid);
    invalid = valid;
    invalid.derivative_decay = -1;
    refusal(invalid);
    invalid = valid;
    invalid.derivative_decay = SCALE + 1;
    refusal(invalid);
    invalid = valid;
    invalid.derivative_gain = -1;
    refusal(invalid);
    return 0;
}
