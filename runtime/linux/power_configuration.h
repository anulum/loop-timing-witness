// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — explicit PAC1934 acquisition configuration

#ifndef WITNESS_POWER_CONFIGURATION_H
#define WITNESS_POWER_CONFIGURATION_H
#include <array>
#include <cstdint>
#include <string>

namespace witness {
/** Operator-supplied rail mapping and unsigned-channel shunt contract. */
struct PowerRail { std::string name, label; unsigned channel; std::uint32_t shunt_microohms; };
/** Explicit kernel/interface identity, polling bounds and separate logging CPU. */
struct PowerConfiguration {
    std::string device, kernel_release;
    std::uint64_t period_ns, maximum_read_ns;
    int worker_cpu;
    unsigned sample_rate;
    std::array<PowerRail, 4> rails;
};
/** Refuse malformed public acquisition structures before device or journal access. */
void validate_power_configuration(const PowerConfiguration &configuration);
/** Read and validate the complete acquisition format; no inferred board/shunt defaults. */
PowerConfiguration read_power_configuration(const std::string &path);
} // namespace witness
#endif
