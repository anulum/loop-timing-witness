// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — native configuration parsing and semantic checks

#include "run_configuration.h"
#include "refusal.h"
#include <charconv>
#include <fstream>
#include <limits>
#include <stdexcept>

namespace witness {
namespace {
/** Parse a whole signed decimal token before range checking or narrowing. */
std::int64_t integer(std::istream &stream, std::int64_t minimum, std::int64_t maximum) {
    std::string token;
    if (!(stream >> token))
        throw witness::RuntimeRefused("incomplete run configuration");
    const auto digits = token.substr(token[0] == '-' || token[0] == '+' ? 1 : 0);
    if (digits.empty() || digits.find_first_not_of("0123456789") != std::string::npos)
        throw witness::RuntimeRefused("invalid configuration integer");
    std::int64_t value = 0;
    const auto *begin = token.data() + (token[0] == '+' ? 1 : 0);
    const auto parsed = std::from_chars(begin, token.data() + token.size(), value);
    if (parsed.ec != std::errc{} || value < minimum || value > maximum)
        throw witness::RuntimeRefused("configuration integer outside range");
    return value;
}
/** Read raw Q8.24 signed data without unsigned conversion. */
std::int32_t fixed(std::istream &stream) {
    return static_cast<std::int32_t>(integer(stream, INT32_MIN, INT32_MAX));
}
/** Read a nonnegative configuration field with its explicit upper bound. */
std::uint32_t field(std::istream &stream, std::uint32_t maximum = UINT32_MAX) {
    return static_cast<std::uint32_t>(integer(stream, 0, maximum));
}
/** Keep early parser diagnostics and public API core validation identical. */
void validate_core(const RunConfiguration &configuration) {
    if (!configuration.cycles || !configuration.period_ticks ||
        !witness_coefficients_valid(&configuration.coefficients))
        throw witness::RuntimeRefused("invalid cycles, period or controller coefficients");
}
} // namespace

void validate_configuration(const RunConfiguration &configuration) {
    validate_core(configuration);
    if (configuration.reference_mode > 2 || configuration.phase > 15 ||
        configuration.fault_kind > 3)
        throw witness::RuntimeRefused("invalid reference mode, phase or fault kind");
    if ((configuration.fault_enabled &&
         (configuration.fault_cycle >= configuration.cycles || !configuration.fault_periods)) ||
        (!configuration.fault_enabled &&
         (configuration.fault_kind || configuration.fault_cycle || configuration.fault_periods)) ||
        ((!configuration.fault_enabled || configuration.fault_kind != 3) &&
         (configuration.overload_iterations || configuration.modeled_overload_ns)) ||
        configuration.overload_iterations > 10000000 ||
        configuration.modeled_overload_ns > 10000000)
        throw witness::RuntimeRefused("invalid fault schedule or overload configuration");
    const auto ticks =
        static_cast<std::uint64_t>(configuration.cycles) * configuration.period_ticks;
    if (ticks > (UINT64_MAX - 1000000000) / 10)
        throw witness::RuntimeRefused("configured duration exceeds the nanosecond run timer");
}

RunConfiguration read_configuration(const std::string &path) {
    std::ifstream input(path);
    if (!input)
        throw witness::RuntimeRefused("cannot open run configuration");
    RunConfiguration result{};
    std::string mode, fault, extra;
    input >> mode;
    if (mode != "pid" && mode != "lqr")
        throw witness::RuntimeRefused("controller must be pid or lqr");
    result.lqr = mode == "lqr";
    result.cycles = field(input);
    result.period_ticks = field(input);
    result.coefficients = {fixed(input), fixed(input), fixed(input), fixed(input),
                           fixed(input), fixed(input), fixed(input), fixed(input),
                           fixed(input), fixed(input), fixed(input)};
    validate_core(result);
    result.reference_mode = field(input, 2);
    result.amplitude = fixed(input);
    result.offset = fixed(input);
    result.ramp = fixed(input);
    result.phase = field(input, 15);
    input >> fault;
    if (fault != "none" && fault != "drop" && fault != "delay" && fault != "freeze" &&
        fault != "overload")
        throw witness::RuntimeRefused("unknown fault kind");
    result.fault_enabled = fault != "none";
    result.fault_kind = fault == "delay" ? 1 : fault == "freeze" ? 2 : fault == "overload" ? 3 : 0;
    result.fault_cycle = field(input);
    result.fault_periods = field(input);
    result.overload_iterations = field(input, 10000000);
    result.modeled_overload_ns = field(input, 10000000);
    validate_configuration(result);
    if (input >> extra || !input.eof())
        throw witness::RuntimeRefused("extra or unreadable run configuration");
    return result;
}
} // namespace witness
