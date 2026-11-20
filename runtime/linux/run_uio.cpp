// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — in-process native controller over actual Linux UIO

#include "uio_device.h"
#include "../refusal.h"
#include "power_journal.h"
#include <algorithm>
#include "../run_control.h"
#include "../run_metadata.h"

/** Require explicit hardware identity and retain outputs without qualification claims. */
int main(int argc, char **argv) {
    if (argc < 9) {
        std::cerr
            << "usage: run_uio configuration events.bin tracking_raw.csv uioN name version map physical_address_decimal [--metadata file] [--cpu N] [--scheduler normal|fifo] [--priority N] [--power-config file --power-journal file] [--trace-stop miss|safe --tracefs directory] [--fault-uio \"uioN name version map physical_address_decimal\"]\n";
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
            throw witness::RuntimeRefused("modeled overload delay is simulation-only");
        if (configuration.fault_enabled != (options.fault_uio != nullptr))
            throw witness::RuntimeRefused(
                "a fault run needs --fault-uio, and only a fault run takes it");
        witness::UioIdentity fault_identity{};
        if (options.fault_uio) {
            std::istringstream fault_fields(options.fault_uio);
            if (!(fault_fields >> fault_identity.device >> fault_identity.name >>
                  fault_identity.version))
                throw witness::RuntimeRefused("fault-page UIO identity is incomplete");
            fault_identity.map =
                static_cast<std::uint32_t>(witness::number(fault_fields, UINT32_MAX));
            fault_identity.physical_address = witness::number(fault_fields, UINT64_MAX);
            witness::end_request(fault_fields);
        }
        std::istringstream arguments(std::string(argv[7]) + " " + argv[8]);
        const auto map = witness::number(arguments, UINT32_MAX);
        const auto physical = witness::number(arguments, UINT64_MAX);
        witness::end_request(arguments);
        if (options.fault_uio &&
            (physical > UINT64_MAX - witness::fault_page ||
             fault_identity.physical_address != physical + witness::fault_page))
            throw witness::RuntimeRefused("fault-page UIO is not the page after the run page");
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
                throw witness::RuntimeRefused("power worker CPU is outside inherited affinity");
            if (options.cpu < 0 || options.cpu == power.worker_cpu)
                throw witness::RuntimeRefused(
                    "power acquisition requires explicit separate controller and worker CPUs");
            sensor = std::make_unique<witness::Pac1934Device>(power);
        }
        const auto policy = witness::apply_host_policy(options);
        const auto kernel = witness::read_kernel_context();
        witness::UioDevice device(
            {argv[4], argv[5], argv[6], static_cast<std::uint32_t>(map), physical});
        if (options.fault_uio)
            device.open_fault_page(fault_identity);
        std::unique_ptr<witness::TraceStop> trace;
        if (options.trace_stop)
            trace = std::make_unique<witness::TraceStop>(options.tracefs, options.trace_stop);
        witness::RunOutput output(argv[2], argv[3]);
        std::unique_ptr<witness::PowerJournal> journal;
        witness::RunHooks hooks;
        if (sensor) {
            journal = std::make_unique<witness::PowerJournal>(options.power_journal, power, *sensor,
                                                              device);
            hooks = journal->hooks();
        }
        if (trace)
            hooks.deadlines = [&trace](std::uint32_t misses, bool safe) {
                trace->observe(misses, safe);
            };
        const auto result = witness::execute_run(device, configuration, output,
                                                 journal || trace ? &hooks : nullptr);
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
                                        "uio_unqualified", options, policy, kernel, artifacts,
                                        trace ? &trace->report() : nullptr);
        std::cout << "uio_unqualified samples=" << result.samples << " records=" << result.records
                  << " misses=" << result.misses << " overflow=" << result.overflow
                  << " safe=" << result.safe << std::endl;
        if (!std::cout)
            throw witness::RuntimeRefused("cannot write run summary");
        return result.overflow ? 1 : 0;
    } catch (const witness::RuntimeRefused &error) {
        std::cerr << error.what() << '\n';
        return 1;
    } catch (const witness::ArgumentRefused &error) {
        std::cerr << error.what() << '\n';
        return 1;
    } catch (const std::exception &) {
        std::cerr << "native execution failed\n";
        return 1;
    }
}
