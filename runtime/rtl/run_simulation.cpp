// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — native run controller over in-process production RTL

#include "simulation.h"
#include "../run_control.h"
#include "../run_metadata.h"
#include <iostream>

/** Execute the native controller and preserve actual RTL events and raw tracking. */
int main(int argc, char **argv) {
    if (argc < 4) {
        std::cerr
            << "usage: run_simulation configuration events.bin tracking_raw.csv [--metadata file] [--cpu N] [--scheduler normal|fifo] [--priority N]\n";
        return 1;
    }
    try {
        const auto options = witness::read_run_options(argc, argv, 4);
        if (options.power_configuration)
            throw std::runtime_error("PAC1934 acquisition is physical UIO-only");
        const auto original =
            options.metadata ? witness::file_digest(argv[1]) : witness::FileDigest{};
        const auto configuration = witness::read_configuration(argv[1]);
        if (options.metadata)
            witness::verify_digest(argv[1], original);
        const auto policy = witness::apply_host_policy(options);
        witness::Simulation device;
        witness::RunOutput output(argv[2], argv[3]);
        const auto result = witness::execute_run(device, configuration, output);
        std::vector<witness::ArtifactDigest> artifacts;
        if (options.metadata) {
            witness::verify_digest(argv[1], original);
            artifacts = {{"configuration", original},
                         {"events", witness::file_digest(argv[2])},
                         {"tracking_raw", witness::file_digest(argv[3])}};
        }
        if (options.metadata)
            witness::write_run_metadata(options.metadata, configuration, result,
                                        witness::read_register(device, 0x6c) != 0, "rtl_simulation",
                                        options, policy, artifacts);
        std::cout << "simulation_only samples=" << result.samples << " records=" << result.records
                  << " misses=" << result.misses << " overflow=" << result.overflow
                  << " safe=" << result.safe << std::endl;
        if (!std::cout)
            throw std::runtime_error("cannot write run summary");
        return result.overflow ? 1 : 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
