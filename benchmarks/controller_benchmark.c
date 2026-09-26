// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — native fixed-point kernel regression measurement

#include "witness_controller.h"
#include <inttypes.h>
#include <stdio.h>
#include <time.h>

#define SCALE INT32_C(16777216)
#define ITERATIONS UINT32_C(1000000)

/** Measure actual public kernels on a deterministic full streaming state input. */
int main(void) {
    const witness_coefficients coefficients = {2 * SCALE, 16777, SCALE / 2, SCALE / 4,
        38822697, 26419076, 55599913, -4 * SCALE, 4 * SCALE, -2 * SCALE, 2 * SCALE};
    for (unsigned mode = 0; mode < 2; mode++) {
        witness_pid_state state;
        witness_pid_reset(&state);
        uint32_t random_state = 1729;
        uint64_t checksum = 0;
        struct timespec begin, end;
        if (clock_gettime(CLOCK_MONOTONIC, &begin) != 0) return 1;
        for (uint32_t cycle = 0; cycle < ITERATIONS; cycle++) {
            random_state = random_state * UINT32_C(1664525) + UINT32_C(1013904223);
            const int32_t position = (int32_t)(((int64_t)random_state - INT64_C(2147483648)) / 128);
            random_state = random_state * UINT32_C(1664525) + UINT32_C(1013904223);
            const int32_t velocity = (int32_t)(((int64_t)random_state - INT64_C(2147483648)) / 128);
            witness_command command;
            const bool valid = mode == 0
                ? witness_pid_step(&coefficients, &state, cycle, SCALE, position, &command)
                : witness_lqr_step(&coefficients, cycle, SCALE, position, velocity, &command);
            if (!valid) return 1;
            checksum += (uint32_t)command.command;
        }
        if (clock_gettime(CLOCK_MONOTONIC, &end) != 0) return 1;
        const uint64_t elapsed = (uint64_t)((end.tv_sec - begin.tv_sec) * INT64_C(1000000000) +
                                           (end.tv_nsec - begin.tv_nsec));
        if (printf("%s,%" PRIu32 ",%" PRIu64 ",%" PRIu64 "\n",
                   mode == 0 ? "pid" : "lqr", ITERATIONS, elapsed, checksum) < 0) return 1;
    }
    return fflush(stdout) == EOF ? 1 : 0;
}
