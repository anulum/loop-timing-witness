// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — actual completed-run metadata API custody

#include "../../runtime/run_metadata.h"
#include <filesystem>

/** Refuse malformed metadata configuration, then write the actual completed run receipt. */
void metadata_refusal(witness::Simulation &device, const witness::RunConfiguration &configuration,
                      const std::string &scenario, const char *config_path, const char *events,
                      const char *tracking) {
    witness::RunOutput output(events, tracking);
    const auto result = witness::execute_run(device, configuration, output);
    assert(result.samples == configuration.cycles && result.misses == 0);
    const auto policy = witness::read_host_policy();
    const witness::RunOptions options;
    std::vector<witness::ArtifactDigest> artifacts{
        {"configuration", witness::file_digest(config_path)},
        {"events", witness::file_digest(events)},
        {"tracking_raw", witness::file_digest(tracking)}};
    const auto path = std::string(events) + ".metadata.json";
    const auto thermal = witness::read_register(device, 0x6c) != 0;
    if (scenario == "metadata_amp") {
        const auto resources = std::string(config_path) + ".amp-resources";
        artifacts.push_back({"amp_resources", witness::file_digest(resources.c_str())});
        witness::write_run_metadata(path.c_str(), configuration, result, thermal,
                                    "amp_uio_unqualified", options, policy, artifacts);
        return;
    }
    auto invalid = configuration;
    const char *message = "invalid cycles, period or controller coefficients";
    if (scenario == "metadata_zero")
        invalid.cycles = 0;
    else {
        assert(scenario == "metadata_fault");
        invalid.fault_enabled = true;
        invalid.fault_kind = 4;
        invalid.fault_periods = 1;
        message = "invalid reference mode, phase or fault kind";
    }
    refusal(
        [&] {
            witness::write_run_metadata(path.c_str(), invalid, result, thermal, "rtl_simulation",
                                        options, policy, artifacts);
        },
        message);
    assert(!std::filesystem::exists(path));
    witness::write_run_metadata(path.c_str(), configuration, result, thermal, "rtl_simulation",
                                options, policy, artifacts);
}
