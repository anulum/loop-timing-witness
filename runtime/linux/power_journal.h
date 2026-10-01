// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — bracketed real IIO acquisition journal

/** @file power_journal.h
 * bracketed real IIO acquisition journal.
 */

#ifndef WITNESS_POWER_JOURNAL_H
#define WITNESS_POWER_JOURNAL_H
#include "pac1934_device.h"
#include "../run_control.h"
#include "../exclusive_output.h"
#include <atomic>
#include <condition_variable>
#include <future>
#include <mutex>
#include <thread>

namespace witness {
/** Separate normal-policy worker; exact raw readings never imply atomic rail windows. */
class PowerJournal {
    const PowerConfiguration configuration;
    Pac1934Device &sensor;
    const std::function<std::uint64_t()> host_time;
    const std::function<std::uint32_t(std::uint8_t)> register_read;
    ExclusiveOutput output;
    std::thread worker;
    std::mutex mutex;
    std::condition_variable wake;
    bool stopping = false;
    std::atomic<bool> failed{false};
    std::exception_ptr failure;
    std::array<std::uint64_t, 4> previous_energy{};
    bool have_energy = false;
    std::uint64_t snapshot = 0;
    /** Only this worker reads the dedicated low/high fabric counter snapshot. */
    std::uint64_t ticks();
    /** Preserve each actual sysfs access with independently measured time brackets. */
    void acquire();
    /** Set/read back worker policy, acquire before START and periodically until drain. */
    void collect(std::promise<void> ready) noexcept;
    /** Stop and join on every path without replacing the original failure. */
    void stop() noexcept;
    /** Bind actual clock/register operations independently of controller versus AMP IRQ ownership. */
    PowerJournal(const char *path, const PowerConfiguration &config, Pac1934Device &device,
                 std::function<std::uint64_t()> clock,
                 std::function<std::uint32_t(std::uint8_t)> read);
public:
    /** Validate configuration before creating and flushing the exclusive journal header. */
    template<class Device>
    PowerJournal(const char *path, const PowerConfiguration &config, Pac1934Device &device, Device &fabric)
        : PowerJournal(path, config, device, [&fabric] { return fabric.time(); },
                       [&fabric](std::uint8_t address) { return read_register(fabric, address); }) {}
    /** Join before releasing UIO/IIO resources, retaining all partial evidence. */
    ~PowerJournal();
    PowerJournal(const PowerJournal &) = delete;
    PowerJournal &operator=(const PowerJournal &) = delete;
    /** Start once before stop/close; require its initial actual acquisition before START. */
    void start();
    /** Propagate a worker acquisition failure to the controller. */
    void check();
    /** Require a started worker; capture after drain, join and close once with error checks. */
    void finish();
    /** Bind the logger to the common native run lifecycle. */
    RunHooks hooks();
};
} // namespace witness
#endif
