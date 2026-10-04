// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — public controller sequence fuzzing

#include <bit>
#include <cassert>
#include <cstddef>
#include <cstdint>

extern "C" {
#include "witness_controller.h"
}

namespace {
constexpr std::int32_t scale = 16777216;

std::uint32_t word(const std::uint8_t *input) {
    return static_cast<std::uint32_t>(input[0]) | (static_cast<std::uint32_t>(input[1]) << 8U) |
           (static_cast<std::uint32_t>(input[2]) << 16U) |
           (static_cast<std::uint32_t>(input[3]) << 24U);
}

std::int32_t signed_word(const std::uint8_t *input) {
    return std::bit_cast<std::int32_t>(word(input));
}

std::int32_t nonnegative(std::int32_t value) {
    return std::bit_cast<std::int32_t>(std::bit_cast<std::uint32_t>(value) & 0x7fffffffU);
}

std::int32_t negative(std::int32_t value) {
    return std::bit_cast<std::int32_t>(std::bit_cast<std::uint32_t>(value) | 0x80000000U);
}

bool same(const witness_pid_state &first, const witness_pid_state &second) {
    return first.integral == second.integral && first.derivative == second.derivative &&
           first.previous_position == second.previous_position &&
           first.initialized == second.initialized;
}

bool same(const witness_command &first, const witness_command &second) {
    return first.cycle == second.cycle && first.command == second.command &&
           first.integral == second.integral && first.derivative == second.derivative &&
           first.clipped == second.clipped && first.integral_held == second.integral_held;
}
} // namespace

/** Exercise coefficient admission and bounded PID/LQR sequences through the public C API.
 * One mode byte precedes eleven little-endian coefficient words and at most 32
 * 17-byte samples: reset flag, cycle, reference, position and velocity.
 * Mode bit0 normalises a valid domain; bit1 forces an invalid decay.
 * Assertions check public contracts without reproducing controller arithmetic.
 */
extern "C" int LLVMFuzzerTestOneInput(const std::uint8_t *data, std::size_t size) {
    constexpr std::size_t header = 45;
    constexpr std::size_t sample = 17;
    if (size < header) {
        return 0;
    }
    witness_coefficients coefficients{
        signed_word(data + 1),  signed_word(data + 5),  signed_word(data + 9),
        signed_word(data + 13), signed_word(data + 17), signed_word(data + 21),
        signed_word(data + 25), signed_word(data + 29), signed_word(data + 33),
        signed_word(data + 37), signed_word(data + 41)};
    if ((data[0] & 1U) != 0) {
        coefficients.kp = nonnegative(coefficients.kp);
        coefficients.ki_period = nonnegative(coefficients.ki_period);
        coefficients.derivative_gain = nonnegative(coefficients.derivative_gain);
        coefficients.derivative_decay = nonnegative(coefficients.derivative_decay) % (scale + 1);
        coefficients.output_min = negative(coefficients.output_min);
        coefficients.output_max = nonnegative(coefficients.output_max);
        coefficients.integral_min = negative(coefficients.integral_min);
        coefficients.integral_max = nonnegative(coefficients.integral_max);
    }
    if ((data[0] & 2U) != 0) {
        coefficients.derivative_decay = scale + 1;
    }
    const bool valid = witness_coefficients_valid(&coefficients);
    if ((data[0] & 2U) != 0) {
        assert(!valid);
    } else if ((data[0] & 1U) != 0) {
        assert(valid);
    }
    witness_pid_state state{1, 2, 3, true};
    witness_pid_reset(&state);
    assert(same(state, witness_pid_state{0, 0, 0, false}));
    for (std::size_t offset = header, count = 0; offset + sample <= size && count < 32;
         offset += sample, ++count) {
        if ((data[offset] & 1U) != 0) {
            witness_pid_reset(&state);
            assert(same(state, witness_pid_state{0, 0, 0, false}));
        }
        const std::uint32_t cycle = word(data + offset + 1);
        const std::int32_t reference = signed_word(data + offset + 5);
        const std::int32_t position = signed_word(data + offset + 9);
        const std::int32_t velocity = signed_word(data + offset + 13);
        const witness_pid_state previous = state;
        witness_command command{cycle ^ 0xffffffffU, 11, 12, 13, true, true};
        const witness_command untouched = command;
        const bool accepted =
            witness_pid_step(&coefficients, &state, cycle, reference, position, &command);
        assert(accepted == valid);
        if (!valid) {
            assert(same(state, previous) && same(command, untouched));
        } else {
            assert(state.initialized && state.previous_position == position);
            assert(command.cycle == cycle && command.integral == state.integral &&
                   command.derivative == state.derivative);
            assert(command.command >= coefficients.output_min &&
                   command.command <= coefficients.output_max);
            assert(state.integral >= coefficients.integral_min &&
                   state.integral <= coefficients.integral_max);
            assert(previous.initialized || command.derivative == 0);
            assert(!command.integral_held || state.integral == previous.integral);
            assert(!command.clipped || command.command == coefficients.output_min ||
                   command.command == coefficients.output_max);
        }
        command = untouched;
        assert(witness_lqr_step(&coefficients, cycle, reference, position, velocity, &command) ==
               valid);
        if (!valid) {
            assert(same(command, untouched));
        } else {
            assert(command.cycle == cycle && command.integral == 0 && command.derivative == 0 &&
                   !command.integral_held);
            assert(command.command >= coefficients.output_min &&
                   command.command <= coefficients.output_max);
            assert(!command.clipped || command.command == coefficients.output_min ||
                   command.command == coefficients.output_max);
            assert(witness_lqr_step(&coefficients, cycle, 0, 0, 0, &command));
            assert(command.command == 0 && !command.clipped);
        }
    }
    return 0;
}
