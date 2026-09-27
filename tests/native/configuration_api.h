// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — actual native configuration API refusals

#ifndef WITNESS_CONFIGURATION_API_TEST_H
#define WITNESS_CONFIGURATION_API_TEST_H

#include "../../runtime/rtl/simulation.h"
#include "../../runtime/run_control.h"
#include <string>
#include <cassert>

/** Refuse malformed public configuration before changing actual RTL registers. */
void configuration_refusal(witness::Simulation &device, witness::RunConfiguration configuration,
                            const std::string &scenario, const char *events, const char *tracking) {
    const auto previous_events = std::string(events) + ".previous";
    const auto previous_trace = std::string(tracking) + ".previous";
    {
        witness::RunOutput initial(previous_events.c_str(), previous_trace.c_str());
        const auto prior = witness::execute_run(device, configuration, initial);
        assert(prior.samples == configuration.cycles && prior.records > 0 && !prior.safe);
    }
    const std::array<std::uint8_t, 10> addresses{4, 0x38, 0x3c, 0x44, 0x48, 0x4c, 0x50, 0x54, 0x9c, 0xa0};
    std::array<std::uint32_t, 10> before{};
    for (std::size_t index = 0; index < addresses.size(); ++index)
        before[index] = witness::read_register(device, addresses[index]);
    assert((before[0] & 4) && before[1] == 1 && before[8] > 0);
    auto invalid = configuration;
    const char *message = "invalid cycles, period or controller coefficients";
    if (scenario == "config_cycles_zero") invalid.cycles = 0;
    else if (scenario == "config_period_zero") invalid.period_ticks = 0;
    else if (scenario == "config_coefficients") invalid.coefficients.kp = -1;
    else if (scenario == "config_reference" || scenario == "config_phase" || scenario == "config_kind") {
        message = "invalid reference mode, phase or fault kind";
        if (scenario == "config_reference") invalid.reference_mode = 3;
        else if (scenario == "config_phase") invalid.phase = 16;
        else invalid.fault_kind = 4;
    } else if (scenario == "config_duration") {
        invalid.cycles = invalid.period_ticks = UINT32_MAX;
        message = "configured duration exceeds the nanosecond run timer";
    } else {
        message = "invalid fault schedule or overload configuration";
        if (scenario == "config_disabled_kind") invalid.fault_kind = 1;
        else if (scenario == "config_disabled_cycle") invalid.fault_cycle = 1;
        else if (scenario == "config_disabled_periods") invalid.fault_periods = 1;
        else if (scenario == "config_unused_work") invalid.overload_iterations = 1;
        else if (scenario == "config_unused_delay") invalid.modeled_overload_ns = 1;
        else {
            invalid.fault_enabled = true;
            invalid.fault_periods = 1;
            if (scenario == "config_fault_cycle") invalid.fault_cycle = invalid.cycles;
            else if (scenario == "config_fault_periods") invalid.fault_periods = 0;
            else if (scenario == "config_work_bound") { invalid.fault_kind = 3; invalid.overload_iterations = 10000001; }
            else if (scenario == "config_delay_bound") { invalid.fault_kind = 3; invalid.modeled_overload_ns = 10000001; }
            else throw std::runtime_error("unknown configuration test scenario");
        }
    }
    refusal([&] { witness::configure_run(device, invalid); }, message);
    for (std::size_t index = 0; index < addresses.size(); ++index)
        assert(witness::read_register(device, addresses[index]) == before[index]);
    witness::RunOutput output(events, tracking);
    const auto result = witness::execute_run(device, configuration, output);
    assert(result.samples == configuration.cycles && result.misses == 0 && !result.safe);
}
#endif
