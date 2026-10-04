// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — actual RTL lifecycle API tests

#include "../../runtime/rtl/simulation.h"
#include "../../runtime/run_control.h"
#include <cassert>
#include <iostream>
#include <fstream>
#include <sstream>
#include <algorithm>
#include "output_limit.h"
#ifdef WITNESS_RTL_COVERAGE
#include "verilated_cov.h"
#endif

/** Require the actual production API to reject a real transport state precisely. */
template <class Operation> void refusal(Operation operation, const char *message) {
    bool rejected = false;
    try {
        operation();
    } catch (const std::runtime_error &error) {
        rejected = true;
        assert(std::string(error.what()) == message);
    }
    assert(rejected);
}

#include "configuration_api.h"
#include "metadata_api.h"

/** Observe a run finishing between the live-status read and command commit. */
void boundary_commit(witness::Simulation &device, const witness::RunConfiguration &configuration,
                     const char *events, const char *tracking) {
    assert(configuration.cycles == 1);
    witness::configure_run(device, configuration);
    witness::write_register(device, 0x38, 1);
    assert(device.wait_interrupt(1000000));
    const auto ready = device.time();
    const std::uint64_t low = witness::read_register(device, 0x9c);
    const auto generation =
        low | (static_cast<std::uint64_t>(witness::read_register(device, 0xa0)) << 32);
    device.advance(static_cast<std::uint64_t>(configuration.period_ticks) * 10 - 1250 -
                   (device.time() - ready));
    witness::RunOutput output(events, tracking);
    witness_pid_state state{};
    witness_pid_reset(&state);
    witness::RunResult result;
    std::uint32_t previous = 0;
    bool observed = false;
    witness::control_sample(device, configuration, state, output, result, generation, previous,
                            observed);
    assert(result.samples == 1 && observed && previous == 0);
    assert(witness::read_register(device, 4) & 4);
    while (!(witness::read_register(device, 0x90) & 8))
        witness::drain_available(device, output, result);
    assert(result.records == 3 && witness::read_register(device, 0x34) == 1);
    output.finish();
}

/** Cross real configured timer bounds through an acquisition callback's public clock. */
void timed_out_run(witness::Simulation &device, const witness::RunConfiguration &configuration,
                   const std::string &scenario, const char *events, const char *tracking) {
    witness::RunOutput output(events, tracking);
    unsigned starts = 0, checks = 0, finishes = 0;
    const auto limit =
        static_cast<std::uint64_t>(configuration.period_ticks) * 10 * configuration.cycles +
        1000000000;
    const witness::RunHooks hooks{[&] { ++starts; },
                                  [&] {
                                      ++checks;
                                      if (scenario == "run_timeout" && checks == 1)
                                          device.advance(limit + 1);
                                      if (scenario == "final_drain_timeout" && checks == 3) {
                                          assert(witness::read_register(device, 4) & 4);
                                          assert(!(witness::read_register(device, 0x90) & 8));
                                          device.advance(1000000001);
                                      }
                                  },
                                  [&] { ++finishes; }};
    refusal([&] { witness::execute_run(device, configuration, output, &hooks); },
            scenario == "run_timeout" ? "configured run completion timed out"
                                      : "final record drain timed out");
    assert(starts == 1 && finishes == 0);
    assert(checks == (scenario == "run_timeout" ? 1U : 3U));
    assert(witness::read_register(device, 4) & 4);
    assert(witness::read_register(device, 0x34) == configuration.cycles);
    output.finish();
}

/** Exercise repeated real samples and malformed public API configuration inputs. */
void sample_refusal(witness::Simulation &device, witness::RunConfiguration configuration,
                    const std::string &scenario, const char *events, const char *tracking) {
    witness::configure_run(device, configuration);
    if (scenario != "unstarted") {
        witness::write_register(device, 0x38, 1);
        assert(device.wait_interrupt(1000000));
    } else {
        assert(witness::read_register(device, 0x38) == 0);
        assert((witness::read_register(device, 4) & 12) == 0);
    }
    const std::uint64_t low = witness::read_register(device, 0x9c);
    const auto generation =
        low | (static_cast<std::uint64_t>(witness::read_register(device, 0xa0)) << 32);
    witness::RunOutput output(events, tracking);
    witness_pid_state state{};
    witness_pid_reset(&state);
    witness::RunResult result;
    std::uint32_t previous = 0;
    bool observed = false;
    const auto sample = [&] {
        witness::control_sample(device, configuration, state, output, result, generation, previous,
                                observed);
    };
    if (scenario == "unstarted") {
        refusal(sample, "register read refused at 0");
        assert(result.samples == 0 && !observed && previous == 0);
        assert(state.integral == 0 && state.derivative == 0 && !state.initialized);
        assert(witness::read_register(device, 0x38) == 0);
        assert((witness::read_register(device, 4) & 12) == 0);
    } else if (scenario == "duplicate") {
        sample();
        assert(result.samples == 1);
        refusal(sample, "duplicate or out-of-order sample cycle");
        assert(result.samples == 1);
    } else if (scenario == "out_of_range") {
        configuration.cycles = 0;
        refusal(sample, "duplicate or out-of-order sample cycle");
        assert(result.samples == 0 && !observed);
    } else {
        configuration.coefficients.kp = -1;
        configuration.lqr = scenario == "invalid_lqr";
        refusal(sample, "native controller refused validated coefficients");
        assert(result.samples == 0);
        assert(state.integral == 0 && state.derivative == 0 && !state.initialized);
    }
    output.finish();
    if (scenario == "unstarted") {
        const auto recovered_events = std::string(events) + ".recovery";
        const auto recovered_tracking = std::string(tracking) + ".recovery";
        witness::RunOutput recovered(recovered_events.c_str(), recovered_tracking.c_str());
        const auto healthy = witness::execute_run(device, configuration, recovered);
        assert(healthy.samples == configuration.cycles && healthy.records > 0);
        assert(healthy.misses == 0 && healthy.overflow == 0 && !healthy.safe);
    }
}

