// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — actual Linux scheduling API validation

#include "../../runtime/linux/run_policy.h"
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <limits>
#include <string>
#include <sys/prctl.h>
#include <sys/syscall.h>

/** Refuse invalid public options without changing the actual child-thread policy. */
int main(int argc, char **argv) {
    if (argc != 2)
        return 1;
    sched_param parameter{};
    assert(sched_setscheduler(0, SCHED_BATCH, &parameter) == 0);
    errno = 0;
    const auto inherited_nice = getpriority(PRIO_PROCESS, 0);
    assert(errno == 0);
    const auto requested_nice = inherited_nice < 19 ? inherited_nice + 1 : inherited_nice;
    assert(setpriority(PRIO_PROCESS, 0, requested_nice) == 0);
    const auto before = witness::read_host_policy();
    assert(before.scheduler == SCHED_BATCH && !before.cpus.empty());
    assert(before.nice == requested_nice);
    witness::RunOptions options;
    const std::string scenario = argv[1];
    std::string message = "invalid CPU, scheduler or priority request";
    if (scenario == "cpu_low")
        options.cpu = -2;
    else if (scenario == "scheduler_low")
        options.scheduler = -2;
    else if (scenario == "scheduler_high") {
        options.scheduler = 2;
        options.cpu = before.cpus.front();
    } else if (scenario == "priority_low")
        options.priority = -2;
    else if (scenario == "cpu_unavailable") {
        message = "requested CPU is outside inherited affinity";
        options.cpu = before.cpus.back() + 1;
    } else if (scenario == "fifo_bounds") {
        message = "FIFO priority is outside Linux scheduler bounds";
        options.scheduler = 1;
        options.cpu = before.cpus.front();
        const auto maximum = sched_get_priority_max(SCHED_FIFO);
        assert(maximum > 0 && maximum < std::numeric_limits<int>::max());
        options.priority = maximum + 1;
    } else if (scenario == "fifo_no_cpu" || scenario == "fifo_no_priority" ||
               scenario == "fifo_zero") {
        message = "FIFO requires explicit CPU and positive priority";
        options.scheduler = 1;
        options.cpu = scenario == "fifo_no_cpu" ? -1 : before.cpus.front();
        options.priority = scenario == "fifo_no_priority" ? -1 : scenario == "fifo_zero" ? 0 : 1;
    } else if (scenario == "orphan_priority" || scenario == "normal_priority") {
        message = "priority requires an explicit scheduler";
        options.priority = 1;
        if (scenario == "normal_priority")
            options.scheduler = 0;
    } else if (scenario == "power_config" || scenario == "power_journal" ||
               scenario == "power_metadata") {
        message = scenario == "power_metadata"
                      ? "power acquisition requires native metadata"
                      : "power configuration and journal must be supplied together";
        if (scenario != "power_journal")
            options.power_configuration = "power.conf";
        if (scenario != "power_config")
            options.power_journal = "power.csv";
    } else if (scenario == "fifo_permissions") {
        options.scheduler = 1;
        options.priority = 1;
        options.cpu = before.cpus.front();
    } else if (scenario == "affinity_denied" || scenario == "scheduler_denied") {
        const bool affinity = scenario == "affinity_denied";
        const auto syscall = affinity ? __NR_sched_setaffinity : __NR_sched_setscheduler;
        std::array<sock_filter, 4> filter{
            {BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(seccomp_data, nr)),
             BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, static_cast<std::uint32_t>(syscall), 0, 1),
             BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EACCES),
             BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW)}};
        sock_fprog program{static_cast<unsigned short>(filter.size()), filter.data()};
        assert(prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) == 0);
        assert(prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program) == 0);
        if (affinity)
            options.cpu = before.cpus.front();
        else
            options.scheduler = 0;
        message = std::string(affinity ? "cannot set Linux CPU affinity (errno "
                                       : "cannot set Linux scheduler (errno ") +
                  std::to_string(EACCES) + ")";
    } else if (scenario != "preserve" && scenario != "normal" && scenario != "cpu_only" &&
               scenario != "normal_unpinned")
        return 1;
    if (scenario == "preserve" || scenario == "normal" || scenario == "cpu_only" ||
        scenario == "normal_unpinned") {
        const bool normal = scenario == "normal" || scenario == "normal_unpinned";
        const bool pinned = scenario == "normal" || scenario == "cpu_only";
        if (normal)
            options.scheduler = 0;
        if (pinned)
            options.cpu = before.cpus.front();
        const auto actual = witness::apply_host_policy(options);
        assert(actual.scheduler == (normal ? SCHED_OTHER : SCHED_BATCH));
        assert(actual.priority == 0 && actual.nice == before.nice);
        assert(actual.cpus == (pinned ? std::vector<int>{before.cpus.front()} : before.cpus));
    } else if (scenario == "fifo_permissions") {
        try {
            const auto actual = witness::apply_host_policy(options);
            assert(actual.scheduler == SCHED_FIFO && actual.priority == 1);
        } catch (const std::runtime_error &error) {
            assert(std::string(error.what()) ==
                   "cannot set Linux scheduler (errno " + std::to_string(EPERM) + ")");
            const auto actual = witness::read_host_policy();
            assert(actual.scheduler == before.scheduler && actual.priority == before.priority);
        }
        const auto actual = witness::read_host_policy();
        assert(actual.cpus == std::vector<int>{before.cpus.front()});
        assert(actual.nice == before.nice);
    } else {
        bool refused = false;
        try {
            witness::apply_host_policy(options);
        } catch (const std::runtime_error &error) {
            refused = true;
            assert(std::string(error.what()) == message);
        }
        assert(refused);
        const auto actual = witness::read_host_policy();
        assert(actual.scheduler == before.scheduler && actual.priority == before.priority);
        assert(actual.nice == before.nice && actual.cpus == before.cpus);
    }
    std::cout << "verified " << scenario << '\n';
}
