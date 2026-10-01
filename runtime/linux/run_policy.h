// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — actual Linux run scheduling policy

/** @file run_policy.h
 * actual Linux run scheduling policy.
 */

#ifndef WITNESS_LINUX_RUN_POLICY_H
#define WITNESS_LINUX_RUN_POLICY_H
#include "../run_options.h"
#include <sched.h>
#include <sys/resource.h>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <string>
#include <vector>

namespace witness {
/** Actual calling-thread Linux policy snapshot, not a timing qualification. */
struct HostPolicy {
    int scheduler;
    int priority;
    int observed_cpu;
    int nice;
    std::vector<int> cpus;
};

/** Own the dynamic libc affinity mask across all error and success exits. */
struct FreeCpuMask {
    /** Release a CPU_ALLOC allocation through libc CPU_FREE. */
    void operator()(cpu_set_t *mask) const noexcept { CPU_FREE(mask); }
};

/** Read the current allowed CPUs, expanding for kernels with large CPU masks. */
inline HostPolicy read_host_policy() {
    HostPolicy result{};
    result.scheduler = sched_getscheduler(0);
    sched_param parameter{};
    if (result.scheduler < 0 || sched_getparam(0, &parameter) != 0)
        throw std::runtime_error("cannot read Linux scheduler policy");
    result.priority = parameter.sched_priority;
    errno = 0;
    result.nice = getpriority(PRIO_PROCESS, 0);
    if (errno) throw std::runtime_error("cannot read Linux nice value");
    result.observed_cpu = sched_getcpu();
    if (result.observed_cpu < 0) throw std::runtime_error("cannot read current Linux CPU");
    for (int capacity = CPU_SETSIZE; capacity <= (1 << 20); capacity *= 2) {
        const auto count = static_cast<std::size_t>(capacity);
        const auto size = CPU_ALLOC_SIZE(count);
        std::unique_ptr<cpu_set_t, FreeCpuMask> mask(CPU_ALLOC(count));
        if (!mask) throw std::runtime_error("cannot allocate Linux CPU affinity mask");
        CPU_ZERO_S(size, mask.get());
        if (sched_getaffinity(0, size, mask.get()) == 0) {
            for (int cpu = 0; cpu < capacity; ++cpu)
                if (CPU_ISSET_S(static_cast<std::size_t>(cpu), size, mask.get()))
                    result.cpus.push_back(cpu);
            return result;
        }
        if (errno != EINVAL) throw std::runtime_error("cannot read Linux CPU affinity");
    }
    throw std::runtime_error("Linux CPU affinity exceeds supported mask size");
}

/** Apply only requested calling-thread changes before device or output acquisition. */
inline HostPolicy apply_host_policy(const RunOptions &options) {
    validate_run_options(options);
    const auto inherited = read_host_policy();
    if (options.cpu >= 0) {
        bool allowed = false;
        for (int cpu : inherited.cpus) if (cpu == options.cpu) allowed = true;
        if (!allowed) throw std::runtime_error("requested CPU is outside inherited affinity");
    }
    if (options.scheduler == 1 &&
        (options.priority < sched_get_priority_min(SCHED_FIFO) ||
         options.priority > sched_get_priority_max(SCHED_FIFO)))
        throw std::runtime_error("FIFO priority is outside Linux scheduler bounds");
    if (options.cpu >= 0) {
        const auto count = static_cast<std::size_t>(options.cpu) + 1;
        const auto size = CPU_ALLOC_SIZE(count);
        std::unique_ptr<cpu_set_t, FreeCpuMask> mask(CPU_ALLOC(count));
        if (!mask) throw std::runtime_error("cannot allocate requested Linux CPU mask");
        CPU_ZERO_S(size, mask.get());
        CPU_SET_S(static_cast<std::size_t>(options.cpu), size, mask.get());
        if (sched_setaffinity(0, size, mask.get()) != 0)
            throw std::runtime_error(std::string("cannot set Linux CPU affinity: ") + std::strerror(errno));
    }
    if (options.scheduler >= 0) {
        sched_param parameter{};
        parameter.sched_priority = options.scheduler == 1 ? options.priority : 0;
        if (sched_setscheduler(0, options.scheduler == 1 ? SCHED_FIFO : SCHED_OTHER, &parameter) != 0)
            throw std::runtime_error(std::string("cannot set Linux scheduler: ") + std::strerror(errno));
    }
    const auto actual = read_host_policy();
    if ((options.cpu >= 0 && (actual.cpus.size() != 1 || actual.cpus[0] != options.cpu)) ||
        (options.scheduler >= 0 && actual.scheduler != (options.scheduler == 1 ? SCHED_FIFO : SCHED_OTHER)) ||
        (options.scheduler >= 0 && actual.priority != (options.scheduler == 1 ? options.priority : 0)))
        throw std::runtime_error("Linux scheduler/affinity readback differs from request");
    return actual;
}

/** Append the observed Linux policy and explicit request to native run JSON. */
inline bool write_host_policy(std::FILE *file, const RunOptions &options, const HostPolicy &actual) {
    bool failed = std::fprintf(file,
        "  \"host_policy\": {\"requested_cpu\": %d, \"requested_scheduler\": %d, "
        "\"requested_priority\": %d, \"scheduler\": %d, \"priority\": %d, "
        "\"observed_cpu\": %d, \"nice\": %d, \"affinity_cpus\": [",
        options.cpu, options.scheduler, options.priority, actual.scheduler, actual.priority, actual.observed_cpu, actual.nice) < 0;
    for (std::size_t index = 0; index < actual.cpus.size(); ++index)
        if (std::fprintf(file, "%s%d", index ? ", " : "", actual.cpus[index]) < 0) failed = true;
    return std::fprintf(file, "]}\n") < 0 || failed;
}
} // namespace witness
/** @var witness::HostPolicy::scheduler
 * Actual Linux scheduler policy identifier.
 */
/** @var witness::HostPolicy::priority
 * Actual Linux scheduling priority.
 */
/** @var witness::HostPolicy::observed_cpu
 * CPU on which the calling thread was observed.
 */
/** @var witness::HostPolicy::nice
 * Actual calling-thread nice value.
 */
/** @var witness::HostPolicy::cpus
 * Actual allowed CPU identifiers from the affinity mask.
 */

#endif
