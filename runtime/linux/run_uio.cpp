// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — in-process native controller over actual Linux UIO

#include "uio_device.h"
#include "power_journal.h"
#include <algorithm>
#include "../run_control.h"
#include "../run_metadata.h"

/** Require explicit hardware identity and retain outputs without qualification claims. */
int main(int argc, char **argv) {
    if (argc < 9) {
        std::cerr
            << "usage: run_uio configuration events.bin tracking_raw.csv uioN name version map physical_address_decimal [--metadata file] [--cpu N] [--scheduler normal|fifo] [--priority N] [--power-config file --power-journal file]\n";
        return 1;
    }
    try {
        const auto options = witness::read_run_options(argc, argv, 9);
        const auto original =
            options.metadata ? witness::file_digest(argv[1]) : witness::FileDigest{};
        const auto configuration = witness::read_configuration(argv[1]);
        if (options.metadata)
            witness::verify_digest(argv[1], original);
        if (configuration.modeled_overload_ns)
            throw std::runtime_error("modeled overload delay is simulation-only");
        std::istringstream arguments(std::string(argv[7]) + " " + argv[8]);
        const auto map = witness::number(arguments, UINT32_MAX);
        const auto physical = witness::number(arguments, UINT64_MAX);
        witness::end_request(arguments);
        std::unique_ptr<witness::Pac1934Device> sensor;
        witness::PowerConfiguration power{};
        witness::FileDigest power_original;
        if (options.power_configuration) {
            if (options.metadata)
                power_original = witness::file_digest(options.power_configuration);
            power = witness::read_power_configuration(options.power_configuration);
            if (options.metadata)
                witness::verify_digest(options.power_configuration, power_original);
            const auto inherited = witness::read_host_policy();
            if (std::find(inherited.cpus.begin(), inherited.cpus.end(), power.worker_cpu) ==
                inherited.cpus.end())
                throw std::runtime_error("power worker CPU is outside inherited affinity");
            if (options.cpu < 0 || options.cpu == power.worker_cpu)
                throw std::runtime_error(
                    "power acquisition requires explicit separate controller and worker CPUs");
            sensor = std::make_unique<witness::Pac1934Device>(power);
        }
        const auto policy = witness::apply_host_policy(options);
        witness::UioDevice device(
            {argv[4], argv[5], argv[6], static_cast<std::uint32_t>(map), physical});
        witness::RunOutput output(argv[2], argv[3]);
        std::unique_ptr<witness::PowerJournal> journal;
        witness::RunHooks hooks;
        if (sensor) {
            journal = std::make_unique<witness::PowerJournal>(options.power_journal, power, *sensor,
                                                              device);
            hooks = journal->hooks();
        }
        const auto result =
            witness::execute_run(device, configuration, output, journal ? &hooks : nullptr);
        std::vector<witness::ArtifactDigest> artifacts;
        if (options.metadata) {
            witness::verify_digest(argv[1], original);
            artifacts = {{"configuration", original},
                         {"events", witness::file_digest(argv[2])},
                         {"tracking_raw", witness::file_digest(argv[3])}};
        }
        if (options.metadata && sensor) {
            witness::verify_digest(options.power_configuration, power_original);
            artifacts.push_back({"power_configuration", power_original});
            artifacts.push_back({"power_journal", witness::file_digest(options.power_journal)});
        }
        if (options.metadata)
            witness::write_run_metadata(options.metadata, configuration, result,
                                        witness::read_register(device, 0x6c) != 0,
                                        "uio_unqualified", options, policy, artifacts);
        std::cout << "uio_unqualified samples=" << result.samples << " records=" << result.records
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
