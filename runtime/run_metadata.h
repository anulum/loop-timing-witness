// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — native configuration and completion metadata

#ifndef WITNESS_RUN_METADATA_H
#define WITNESS_RUN_METADATA_H
#include "run_control.h"
#include "linux/run_policy.h"
#include "linux/file_digest.h"
#include <openssl/crypto.h>

namespace witness {
/** Validate configuration before creating exclusive JSON for actual completion counts. */
inline void write_run_metadata(const char *path, const RunConfiguration &config,
    const RunResult &result, bool thermal, const char *kind,
    const RunOptions &options, const HostPolicy &policy, const std::vector<ArtifactDigest> &artifacts) {
    validate_configuration(config);
    std::FILE *file = std::fopen(path, "wx");
    if (!file) throw std::runtime_error("cannot create exclusive native metadata");
    const std::array<const char *, 4> faults = {"drop", "delay", "freeze", "overload_request"};
    const auto &c = config.coefficients;
    const bool failed = std::fprintf(file,
        "{\n  \"schema\": \"loop-timing-witness.native-run.v1\",\n"
        "  \"source_kind\": \"%s\",\n  \"controller\": \"%s\",\n"
        "  \"cycles\": %u, \"period_ticks\": %u, \"thermal\": %s,\n"
        "  \"coefficients\": {\"kp\": %d, \"ki_period\": %d, \"derivative_decay\": %d,"
        " \"derivative_gain\": %d, \"position_gain\": %d, \"velocity_gain\": %d,"
        " \"reference_gain\": %d, \"output_min\": %d, \"output_max\": %d,"
        " \"integral_min\": %d, \"integral_max\": %d},\n"
        "  \"reference\": {\"mode\": %u, \"amplitude\": %d, \"offset\": %d,"
        " \"ramp\": %d, \"phase\": %u},\n"
        "  \"fault\": {\"kind\": \"%s\", \"cycle\": %u, \"duration_periods\": %u},\n"
        "  \"overload\": {\"iterations\": %u, \"modeled_nanoseconds\": %u},\n"
        "  \"result\": {\"samples\": %llu, \"records\": %llu, \"misses\": %u,"
        " \"overflow\": %u, \"safe\": %s},\n",
        kind, config.lqr ? "lqr" : "pid", config.cycles, config.period_ticks, thermal ? "true" : "false",
        c.kp, c.ki_period, c.derivative_decay, c.derivative_gain, c.position_gain, c.velocity_gain,
        c.reference_gain, c.output_min, c.output_max, c.integral_min, c.integral_max,
        config.reference_mode, config.amplitude, config.offset, config.ramp, config.phase,
        config.fault_enabled ? faults[config.fault_kind] : "none", config.fault_cycle, config.fault_periods,
        config.overload_iterations, config.modeled_overload_ns,
        static_cast<unsigned long long>(result.samples), static_cast<unsigned long long>(result.records),
        result.misses, result.overflow, result.safe ? "true" : "false") < 0;
    bool artifact_failed = std::fputs("  \"artifacts\": {", file) < 0;
    for (std::size_t index = 0; index < artifacts.size(); ++index) {
        const auto &artifact = artifacts[index];
        if (std::fprintf(file, "%s\"%s\": {\"sha256\": \"%s\", \"bytes\": %llu}",
            index ? ", " : "", artifact.role, artifact.digest.sha256.c_str(),
            static_cast<unsigned long long>(artifact.digest.bytes)) < 0) artifact_failed = true;
    }
    artifact_failed = std::fputs("},\n", file) < 0 || artifact_failed;
    const bool crypto_failed = std::fprintf(file,
        "  \"crypto_library\": {\"algorithm\": \"sha256\", \"header_version_number\": %llu, "
        "\"runtime_version_number\": %llu},\n",
        static_cast<unsigned long long>(OPENSSL_VERSION_NUMBER),
        static_cast<unsigned long long>(OpenSSL_version_num())) < 0;
    const bool policy_failed = write_host_policy(file, options, policy);
    const bool end_failed = std::fprintf(file, "}\n") < 0;
    const int status = std::fclose(file);
    if (failed || artifact_failed || crypto_failed || policy_failed || end_failed || status) throw std::runtime_error("cannot write native metadata");
}
} // namespace witness
#endif
