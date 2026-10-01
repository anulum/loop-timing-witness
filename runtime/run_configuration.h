// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — native run configuration contract

/** @file run_configuration.h
 * native run configuration contract.
 */

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
/** @var witness::RunConfiguration::lqr
 * True selects LQR; false selects PID.
 */
/** @var witness::RunConfiguration::cycles
 * Requested finite number of controller input cycles.
 */
/** @var witness::RunConfiguration::period_ticks
 * Requested controller period in fabric timebase ticks.
 */
/** @var witness::RunConfiguration::coefficients
 * Immutable signed raw Q8.24 gains and saturation bounds.
 */
/** @var witness::RunConfiguration::reference_mode
 * Fabric reference-generator selection.
 */
/** @var witness::RunConfiguration::amplitude
 * Reference-generator amplitude in signed raw Q8.24.
 */
/** @var witness::RunConfiguration::offset
 * Reference-generator offset in signed raw Q8.24.
 */
/** @var witness::RunConfiguration::ramp
 * Reference-generator ramp increment in signed raw Q8.24.
 */
/** @var witness::RunConfiguration::phase
 * Reference-generator initial phase word.
 */
/** @var witness::RunConfiguration::fault_enabled
 * Whether the configured fault injector is enabled.
 */
/** @var witness::RunConfiguration::fault_kind
 * Fabric fault-injector operation identifier.
 */
/** @var witness::RunConfiguration::fault_cycle
 * Input cycle at which injection is requested.
 */
/** @var witness::RunConfiguration::fault_periods
 * Number of configured periods for the injected fault.
 */
/** @var witness::RunConfiguration::overload_iterations
 * Requested native overload checksum-loop iteration count.
 */
/** @var witness::RunConfiguration::modeled_overload_ns
 * Explicit simulated overload duration in nanoseconds.
 */

#endif
