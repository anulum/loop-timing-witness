// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — PAC1934 IIO acquisition and identity checks

#include "pac1934_device.h"
#include <charconv>
#include <cstdio>
#include <filesystem>
#include <fcntl.h>
#include <stdexcept>
#include <sys/utsname.h>
#include <unistd.h>

namespace witness {
namespace {
/** Reproduce the selected kernel IIO fractional scale's nine-decimal truncation. */
std::string fractional(std::uint64_t numerator, std::uint64_t denominator) {
    const auto nano = numerator * 1000000000 / denominator;
    std::array<char, 64> buffer{};
    std::snprintf(buffer.data(), buffer.size(), "%llu.%09llu",
        static_cast<unsigned long long>(nano / 1000000000), static_cast<unsigned long long>(nano % 1000000000));
    return buffer.data();
}
/** Validate nonnegative integer raw readings with their actual ABI bounds. */
void raw_value(const std::string &text, std::uint64_t maximum) {
    std::uint64_t value = 0;
    const auto parsed = std::from_chars(text.data(), text.data() + text.size(), value);
    if (parsed.ec != std::errc{} || parsed.ptr != text.data() + text.size() || value > maximum)
        throw std::runtime_error("PAC1934 raw reading is invalid or outside ABI bounds");
}
}
std::string Pac1934Device::attribute(const std::string &name) const {
    const int fd = openat(directory, name.c_str(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) throw std::runtime_error("cannot open actual PAC1934 attribute: " + name);
    std::array<char, 4096> data{};
    const auto count = ::read(fd, data.data(), data.size());
    const int closed = ::close(fd);
    if (count <= 0 || count == static_cast<ssize_t>(data.size()) || closed != 0)
        throw std::runtime_error("cannot read complete PAC1934 attribute: " + name);
    std::string result(data.data(), static_cast<std::size_t>(count));
    if (!result.empty() && result.back() == '\n') result.pop_back();
    if (result.empty() || result.find_first_of("\n\r") != std::string::npos || result.find('\0') != std::string::npos)
        throw std::runtime_error("invalid PAC1934 attribute text: " + name);
    return result;
}
Pac1934Device::Pac1934Device(const PowerConfiguration &config) : configuration(config) {
    validate_power_configuration(configuration);
    struct utsname kernel{};
    if (uname(&kernel) != 0 || configuration.kernel_release != kernel.release)
        throw std::runtime_error("actual kernel release differs from power configuration");
    const auto path = std::filesystem::path("/sys/bus/iio/devices") / configuration.device;
    const auto actual = std::filesystem::canonical(path);
    if (actual.string().rfind("/sys/devices/", 0) != 0)
        throw std::runtime_error("PAC1934 device does not resolve into kernel devices");
    directory = open(actual.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (directory < 0) throw std::runtime_error("cannot open actual PAC1934 device directory");
    try {
        if (fstat(directory, &identity) != 0) throw std::runtime_error("cannot identify PAC1934 directory");
        verify();
    } catch (...) { ::close(directory); directory = -1; throw; }
}
Pac1934Device::~Pac1934Device() { if (directory >= 0) ::close(directory); }
void Pac1934Device::verify() const {
    const auto path = std::filesystem::path("/sys/bus/iio/devices") / configuration.device;
    const auto actual = std::filesystem::canonical(path);
    struct stat current{};
    if (stat(actual.c_str(), &current) != 0 || current.st_dev != identity.st_dev || current.st_ino != identity.st_ino ||
        std::filesystem::canonical(actual.parent_path() / "driver").filename() != "pac1934" ||
        attribute("name") != "pac1934" || attribute("sampling_frequency") != std::to_string(configuration.sample_rate))
        throw std::runtime_error("PAC1934 device, driver or sample-rate identity changed");
    for (const auto &rail : configuration.rails) {
        const auto channel = std::to_string(rail.channel);
        if (attribute("in_voltage" + channel + "_label") != rail.label + "_VBUS_" + channel ||
            attribute("in_current" + channel + "_label") != rail.label + "_IBUS_" + channel ||
            attribute("in_energy" + channel + "_label") != rail.label + "_ENERGY_" + channel ||
            attribute("in_energy" + channel + "_en") != "1" ||
            attribute("in_shunt_resistor" + channel) != std::to_string(rail.shunt_microohms))
            throw std::runtime_error("PAC1934 rail labels, shunts or accumulator enable differs");
        read(rail, "voltage", true); read(rail, "current", true); read(rail, "energy", true);
    }
}
std::string Pac1934Device::read(const PowerRail &rail, const std::string &quantity, bool scale) const {
    if (quantity != "voltage" && quantity != "current" && quantity != "energy")
        throw std::runtime_error("unsupported PAC1934 acquisition quantity");
    bool configured = false;
    for (const auto &known : configuration.rails)
        if (rail.name == known.name && rail.label == known.label &&
            rail.channel == known.channel && rail.shunt_microohms == known.shunt_microohms)
            configured = true;
    if (!configured) throw std::runtime_error("PAC1934 acquisition rail differs from configuration");
    const auto result = attribute("in_" + quantity + std::to_string(rail.channel) + (scale ? "_scale" : "_raw"));
    if (scale) {
        const auto expected = quantity == "voltage" ? fractional(32000, 65536) :
            fractional(quantity == "current" ? 1525 : 11921, rail.shunt_microohms);
        if (result != expected) throw std::runtime_error("PAC1934 unsigned scale/shunt contract differs");
    } else raw_value(result, quantity == "energy" ? 214748364799999999ULL : 65535);
    return result;
}
} // namespace witness
