// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — typed PAC1934 configuration refusal before IIO selection

#include "../../runtime/linux/pac1934_device.h"
#include <cassert>
#include <iostream>
#include <stdexcept>

/** Submit malformed public structures to the real PAC1934 constructor. */
int main(int argc, char **argv) {
    if (argc != 3) return 1;
    auto configuration = witness::read_power_configuration(argv[2]);
    const std::string scenario = argv[1];
    const char *message = "power configuration integer outside range";
    if (scenario == "device") { configuration.device = "../devices"; message = "invalid power ABI, IIO identity or kernel release"; }
    else if (scenario == "device_prefix" || scenario == "device_suffix") {
        configuration.device = scenario == "device_prefix" ? "wrongdevice999" : "iio:devicebad";
        message = "invalid power ABI, IIO identity or kernel release";
    }
    else if (scenario == "kernel") { configuration.kernel_release = "bad/kernel"; message = "invalid power ABI, IIO identity or kernel release"; }
    else if (scenario == "kernel_empty" || scenario == "kernel_long") {
        configuration.kernel_release = scenario == "kernel_empty" ? "" : std::string(129, 'a');
        message = "invalid power ABI, IIO identity or kernel release";
    }
    else if (scenario == "period_low") configuration.period_ns = 49999999;
    else if (scenario == "period_high") configuration.period_ns = 60000000001;
    else if (scenario == "span_zero") configuration.maximum_read_ns = 0;
    else if (scenario == "span_high") configuration.maximum_read_ns = configuration.period_ns + 1;
    else if (scenario == "worker") configuration.worker_cpu = -1;
    else if (scenario == "rate") { configuration.sample_rate = 128; message = "unsupported PAC1934 sample rate"; }
    else if (scenario == "rail") { configuration.rails[0].name = "VDDA"; message = "power rails must be VDD VDD25 VDDA25 VDDA in order"; }
    else if (scenario == "channel_zero") configuration.rails[0].channel = 0;
    else if (scenario == "channel_high") configuration.rails[0].channel = 5;
    else if (scenario == "shunt_zero") configuration.rails[0].shunt_microohms = 0;
    else if (scenario == "shunt_high") configuration.rails[0].shunt_microohms = 1000000001;
    else if (scenario == "label") { configuration.rails[0].label = "label,comma"; message = "invalid power label or duplicate channel"; }
    else if (scenario == "label_empty" || scenario == "label_long") {
        configuration.rails[0].label = scenario == "label_empty" ? "" : std::string(129, 'a');
        message = "invalid power label or duplicate channel";
    }
    else if (scenario == "duplicate") { configuration.rails[1].channel = configuration.rails[0].channel; message = "invalid power label or duplicate channel"; }
    else if (scenario == "rate_8" || scenario == "rate_64" || scenario == "rate_256" || scenario == "rate_1024") {
        configuration.sample_rate = scenario == "rate_8" ? 8 : scenario == "rate_64" ? 64 : scenario == "rate_256" ? 256 : 1024;
        message = nullptr;
    }
    else return 1;
    bool refused = false;
    try { witness::Pac1934Device device(configuration); }
    catch (const std::runtime_error &error) {
        refused = true;
        const auto text = std::string(error.what());
        const bool expected = message ? text == message : text.find("cannot make canonical path") != std::string::npos;
        if (!expected) std::cerr << text << '\n';
        assert(expected);
    }
    assert(refused);
    std::cout << "verified " << scenario << '\n';
}
