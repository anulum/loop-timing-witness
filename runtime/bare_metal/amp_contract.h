// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — dedicated hart and single producer telemetry contract

/** @file amp_contract.h
 * dedicated hart and single producer telemetry contract.
 */

#ifndef WITNESS_AMP_CONTRACT_H
#define WITNESS_AMP_CONTRACT_H
#include "../../controllers/c/witness_controller.h"

/** Telemetry ABI and power-of-two capacity; fullness is never silent data loss. */
#define WITNESS_AMP_ABI UINT32_C(2)
/** Telemetry ring capacity; producer and consumer index it with a power-of-two mask. */
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
enum witness_amp_status {
    WITNESS_AMP_INITIAL = 0 /**< Mailbox is initialised; the controller is not armed. */,
    WITNESS_AMP_ARMED = 1 /**< Controller interrupt service is armed for the configured run. */,
    WITNESS_AMP_FINISHED =
        2 /**< The finite run completed and telemetry remains available for draining. */,
    WITNESS_AMP_REFUSED = 3 /**< Terminal refusal; trap cause and value retain the failure. */
};

/** Logger owns readiness and final close acknowledgement after firmware publishes its fresh ABI. */
enum witness_amp_logger_status {
    WITNESS_AMP_LOGGER_WAITING =
        0 /**< Firmware waits for the sole logger to validate the fresh mailbox. */,
    WITNESS_AMP_LOGGER_COMPLETE =
        1 /**< Logger has flushed and closed both completed output streams. */,
    WITNESS_AMP_LOGGER_READY = 2 /**< Logger owns the consumer and is ready to drain telemetry. */
};

/** Platform and run data must be supplied by the complete firmware build, never defaulted. */
extern const witness_amp_platform_contract witness_amp_platform;
/** Immutable operator-supplied run data compiled into the hash-bound image. */
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
/** @var witness_amp_mailbox::abi
 * Telemetry ABI published by firmware before logger readiness.
 */
/** @var witness_amp_mailbox::status
 * Monotonic firmware lifecycle state from witness_amp_status.
 */
/** @var witness_amp_mailbox::producer
 * Firmware-owned monotonically advancing telemetry producer cursor.
 */
/** @var witness_amp_mailbox::consumer
 * Logger-owned monotonically advancing telemetry consumer cursor.
 */
/** @var witness_amp_mailbox::trap_cause
 * Architectural or software refusal cause retained on termination.
 */
/** @var witness_amp_mailbox::trap_value
 * Additional architectural or software refusal value.
 */
/** @var witness_amp_mailbox::telemetry_overflow
 * Latched indication that a telemetry sample could not enter the full ring.
 */
/** @var witness_amp_mailbox::samples
 * Number of firmware samples published during the run.
 */
/** @var witness_amp_mailbox::logger_status
 * Logger-owned readiness or final-close acknowledgement.
 */
/** @var witness_amp_mailbox::reserved
 * ABI padding required to remain zero.
 */
/** @var witness_amp_mailbox::run
 * Firmware-published immutable copy of the compiled run contract.
 */
/** @var witness_amp_mailbox::run_reserved
 * Run-contract alignment padding required to remain zero.
 */
/** @var witness_amp_mailbox::records
 * Power-of-two telemetry ring indexed by the producer and consumer cursors.
 */
/** @var witness_amp_platform_contract::hart
 * Dedicated machine-mode application hart identifier.
 */
/** @var witness_amp_platform_contract::interrupt
 * Controller-owned PLIC source identifier.
 */
/** @var witness_amp_platform_contract::mmio
 * Physical base of the fabric register aperture.
 */
/** @var witness_amp_platform_contract::priority
 * Physical PLIC priority-register address.
 */
/** @var witness_amp_platform_contract::enable_word
 * Physical address of the selected PLIC enable word.
 */
/** @var witness_amp_platform_contract::threshold
 * Physical PLIC threshold-register address.
 */
/** @var witness_amp_platform_contract::claim
 * Physical PLIC claim/complete-register address.
 */
/** @var witness_amp_platform_contract::shared
 * Physical base of the reserved telemetry mailbox.
 */
/** @var witness_amp_run_contract::cycles
 * Exclusive upper bound on accepted input cycle identifiers.
 */
/** @var witness_amp_run_contract::period_ticks
 * Requested controller period in fabric timebase ticks.
 */
/** @var witness_amp_run_contract::lqr
 * Nonzero selects LQR; zero selects PID.
 */
/** @var witness_amp_run_contract::overload_iterations
 * Number of checksum iterations performed during an overload request.
 */
/** @var witness_amp_run_contract::coefficients
 * Immutable signed raw Q8.24 gains and saturation bounds.
 */
/** @var witness_amp_sample::ticks
 * Fabric timestamp sampled with the controller input.
 */
/** @var witness_amp_sample::generation
 * Observed interrupt generation associated with this input.
 */
/** @var witness_amp_sample::overload_work
 * Checksum accumulated by the actual requested overload loop.
 */
/** @var witness_amp_sample::cycle
 * Original fabric input cycle identifier.
 */
/** @var witness_amp_sample::reference
 * Signed raw Q8.24 reference input.
 */
/** @var witness_amp_sample::position
 * Signed raw Q8.24 observed plant position.
 */
/** @var witness_amp_sample::velocity
 * Signed raw Q8.24 observed plant velocity.
 */
/** @var witness_amp_sample::command
 * Signed raw Q8.24 computed actuator command.
 */
/** @var witness_amp_sample::integral
 * Signed raw Q8.24 PID integral state after computation.
 */
/** @var witness_amp_sample::derivative
 * Signed raw Q8.24 filtered derivative state after computation.
 */
/** @var witness_amp_sample::clipped
 * One when the computed command exceeds configured output limits.
 */
/** @var witness_amp_sample::integral_held
 * One when conditional integration retains the previous integral.
 */
/** @var witness_amp_sample::submitted
 * One after the command commit was actually attempted; zero when safe-state flags prevent it.
 */

#endif
