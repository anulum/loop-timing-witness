// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — native run configuration contract

#ifndef WITNESS_RUN_CONFIGURATION_H
#define WITNESS_RUN_CONFIGURATION_H
#include <cstdint>
#include <string>
extern "C" {
#include "../controllers/c/witness_controller.h"
}
namespace witness {
/** Fully supplied run configuration; raw coefficients and reference use Q8.24. */
struct RunConfiguration {
    bool lqr;
    std::uint32_t cycles, period_ticks;
    witness_coefficients coefficients;
    std::uint32_t reference_mode;
    std::int32_t amplitude, offset, ramp;
    std::uint32_t phase;
    bool fault_enabled;
    std::uint32_t fault_kind, fault_cycle, fault_periods;
    std::uint32_t overload_iterations, modeled_overload_ns;
};
/** Validate a public configuration before reset, register writes or run duration arithmetic. */
void validate_configuration(const RunConfiguration &configuration);
/** Read the complete whitespace configuration, rejecting extras and invalid bounds. */
RunConfiguration read_configuration(const std::string &path);
} // namespace witness
#endif