/** Re-submit actual captured bytes and sample fields to the closed public output API. */
void closed_output(witness::RunOutput &output, const char *events, const char *tracking) {
    refusal([&] { output.finish(); }, "run output is closed");
    std::ifstream binary(events, std::ios::binary);
    std::array<unsigned char, 16> bytes{};
    binary.read(reinterpret_cast<char *>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
    assert(binary.gcount() == 16);
    const auto copy_path = std::string(events) + ".copy";
    witness::ExclusiveOutput copy(copy_path.c_str(), witness::OutputFormat::binary,
                                  "cannot create event copy");
    assert(copy.is_open());
    assert(std::fwrite(bytes.data(), 1, bytes.size(), copy.stream("event copy is closed")) ==
           bytes.size());
    assert(copy.close("event copy is closed") == 0);
    assert(!copy.is_open());
    refusal([&] { copy.close("event copy is closed"); }, "event copy is closed");
    refusal([&] { copy.stream("event copy is closed"); }, "event copy is closed");
    refusal(
        [&] {
            witness::ExclusiveOutput existing(copy_path.c_str(), witness::OutputFormat::binary,
                                              "cannot create event copy");
        },
        "cannot create event copy");
    std::array<std::uint32_t, 4> words{};
    for (std::size_t word = 0; word < 4; ++word)
        for (unsigned byte = 0; byte < 4; ++byte)
            words[word] |= static_cast<std::uint32_t>(bytes[word * 4 + byte]) << (byte * 8);
    refusal([&] { output.event(words); }, "event output is closed");
    std::ifstream trace(tracking);
    std::string line;
    std::getline(trace, line);
    std::getline(trace, line);
    std::replace(line.begin(), line.end(), ',', ' ');
    std::istringstream fields(line);
    witness_command command{};
    std::int32_t reference = 0, position = 0, velocity = 0;
    unsigned clipped = 0, held = 0, submitted = 0;
    std::uint64_t ticks = 0, generation = 0, work = 0;
    fields >> command.cycle >> reference >> position >> velocity >> command.command >>
        command.integral >> command.derivative >> clipped >> held >> submitted >> ticks >>
        generation >> work;
    assert(fields && submitted == 1);
    command.clipped = clipped != 0;
    command.integral_held = held != 0;
    refusal(
        [&] {
            output.sample(reference, position, velocity, command, submitted != 0, ticks, generation,
                          work);
        },
        "tracking output is closed");
}

/** Preserve real EFBIG failures while restoring the cap before profiling completion. */
void output_limit(witness::Simulation &device, const witness::RunConfiguration &configuration,
                  const std::string &scenario, const char *events, const char *tracking) {
    const rlim_t maximum = scenario == "header_limit" ? 32 : scenario == "finish_limit" ? 192 : 512;
    const char *message = scenario == "header_limit"   ? "cannot write tracking header"
                          : scenario == "event_limit"  ? "cannot write event record"
                          : scenario == "sample_limit" ? "cannot write tracking sample"
                                                       : "cannot finish run output";
    ScopedOutputLimit limit(maximum);
    refusal(
        [&] {
            witness::RunOutput output(events, tracking);
            if (scenario != "header_limit")
                witness::execute_run(device, configuration, output);
        },
        message);
}

/** Exercise lifecycle refusals and acquisition callbacks through production RTL. */
int main(int argc, char **argv) {
    if (argc != 5)
        return 1;
    const auto configuration = witness::read_configuration(argv[2]);
    witness::Simulation device;
    const std::string scenario = argv[1];
    if (scenario == "run_timeout" || scenario == "final_drain_timeout") {
        timed_out_run(device, configuration, scenario, argv[3], argv[4]);
    } else if (scenario == "commit_boundary") {
        boundary_commit(device, configuration, argv[3], argv[4]);
    } else if (scenario == "period_mismatch") {
        assert(witness::read_register(device, 0x40) == configuration.period_ticks);
        auto mismatched = configuration;
        ++mismatched.period_ticks;
        refusal([&] { witness::configure_run(device, mismatched); },
                "compiled register ABI, Q format or period mismatch");
        assert(witness::read_register(device, 0x38) == 0);
        assert(witness::read_register(device, 0x40) == configuration.period_ticks);
        witness::RunOutput output(argv[3], argv[4]);
        const auto healthy = witness::execute_run(device, configuration, output);
        assert(healthy.samples == configuration.cycles && healthy.records > 0);
        assert(healthy.misses == 0 && healthy.overflow == 0 && !healthy.safe);
    } else if (scenario.compare(0, 7, "config_") == 0) {
        configuration_refusal(device, configuration, scenario, argv[3], argv[4]);
    } else if (scenario.compare(0, 9, "metadata_") == 0) {
        metadata_refusal(device, configuration, scenario, argv[2], argv[3], argv[4]);
    } else if (scenario == "read") {
        refusal([&] { witness::read_register(device, 0xfc); }, "register read refused at 252");
        assert(witness::read_register(device, 0x7c) == 1);
        refusal([&] { witness::read_register(device, 0x0c); }, "register read refused at 12");
        assert(witness::read_register(device, 0x08) > 0);
        assert(witness::read_register(device, 0x0c) == 0);
    } else if (scenario == "write") {
        refusal([&] { witness::write_register(device, 0x7c, 0); }, "register write refused at 124");
        assert(witness::read_register(device, 0x7c) == 1);
    } else if (scenario == "active" || scenario == "unread" || scenario == "recover") {
        witness::configure_run(device, configuration);
        witness::write_register(device, 0x38, 1);
        if (scenario == "active") {
            assert(!(witness::read_register(device, 0x98) & 8));
            refusal([&] { witness::configure_run(device, configuration); },
                    "cannot reset an active run");
        } else {
            device.advance(static_cast<std::uint64_t>(configuration.period_ticks) * 10 * 3);
            assert(witness::read_register(device, 4) & 4);
            assert(witness::read_register(device, 0x98) & 8);
            assert((witness::read_register(device, 0x90) & 7) != 4);
            refusal([&] { witness::configure_run(device, configuration); },
                    "unread previous run records prevent reset");
            assert(witness::read_register(device, 0x90) & 1);
            if (scenario == "recover") {
                witness::RunOutput output(argv[3], argv[4]);
                witness::RunResult result;
                while (!(witness::read_register(device, 0x90) & 8))
                    witness::drain_available(device, output, result);
                assert(result.records > 0);
                output.finish();
                witness::configure_run(device, configuration);
                assert((witness::read_register(device, 0x98) & 7) == 7);
                assert((witness::read_register(device, 0x90) & 7) == 4);
            }
        }
    } else if (scenario == "unstarted" || scenario == "duplicate" || scenario == "out_of_range" ||
               scenario == "invalid_pid" || scenario == "invalid_lqr") {
        sample_refusal(device, configuration, scenario, argv[3], argv[4]);
    } else if (scenario == "header_limit" || scenario == "event_limit" ||
               scenario == "sample_limit" || scenario == "finish_limit") {
        output_limit(device, configuration, scenario, argv[3], argv[4]);
    } else if (scenario == "hooks" || scenario == "closed" || scenario == "final_drain" ||
               scenario == "final_drain_no_hooks") {
        witness::RunOutput output(argv[3], argv[4]);
        unsigned starts = 0, checks = 0, finishes = 0;
        const witness::RunHooks hooks{[&] {
                                          assert(checks == 0 && finishes == 0);
                                          ++starts;
                                      },
                                      [&] {
                                          assert(starts == 1 && finishes == 0);
                                          ++checks;
                                      },
                                      [&] {
                                          assert(starts == 1 && checks > 0);
                                          assert(witness::read_register(device, 0x90) & 8);
                                          ++finishes;
                                      }};
        const auto result = witness::execute_run(
            device, configuration, output, scenario == "final_drain_no_hooks" ? nullptr : &hooks);
        if (scenario == "final_drain_no_hooks")
            assert(starts == 0 && checks == 0 && finishes == 0);
        else
            assert(starts == 1 && checks > 0 && finishes == 1);
        if (scenario == "final_drain" || scenario == "final_drain_no_hooks") {
            assert(result.samples == 1 && result.records == 20);
            assert(result.misses == 8 && result.overflow == 0 && result.safe);
        } else {
            assert(result.samples == configuration.cycles && result.records > 0);
            assert(result.misses == 0 && result.overflow == 0 && !result.safe);
        }
        if (scenario == "closed")
            closed_output(output, argv[3], argv[4]);
    } else
        return 1;
    std::cout << "verified " << scenario << '\n';
#ifdef WITNESS_RTL_COVERAGE
    const std::string profile = std::string(argv[3]) + ".coverage.dat";
    VerilatedCov::write(profile.c_str());
#endif
}
