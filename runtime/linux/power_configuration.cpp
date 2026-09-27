// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — PAC1934 configuration parser

#include "power_configuration.h"
#include <charconv>
#include <fstream>
#include <stdexcept>

namespace witness {
namespace {
/** Bound a whole unsigned token before conversion or narrowing. */
std::uint64_t value(std::istream &input, std::uint64_t low, std::uint64_t high) {
    std::string token;
    std::uint64_t result = 0;
    if (!(input >> token)) throw std::runtime_error("incomplete power configuration");
    const auto parsed = std::from_chars(token.data(), token.data() + token.size(), result);
    if (parsed.ec != std::errc{} || parsed.ptr != token.data() + token.size() || result < low || result > high)
        throw std::runtime_error("power configuration integer outside range");
    return result;
}
/** Keep kernel/label tokens bounded and safe for exact text journal fields. */
bool identifier(const std::string &text) {
    return !text.empty() && text.size() <= 128 &&
        text.find_first_not_of("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-+~") == std::string::npos;
}
/** Validate identity before the parser consumes numeric or rail fields. */
void validate_identity(const PowerConfiguration &configuration) {
    if (configuration.device.size() <= 10 || configuration.device.substr(0, 10) != "iio:device" ||
        configuration.device.substr(10).find_first_not_of("0123456789") != std::string::npos ||
        !identifier(configuration.kernel_release))
        throw std::runtime_error("invalid power ABI, IIO identity or kernel release");
}
}
void validate_power_configuration(const PowerConfiguration &configuration) {
    validate_identity(configuration);
    if (configuration.period_ns < 50000000 || configuration.period_ns > 60000000000 ||
        !configuration.maximum_read_ns || configuration.maximum_read_ns > configuration.period_ns ||
        configuration.worker_cpu < 0)
        throw std::runtime_error("power configuration integer outside range");
    if (configuration.sample_rate != 8 && configuration.sample_rate != 64 &&
        configuration.sample_rate != 256 && configuration.sample_rate != 1024)
        throw std::runtime_error("unsupported PAC1934 sample rate");
    const std::array<std::string, 4> names = {"VDD", "VDD25", "VDDA25", "VDDA"};
    std::array<bool, 4> used{};
    for (std::size_t index = 0; index < configuration.rails.size(); ++index) {
        const auto &rail = configuration.rails[index];
        if (rail.name != names[index]) throw std::runtime_error("power rails must be VDD VDD25 VDDA25 VDDA in order");
        if (rail.channel < 1 || rail.channel > 4 || !rail.shunt_microohms || rail.shunt_microohms > 1000000000)
            throw std::runtime_error("power configuration integer outside range");
        if (!identifier(rail.label) || used[rail.channel - 1])
            throw std::runtime_error("invalid power label or duplicate channel");
        used[rail.channel - 1] = true;
    }
}
PowerConfiguration read_power_configuration(const std::string &path) {
    std::ifstream input(path);
    PowerConfiguration result{};
    std::string abi, extra;
    if (!(input >> abi >> result.device >> result.kernel_release) || abi != "pac1934-iio-mchp-v1")
        throw std::runtime_error("invalid power ABI, IIO identity or kernel release");
    validate_identity(result);
    result.period_ns = value(input, 50000000, 60000000000);
    result.maximum_read_ns = value(input, 1, result.period_ns);
    result.worker_cpu = static_cast<int>(value(input, 0, INT32_MAX));
    result.sample_rate = static_cast<unsigned>(value(input, 8, 1024));
    for (std::size_t index = 0; index < result.rails.size(); ++index) {
        auto &rail = result.rails[index];
        if (!(input >> rail.name)) throw std::runtime_error("power rails must be VDD VDD25 VDDA25 VDDA in order");
        rail.channel = static_cast<unsigned>(value(input, 1, 4));
        rail.shunt_microohms = static_cast<std::uint32_t>(value(input, 1, 1000000000));
        if (!(input >> rail.label))
            throw std::runtime_error("invalid power label or duplicate channel");
    }
    validate_power_configuration(result);
    if (input >> extra || !input.eof()) throw std::runtime_error("extra or unreadable power configuration");
    return result;
}
} // namespace witness
