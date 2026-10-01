// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — separate AMP telemetry and fabric event logger

/** @file amp_logger.h
 * separate AMP telemetry and fabric event logger.
 */

#ifndef WITNESS_AMP_LOGGER_H
#define WITNESS_AMP_LOGGER_H
#include "run_control.h"
extern "C" {
#include "bare_metal/amp_contract.h"
}
#include <cstddef>

namespace witness {
static_assert(sizeof(witness_amp_sample) == 64, "shared sample ABI mismatch");
static_assert(sizeof(witness_amp_mailbox) == 16496, "shared mailbox ABI mismatch");
static_assert(sizeof(witness_amp_run_contract) == 60, "shared run ABI mismatch");

/** Sole consumer of actual firmware RAM telemetry; sole drainer of the fabric event FIFO. */
template<class Device> class AmpLogger {
    Device &device;
    const RunConfiguration &configuration;
    RunOutput &output;
    const RunHooks *hooks;
    std::uint64_t shared;
    RunResult result;
    bool ready = false, started = false, completed = false, have_previous = false;
    std::uint32_t consumer = 0, previous_cycle = 0;
    std::uint64_t previous_ticks = 0, previous_generation = 0;

    /** Read a real little-endian RAM word through the backend's mapped memory transport. */
    std::uint32_t memory(std::size_t offset) {
        return device.read_memory32(shared + offset);
    }

    /** Reassemble actual low/high words; firmware retains the slot until consumer release. */
    std::uint64_t wide(std::size_t offset) {
        const auto low = memory(offset);
        return low | (static_cast<std::uint64_t>(memory(offset + 4)) << 32);
    }

    /** Match the actually running firmware's published constants before releasing startup. */
    void verify_run() {
        const auto &c = configuration.coefficients;
        const std::array<std::uint32_t, 15> expected{
            configuration.cycles, configuration.period_ticks, configuration.lqr ? 1U : 0U,
            configuration.overload_iterations,
            static_cast<std::uint32_t>(c.kp), static_cast<std::uint32_t>(c.ki_period),
            static_cast<std::uint32_t>(c.derivative_decay), static_cast<std::uint32_t>(c.derivative_gain),
            static_cast<std::uint32_t>(c.position_gain), static_cast<std::uint32_t>(c.velocity_gain),
            static_cast<std::uint32_t>(c.reference_gain), static_cast<std::uint32_t>(c.output_min),
            static_cast<std::uint32_t>(c.output_max), static_cast<std::uint32_t>(c.integral_min),
            static_cast<std::uint32_t>(c.integral_max)};
        for (std::size_t index = 0; index < expected.size(); ++index)
            if (memory(offsetof(witness_amp_mailbox, run) + index * 4) != expected[index])
                throw std::runtime_error("AMP running firmware contract differs from logger configuration");
        if (memory(offsetof(witness_amp_mailbox, run_reserved)))
            throw std::runtime_error("AMP run contract reserved field changed");
    }

    /** Decode one stable firmware-owned record with explicit ABI offsets and value bounds. */
    void consume(std::uint32_t producer) {
        if (producer - consumer > WITNESS_AMP_CAPACITY)
            throw std::runtime_error("AMP producer advanced beyond telemetry capacity");
        for (unsigned batch = 0; batch < 8 && consumer != producer; ++batch) {
            const auto slot = offsetof(witness_amp_mailbox, records) +
                (consumer & (WITNESS_AMP_CAPACITY - 1)) * sizeof(witness_amp_sample);
            const auto ticks = wide(slot);
            const auto generation = wide(slot + 8);
            const auto work = wide(slot + 16);
            const auto cycle = memory(slot + 24);
            const auto reference = signed_word(memory(slot + 28));
            const auto position = signed_word(memory(slot + 32));
            const auto velocity = signed_word(memory(slot + 36));
            const auto command = signed_word(memory(slot + 40));
            const auto integral = signed_word(memory(slot + 44));
            const auto derivative = signed_word(memory(slot + 48));
            const auto clipped = memory(slot + 52);
            const auto held = memory(slot + 56);
            const auto submitted = memory(slot + 60);
            if (cycle >= configuration.cycles || !generation || clipped > 1 || held > 1 || submitted > 1 ||
                (have_previous && (cycle <= previous_cycle || ticks <= previous_ticks ||
                                   generation <= previous_generation)))
                throw std::runtime_error("AMP telemetry contradicts the observed sample sequence");
            const witness_command observed{cycle, command, integral, derivative, clipped != 0, held != 0};
            output.sample(reference, position, velocity, observed, submitted != 0, ticks, generation, work);
            previous_cycle = cycle;
            previous_ticks = ticks;
            previous_generation = generation;
            have_previous = true;
            ++result.samples;
            ++consumer;
            device.write_memory32(shared + offsetof(witness_amp_mailbox, consumer), consumer);
        }
    }

public:
    /** Bind hash-bound run data and an explicit reserved mailbox before either owner starts. */
    AmpLogger(Device &backend, const RunConfiguration &run, RunOutput &files, std::uint64_t mailbox_address,
              const RunHooks *acquisition = nullptr)
        : device(backend), configuration(run), output(files), hooks(acquisition), shared(mailbox_address) {
        validate_configuration(configuration);
        if (!shared || shared % 8 || shared > UINT64_MAX - sizeof(witness_amp_mailbox))
            throw std::invalid_argument("AMP mailbox address outside bounds");
    }

    /** Poll real owners; start only after firmware arms, finish only after both streams drain. */
    bool poll() {
        if (completed) throw std::runtime_error("AMP logger is already complete");
        if (hooks) hooks->check();
        const auto status = memory(offsetof(witness_amp_mailbox, status));
        if (status > WITNESS_AMP_REFUSED) throw std::runtime_error("unknown AMP firmware status");
        if (status == WITNESS_AMP_REFUSED || memory(offsetof(witness_amp_mailbox, telemetry_overflow)))
            throw std::runtime_error("AMP firmware refused or telemetry overflowed: cause=" +
                std::to_string(wide(offsetof(witness_amp_mailbox, trap_cause))) + " value=" +
                std::to_string(wide(offsetof(witness_amp_mailbox, trap_value))));
        const auto abi = memory(offsetof(witness_amp_mailbox, abi));
        if (!abi) {
            if (ready) throw std::runtime_error("AMP ABI disappeared during the run");
            return false;
        }
        if (abi != WITNESS_AMP_ABI) throw std::runtime_error("AMP telemetry ABI mismatch");
        if (!ready) {
            if (status != WITNESS_AMP_INITIAL ||
                memory(offsetof(witness_amp_mailbox, producer)) ||
                memory(offsetof(witness_amp_mailbox, consumer)) ||
                wide(offsetof(witness_amp_mailbox, trap_cause)) ||
                wide(offsetof(witness_amp_mailbox, trap_value)) ||
                memory(offsetof(witness_amp_mailbox, samples)) ||
                memory(offsetof(witness_amp_mailbox, logger_status)) ||
                memory(offsetof(witness_amp_mailbox, reserved)))
                throw std::runtime_error("AMP firmware did not initialize a fresh mailbox");
            verify_run();
            device.write_memory32(shared + offsetof(witness_amp_mailbox, logger_status),
                                  WITNESS_AMP_LOGGER_READY);
            ready = true;
            return false;
        }
        if ((started && status == WITNESS_AMP_INITIAL) ||
            memory(offsetof(witness_amp_mailbox, logger_status)) != WITNESS_AMP_LOGGER_READY ||
            memory(offsetof(witness_amp_mailbox, reserved)) ||
            memory(offsetof(witness_amp_mailbox, run_reserved)))
            throw std::runtime_error("AMP shared ownership or reserved fields changed");
        if (wide(offsetof(witness_amp_mailbox, trap_cause)) ||
            wide(offsetof(witness_amp_mailbox, trap_value)))
            throw std::runtime_error("AMP trap state contradicts active firmware status");
        if (!started) {
            if (status == WITNESS_AMP_INITIAL) return false;
            if (status != WITNESS_AMP_ARMED || memory(offsetof(witness_amp_mailbox, consumer)) ||
                memory(offsetof(witness_amp_mailbox, producer)))
                throw std::runtime_error("AMP firmware did not arm a fresh run");
            if (hooks) hooks->start();
            write_register(device, 0x38, 1);
            started = true;
        }
        if (memory(offsetof(witness_amp_mailbox, consumer)) != consumer)
            throw std::runtime_error("AMP telemetry consumer ownership changed");
        const auto producer = memory(offsetof(witness_amp_mailbox, producer));
        consume(producer);
        drain_available(device, output, result);
        if (status != WITNESS_AMP_FINISHED) return false;
        if (!(read_register(device, 4) & 4))
            throw std::runtime_error("AMP completion precedes the actual fabric run finish");
        if (consumer != memory(offsetof(witness_amp_mailbox, producer)) ||
            !(read_register(device, 0x90) & 8)) return false;
        if (memory(offsetof(witness_amp_mailbox, samples)) != result.samples)
            throw std::runtime_error("AMP sample count differs from consumed telemetry");
        result.misses = read_register(device, 0x34);
        result.overflow = read_register(device, 0x30);
        result.safe = (read_register(device, 4) & 8) != 0;
        if (hooks) hooks->finish();
        output.finish();
        device.write_memory32(shared + offsetof(witness_amp_mailbox, logger_status),
                              WITNESS_AMP_LOGGER_COMPLETE);
        completed = true;
        return true;
    }

    /** Return observed counts only after successful final event and telemetry drain. */
    RunResult completion() const {
        if (!completed) throw std::runtime_error("AMP run is not complete");
        return result;
    }
};
}
#endif
