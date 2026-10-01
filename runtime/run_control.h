// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — native IRQ sample command and drain lifecycle

/** @file run_control.h
 * native IRQ sample command and drain lifecycle.
 */

#ifndef WITNESS_RUN_CONTROL_H
#define WITNESS_RUN_CONTROL_H
#include "run_output.h"
#include <cstring>
#include <functional>

namespace witness {
/** Optional real acquisition lifecycle, checked between controller iterations. */
struct RunHooks { std::function<void()> start, check, finish; };

/** Observed counts, independent of planned cycle count or controller output. */
struct RunResult { std::uint64_t samples = 0, records = 0; std::uint32_t misses = 0, overflow = 0; bool safe = false; };

/** Preserve signed raw word bits without out-of-range arithmetic conversion. */
inline std::int32_t signed_word(std::uint32_t value) {
    std::int32_t result;
    std::memcpy(&result, &value, sizeof(result));
    return result;
}

/** Use the actual decoder response; hardware UIO accesses may instead bus-fault. */
template<class Device> std::uint32_t read_register(Device &device, std::uint8_t address) {
    const auto result = device.read(address);
    if (result.response != 0) throw std::runtime_error("register read refused at " + std::to_string(address));
    return result.data;
}

/** Full-word register submission through the selected in-process transport. */
template<class Device> void write_register(Device &device, std::uint8_t address, std::uint32_t value) {
    if (device.write(address, value, 15).response != 0)
        throw std::runtime_error("register write refused at " + std::to_string(address));
}

/** Reset only an idle/finished run, poll real release readiness, then configure. */
template<class Device> void configure_run(Device &device, const RunConfiguration &configuration) {
    validate_configuration(configuration);
    if (!(read_register(device, 0x98) & 8)) throw std::runtime_error("cannot reset an active run");
    if ((read_register(device, 0x90) & 7) != 4) throw std::runtime_error("unread previous run records prevent reset");
    write_register(device, 0x98, 0);
    write_register(device, 0x98, 1);
    const auto start = device.time();
    while ((read_register(device, 0x98) & 7) != 7)
        if (device.time() - start > 1000000000) throw std::runtime_error("run bank release timed out");
    if (read_register(device, 0x7c) != 1 || read_register(device, 0x78) != 24 ||
        read_register(device, 0x40) != configuration.period_ticks)
        throw std::runtime_error("compiled register ABI, Q format or period mismatch");
    write_register(device, 0x3c, configuration.cycles - 1);
    write_register(device, 0x44, configuration.reference_mode);
    write_register(device, 0x48, static_cast<std::uint32_t>(configuration.amplitude));
    write_register(device, 0x4c, static_cast<std::uint32_t>(configuration.offset));
    write_register(device, 0x50, static_cast<std::uint32_t>(configuration.ramp));
    write_register(device, 0x54, configuration.phase);
    if (configuration.fault_enabled) {
        write_register(device, 0x58, configuration.fault_kind);
        write_register(device, 0x5c, configuration.fault_cycle);
        write_register(device, 0x60, configuration.fault_periods);
        write_register(device, 0x64, 1);
    }
}

/** Drain at most eight held records before returning to IRQ service. */
template<class Device> void drain_available(Device &device, RunOutput &output, RunResult &result) {
    for (unsigned batch = 0; batch < 8 && (read_register(device, 0x90) & 1); ++batch) {
        std::array<std::uint32_t, 4> words{};
        for (unsigned index = 0; index < 4; ++index)
            words[index] = read_register(device, static_cast<std::uint8_t>(0x80 + index * 4));
        output.event(words);
        write_register(device, 0x94, 1);
        ++result.records;
    }
}

/** Handle one actual sample with the native kernel and an independently safe commit. */
template<class Device> void control_sample(Device &device, const RunConfiguration &configuration,
    witness_pid_state &state, RunOutput &output, RunResult &result, std::uint64_t generation,
    std::uint32_t &previous_cycle, bool &have_previous) {
    const auto position = signed_word(read_register(device, 0));
    const auto cycle = read_register(device, 0x10);
    const auto velocity = signed_word(read_register(device, 0x14));
    const auto reference = signed_word(read_register(device, 0x18));
    const std::uint64_t low = read_register(device, 0x1c);
    const auto ticks = low | (static_cast<std::uint64_t>(read_register(device, 0x20)) << 32);
    if (cycle >= configuration.cycles || (have_previous && cycle <= previous_cycle))
        throw std::runtime_error("duplicate or out-of-order sample cycle");
    previous_cycle = cycle;
    have_previous = true;
    witness_command command{};
    const bool computed = configuration.lqr ?
        witness_lqr_step(&configuration.coefficients, cycle, reference, position, velocity, &command) :
        witness_pid_step(&configuration.coefficients, &state, cycle, reference, position, &command);
    if (!computed) throw std::runtime_error("native controller refused validated coefficients");
    std::uint64_t work = 0;
    if (read_register(device, 0x68) & 4) {
        volatile std::uint64_t accumulator = 0;
        for (std::uint32_t index = 0; index < configuration.overload_iterations; ++index)
            accumulator = accumulator + static_cast<std::uint64_t>(index) * index;
        work = accumulator;
        device.advance(configuration.modeled_overload_ns);
    }
    bool submitted = false;
    if (!(read_register(device, 4) & 12)) {
        write_register(device, 0x28, cycle);
        write_register(device, 0x2c, static_cast<std::uint32_t>(command.command));
        const auto commit = device.write(0x30, 1, 15);
        if (commit.response != 0 && !(read_register(device, 4) & 12))
            throw std::runtime_error("command commit refused without a safe or finished run");
        submitted = commit.response == 0;
    }
    output.sample(reference, position, velocity, command, submitted, ticks, generation, work);
    ++result.samples;
}

/** Run configuration through final producer quiescence, receiver drain and real statistics. */
template<class Device> RunResult execute_run(Device &device, const RunConfiguration &configuration, RunOutput &output, const RunHooks *hooks = nullptr) {
    configure_run(device, configuration);
    witness_pid_state state{};
    witness_pid_reset(&state);
    RunResult result;
    std::uint32_t previous_cycle = 0;
    bool have_previous = false, finished = false;
    const auto run_limit = static_cast<std::uint64_t>(configuration.period_ticks) * 10 * configuration.cycles + 1000000000;
    if (hooks) hooks->start();
    write_register(device, 0x38, 1);
    const auto run_start = device.time();
    while (!finished) {
        if (hooks) hooks->check();
        if (device.wait_interrupt(1000000)) {
            const std::uint64_t low = read_register(device, 0x9c);
            const auto generation = low | (static_cast<std::uint64_t>(read_register(device, 0xa0)) << 32);
            const auto status = read_register(device, 4);
            finished = (status & 4) != 0;
            if (!finished && !(status & 8))
                control_sample(device, configuration, state, output, result, generation, previous_cycle, have_previous);
            write_register(device, 0xa4, 1);
        }
        if (device.time() - run_start > run_limit) throw std::runtime_error("configured run completion timed out");
        drain_available(device, output, result);
    }
    const auto drain_start = device.time();
    while (!(read_register(device, 0x90) & 8)) {
        if (hooks) hooks->check();
        drain_available(device, output, result);
        if (device.time() - drain_start > 1000000000) throw std::runtime_error("final record drain timed out");
    }
    result.misses = read_register(device, 0x34);
    result.overflow = read_register(device, 0x30);
    result.safe = (read_register(device, 4) & 8) != 0;
    if (hooks) hooks->finish();
    output.finish();
    return result;
}
} // namespace witness
/** @var witness::RunHooks::start
 * Optional acquisition start callback before controller execution.
 */
/** @var witness::RunHooks::check
 * Optional acquisition health callback between controller iterations.
 */
/** @var witness::RunHooks::finish
 * Optional acquisition completion callback after controller execution.
 */
/** @var witness::RunResult::samples
 * Actual number of completed controller samples.
 */
/** @var witness::RunResult::records
 * Actual number of drained fabric event records.
 */
/** @var witness::RunResult::misses
 * Observed fabric deadline-miss counter.
 */
/** @var witness::RunResult::overflow
 * Observed fabric dropped-event counter.
 */
/** @var witness::RunResult::safe
 * Observed latched fabric safe-state flag.
 */

#endif
