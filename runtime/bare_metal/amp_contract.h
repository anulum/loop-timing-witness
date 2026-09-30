// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — dedicated hart and single producer telemetry contract

#ifndef WITNESS_AMP_CONTRACT_H
#define WITNESS_AMP_CONTRACT_H
#include "../../controllers/c/witness_controller.h"

/** Telemetry ABI and power-of-two capacity; fullness is never silent data loss. */
#define WITNESS_AMP_ABI UINT32_C(2)
#define WITNESS_AMP_CAPACITY UINT32_C(256)

/** Operator-supplied resource addresses, checked against the actual boot and device mapping. */
typedef struct {
    uint32_t hart, interrupt;
    uint64_t mmio, priority, enable_word, threshold, claim, shared;
} witness_amp_platform_contract;

/** Immutable coefficients and run bounds compiled into the hash-bound firmware image. */
typedef struct {
    uint32_t cycles, period_ticks, lqr, overload_iterations;
    witness_coefficients coefficients;
} witness_amp_run_contract;

/** One observed sample and computed command, including actual commit-attempt status. */
typedef struct {
    uint64_t ticks, generation, overload_work;
    uint32_t cycle;
    int32_t reference, position, velocity, command, integral, derivative;
    uint32_t clipped, integral_held, submitted;
} witness_amp_sample;

/** Firmware owns producer/status; the sole Linux consumer owns consumer, with fence ordering. */
typedef struct {
    uint32_t abi, status, producer, consumer;
    uint64_t trap_cause, trap_value;
    uint32_t telemetry_overflow, samples;
    uint32_t logger_status, reserved;
    witness_amp_run_contract run;
    uint32_t run_reserved;
    witness_amp_sample records[WITNESS_AMP_CAPACITY];
} witness_amp_mailbox;

/** Status is monotonic: initial, armed, run finished or terminal refusal. */
enum witness_amp_status { WITNESS_AMP_INITIAL = 0, WITNESS_AMP_ARMED = 1,
                          WITNESS_AMP_FINISHED = 2, WITNESS_AMP_REFUSED = 3 };

/** Logger owns readiness and final close acknowledgement after firmware publishes its fresh ABI. */
enum witness_amp_logger_status { WITNESS_AMP_LOGGER_WAITING = 0,
                                WITNESS_AMP_LOGGER_COMPLETE = 1,
                                WITNESS_AMP_LOGGER_READY = 2 };

/** Platform and run data must be supplied by the complete firmware build, never defaulted. */
extern const witness_amp_platform_contract witness_amp_platform;
extern const witness_amp_run_contract witness_amp_run;

/** Validate the dedicated context, arm one IRQ source and wait for actual traps. */
#ifdef __cplusplus
[[noreturn]] void witness_amp_main(void);
#else
_Noreturn void witness_amp_main(void);
#endif
/** Service architectural machine external IRQs; other traps terminate controller service. */
void witness_amp_trap(uint64_t cause, uint64_t value);
/** Rust panic termination shares the original terminal telemetry refusal path. */
#ifdef __cplusplus
[[noreturn]] void witness_amp_rust_panic(void);
#else
_Noreturn void witness_amp_rust_panic(void);
#endif
/** Platform-specific termination after the real logger has flushed both completed streams. */
#ifdef __cplusplus
[[noreturn]] void witness_amp_exit(void);
#else
_Noreturn void witness_amp_exit(void);
#endif
#endif
