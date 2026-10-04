// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — dedicated controller Linux AMP logging lifecycle

#include "amp_uio_configuration.h"
#include "power_journal.h"
#include "../amp_logger.h"
#include "../run_metadata.h"
#include <algorithm>

/** Bind original files before acquiring two actual IRQ-free UIO resources and raw outputs. */
int main(int argc, char **argv) {
    if (argc < 5) {
        std::cerr
            << "usage: run_amp_uio run_configuration resource_configuration events.bin tracking_raw.csv [--metadata file] [--cpu N] [--scheduler normal|fifo] [--priority N] [--power-config file --power-journal file]\n";
        return 1;
    }
    try {
        const auto options = witness::read_run_options(argc, argv, 5);
        const auto original = witness::file_digest(argv[1]);
        const auto resource_original = witness::file_digest(argv[2]);
        const auto configuration = witness::read_configuration(argv[1]);
        const auto resources = witness::read_amp_uio_configuration(argv[2]);
        witness::verify_digest(argv[1], original);
        witness::verify_digest(argv[2], resource_original);
        if (configuration.modeled_overload_ns)
            throw std::runtime_error("modeled overload delay is simulation-only");
        if (resources.poll_ns > static_cast<std::uint64_t>(configuration.period_ticks) * 10)
            throw std::runtime_error("AMP nominal logger polling exceeds the sample interval");
        std::unique_ptr<witness::Pac1934Device> sensor;
        witness::PowerConfiguration power{};
        witness::FileDigest power_original;
        if (options.power_configuration) {
            power_original = witness::file_digest(options.power_configuration);
            power = witness::read_power_configuration(options.power_configuration);
            witness::verify_digest(options.power_configuration, power_original);
            const auto inherited = witness::read_host_policy();
            if (std::find(inherited.cpus.begin(), inherited.cpus.end(), power.worker_cpu) ==
                inherited.cpus.end())
                throw std::runtime_error("power worker CPU is outside inherited affinity");
            if (options.cpu < 0 || options.cpu == power.worker_cpu)
                throw std::runtime_error(
                    "power acquisition requires separate logger and worker CPUs");
            sensor = std::make_unique<witness::Pac1934Device>(power);
        }
        const auto policy = witness::apply_host_policy(options);
        witness::AmpUioDevice device(resources.identity, resources.fabric, resources.mailbox);
        const auto startup = device.time();
        std::uint32_t abi = 0;
        while (!(abi = device.read_memory32(resources.mailbox.address +
                                            offsetof(witness_amp_mailbox, abi)))) {
            if (device.time() - startup > resources.startup_ns)
                throw std::runtime_error("AMP firmware mailbox initialisation timed out");
            device.advance(resources.poll_ns);
        }
        if (abi != WITNESS_AMP_ABI)
            throw std::runtime_error("AMP firmware mailbox ABI mismatch");
        if (device.read_memory32(resources.mailbox.address +
                                 offsetof(witness_amp_mailbox, status)) != WITNESS_AMP_INITIAL ||
            device.read_memory32(resources.mailbox.address +
                                 offsetof(witness_amp_mailbox, logger_status)))
            throw std::runtime_error("AMP logger requires a fresh dedicated firmware boot");
        witness::verify_digest(argv[1], original);
        witness::verify_digest(argv[2], resource_original);
        witness::configure_run(device, configuration);
        witness::RunOutput output(argv[3], argv[4]);
        std::unique_ptr<witness::PowerJournal> journal;
        witness::RunHooks hooks;
        if (sensor) {
            journal = std::make_unique<witness::PowerJournal>(options.power_journal, power, *sensor,
                                                              device);
            hooks = journal->hooks();
        }
        witness::AmpLogger<witness::AmpUioDevice> logger(
            device, configuration, output, resources.mailbox.address, journal ? &hooks : nullptr);
        const auto completion_start = device.time();
        while (!logger.poll()) {
            if (device.time() - completion_start > resources.completion_ns)
                throw std::runtime_error("AMP logger completion timed out");
            device.advance(resources.poll_ns);
        }
        const auto result = logger.completion();
        witness::verify_digest(argv[1], original);
        witness::verify_digest(argv[2], resource_original);
        std::vector<witness::ArtifactDigest> artifacts{
            {"configuration", original},
            {"amp_resources", resource_original},
            {"events", witness::file_digest(argv[3])},
            {"tracking_raw", witness::file_digest(argv[4])}};
        if (sensor) {
            witness::verify_digest(options.power_configuration, power_original);
            artifacts.push_back({"power_configuration", power_original});
            artifacts.push_back({"power_journal", witness::file_digest(options.power_journal)});
        }
        if (options.metadata)
            witness::write_run_metadata(options.metadata, configuration, result,
                                        witness::read_register(device, 0x6c) != 0,
                                        "amp_uio_unqualified", options, policy, artifacts);
        std::cout << "amp_uio_unqualified samples=" << result.samples
                  << " records=" << result.records << " misses=" << result.misses
                  << " overflow=" << result.overflow << " safe=" << result.safe << std::endl;
        if (!std::cout)
            throw std::runtime_error("cannot write AMP logger summary");
        return result.overflow ? 1 : 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
