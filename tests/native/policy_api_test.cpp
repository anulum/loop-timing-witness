// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — actual Linux scheduling API validation

#include "../../runtime/linux/run_policy.h"
#include "system_call_answer.h"
#include <cassert>
#include <iostream>
#include <limits>
#include <string>
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
    bool reads_denied = false;
    auto expected_cpus = before.cpus;
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
        answer_system_call(affinity ? __NR_sched_setaffinity : __NR_sched_setscheduler, EACCES);
        if (affinity)
            options.cpu = before.cpus.front();
        else
            options.scheduler = 0;
        message = std::string(affinity ? "cannot set Linux CPU affinity (errno "
                                       : "cannot set Linux scheduler (errno ") +
                  std::to_string(EACCES) + ")";
    } else if (scenario == "scheduler_read_denied" || scenario == "parameter_read_denied") {
        message = "cannot read Linux scheduler policy";
        answer_system_call(scenario == "scheduler_read_denied" ? __NR_sched_getscheduler
                                                               : __NR_sched_getparam,
                           EPERM);
        options.cpu = before.cpus.front();
        reads_denied = true;
    } else if (scenario == "nice_read_denied") {
        message = "cannot read Linux nice value";
        answer_system_call(__NR_getpriority, EPERM);
        options.cpu = before.cpus.front();
        reads_denied = true;
    } else if (scenario == "affinity_read_denied" || scenario == "affinity_mask_unbounded") {
        const bool unbounded = scenario == "affinity_mask_unbounded";
        message = unbounded ? "Linux CPU affinity exceeds supported mask size"
                            : "cannot read Linux CPU affinity";
        answer_system_call(__NR_sched_getaffinity, unbounded ? EINVAL : EPERM);
        options.cpu = before.cpus.front();
        reads_denied = true;
    } else if (scenario == "affinity_ignored") {
        message = "Linux scheduler/affinity readback differs from request";
        if (before.cpus.size() < 2) {
            std::cerr << "affinity_ignored needs more than one inherited CPU\n";
            return 1;
        }
        answer_system_call(__NR_sched_setaffinity, 0);
        options.cpu = before.cpus.front();
    } else if (scenario == "fifo_ignored") {
        // The affinity change applies; the skipped scheduler change leaves SCHED_BATCH.
        message = "Linux scheduler/affinity readback differs from request";
        answer_system_call(__NR_sched_setscheduler, 0);
        options.scheduler = 1;
        options.priority = 1;
        options.cpu = before.cpus.front();
        expected_cpus = {before.cpus.front()};
    } else if (scenario != "preserve" && scenario != "normal" && scenario != "cpu_only" &&
               scenario != "normal_unpinned" && scenario != "fifo_priority_ignored")
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
    } else if (scenario == "fifo_priority_ignored") {
        // A FIFO thread whose priority change the kernel skips: the scheduler reads back equal
        // and only the priority differs. Without real-time permission the kernel refuses FIFO.
        sched_param fifo{};
        fifo.sched_priority = 1;
        if (sched_setscheduler(0, SCHED_FIFO, &fifo) != 0) {
            assert(errno == EPERM);
        } else {
            answer_system_call(__NR_sched_setscheduler, 0);
            options.scheduler = 1;
            options.priority = 2;
            options.cpu = before.cpus.front();
            bool refused = false;
            try {
                witness::apply_host_policy(options);
            } catch (const std::runtime_error &error) {
                refused = true;
                assert(std::string(error.what()) ==
                       "Linux scheduler/affinity readback differs from request");
            }
            assert(refused);
            const auto actual = witness::read_host_policy();
            assert(actual.scheduler == SCHED_FIFO && actual.priority == 1);
            assert(actual.cpus == std::vector<int>{before.cpus.front()});
        }
    } else {
        bool refused = false;
        try {
            witness::apply_host_policy(options);
        } catch (const std::runtime_error &error) {
            refused = true;
            assert(std::string(error.what()) == message);
        }
        assert(refused);
        if (!reads_denied) {
            const auto actual = witness::read_host_policy();
            assert(actual.scheduler == before.scheduler && actual.priority == before.priority);
            assert(actual.nice == before.nice && actual.cpus == expected_cpus);
        }
    }
    std::cout << "verified " << scenario << '\n';
}
