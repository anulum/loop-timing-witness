// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — native run command options

/** @file run_options.h
 * native run command options.
 */

#ifndef WITNESS_RUN_OPTIONS_H
#define WITNESS_RUN_OPTIONS_H
#include <charconv>
#include <cstring>
#include <stdexcept>

namespace witness {
/** Explicit per-process command options; omission preserves inherited Linux policy. */
struct RunOptions {
    const char *metadata = nullptr;
    const char *power_configuration = nullptr;
    const char *power_journal = nullptr;
    int cpu = -1;
    int scheduler = -1;
    int priority = -1;
};

/** Validate public options before changing any calling-thread Linux policy. */
inline void validate_run_options(const RunOptions &options) {
    if (options.cpu < -1 || options.scheduler < -1 || options.scheduler > 1 ||
        options.priority < -1)
        throw std::runtime_error("invalid CPU, scheduler or priority request");
    if (options.scheduler == 1 && (options.cpu < 0 || options.priority <= 0))
        throw std::runtime_error("FIFO requires explicit CPU and positive priority");
    if (options.scheduler != 1 && options.priority != -1 &&
        !(options.scheduler == 0 && options.priority == 0))
        throw std::runtime_error("priority requires an explicit scheduler");
    if ((options.power_configuration == nullptr) != (options.power_journal == nullptr))
        throw std::runtime_error("power configuration and journal must be supplied together");
    if (options.power_configuration && !options.metadata)
        throw std::runtime_error("power acquisition requires native metadata");
}

/** Read a full nonnegative decimal Linux CPU/priority argument without truncation. */
inline int option_number(const char *text) {
    int result = 0;
    const auto parsed = std::from_chars(text, text + std::strlen(text), result);
    if (parsed.ec != std::errc{} || parsed.ptr != text + std::strlen(text) || result < 0)
        throw std::runtime_error("run option requires a nonnegative decimal integer");
    return result;
}

/** Parse each optional argument once and require explicit FIFO priority and CPU. */
inline RunOptions read_run_options(int argc, char **argv, int first) {
    RunOptions result;
    for (int index = first; index < argc; index += 2) {
        if (index + 1 >= argc)
            throw std::runtime_error("run option requires a value");
        if (std::strcmp(argv[index], "--metadata") == 0 && !result.metadata) {
            result.metadata = argv[index + 1];
        } else if (std::strcmp(argv[index], "--power-config") == 0 && !result.power_configuration) {
            result.power_configuration = argv[index + 1];
        } else if (std::strcmp(argv[index], "--power-journal") == 0 && !result.power_journal) {
            result.power_journal = argv[index + 1];
        } else if (std::strcmp(argv[index], "--cpu") == 0 && result.cpu == -1) {
            result.cpu = option_number(argv[index + 1]);
        } else if (std::strcmp(argv[index], "--scheduler") == 0 && result.scheduler == -1) {
            if (std::strcmp(argv[index + 1], "normal") == 0)
                result.scheduler = 0;
            else if (std::strcmp(argv[index + 1], "fifo") == 0)
                result.scheduler = 1;
            else
                throw std::runtime_error("scheduler must be normal or fifo");
        } else if (std::strcmp(argv[index], "--priority") == 0 && result.priority == -1) {
            result.priority = option_number(argv[index + 1]);
        } else
            throw std::runtime_error("unknown or duplicate run option");
    }
    validate_run_options(result);
    return result;
}
} // namespace witness
/** @var witness::RunOptions::metadata
 * Optional exclusive output path for the native run receipt.
 */
/** @var witness::RunOptions::power_configuration
 * Optional explicit power-acquisition configuration path.
 */
/** @var witness::RunOptions::power_journal
 * Optional exclusive power journal paired with power_configuration.
 */
/** @var witness::RunOptions::cpu
 * Requested CPU, or minus one to preserve inherited affinity.
 */
/** @var witness::RunOptions::scheduler
 * Minus one preserves policy; zero requests normal and one requests FIFO.
 */
/** @var witness::RunOptions::priority
 * Requested scheduler priority, or minus one to preserve inherited policy.
 */

#endif
