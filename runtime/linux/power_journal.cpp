// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — separate CPU PAC1934 raw logger

#include "power_journal.h"
#include "run_policy.h"
#include <algorithm>
#include <chrono>

namespace witness {
PowerJournal::PowerJournal(const char *path, const PowerConfiguration &config, Pac1934Device &device, UioDevice &uio)
    : configuration(config), sensor(device), fabric(uio),
      output((validate_power_configuration(config), path), OutputFormat::text, "cannot create exclusive power journal") {
    auto *file = output.stream("power journal is closed");
    if (std::fputs("snapshot,rail,channel,quantity,attribute,host_before_ns,host_after_ns,fabric_before_ticks,fabric_after_ticks,worker_cpu,scheduler,priority,kernel_release,label_prefix,shunt_microohms,sample_rate,value\n", file) < 0 || std::fflush(file) != 0) {
        throw std::runtime_error("cannot write power journal header");
    }
}
PowerJournal::~PowerJournal() { stop(); }
std::uint64_t PowerJournal::ticks() {
    const std::uint64_t low = read_register(fabric, 0x08);
    return low | (static_cast<std::uint64_t>(read_register(fabric, 0x0c)) << 32);
}
void PowerJournal::acquire() {
    auto *file = output.stream("power journal is closed");
    const auto frame_start = fabric.time();
    sensor.verify();
    for (std::size_t index = 0; index < configuration.rails.size(); ++index) {
        const auto &rail = configuration.rails[index];
        for (const auto *quantity : {"voltage", "current", "energy"}) {
            for (bool scale : {false, true}) {
                const auto host_before = fabric.time(), fabric_before = ticks();
                const auto value = sensor.read(rail, quantity, scale);
                const auto fabric_after = ticks(), host_after = fabric.time();
                if (std::fprintf(file, "%llu,%s,%u,%s,%s,%llu,%llu,%llu,%llu,%d,%d,0,%s,%s,%u,%u,%s\n",
                    static_cast<unsigned long long>(snapshot), rail.name.c_str(), rail.channel, quantity,
                    scale ? "scale" : "raw", static_cast<unsigned long long>(host_before),
                    static_cast<unsigned long long>(host_after), static_cast<unsigned long long>(fabric_before),
                    static_cast<unsigned long long>(fabric_after), configuration.worker_cpu, SCHED_OTHER, configuration.kernel_release.c_str(), rail.label.c_str(),
                    rail.shunt_microohms, configuration.sample_rate, value.c_str()) < 0)
                    throw std::runtime_error("cannot write power journal reading");
                if (host_after < host_before || fabric_after < fabric_before)
                    throw std::runtime_error("power acquisition clock moved backwards");
                if (!scale && std::strcmp(quantity, "energy") == 0) {
                    const auto energy = std::stoull(value);
                    if ((have_energy && energy < previous_energy[index]) || energy == 214748364799999999ULL)
                        throw std::runtime_error("PAC1934 energy accumulator reset or saturated");
                    previous_energy[index] = energy;
                }
            }
        }
    }
    sensor.verify();
    if (fabric.time() - frame_start > configuration.maximum_read_ns)
        throw std::runtime_error("power acquisition exceeds configured read span");
    if (std::fflush(file) != 0) throw std::runtime_error("cannot flush power journal frame");
    have_energy = true;
    ++snapshot;
}
void PowerJournal::collect(std::promise<void> ready) noexcept {
    bool announced = false;
    try {
        const auto count = static_cast<std::size_t>(configuration.worker_cpu) + 1;
        const auto size = CPU_ALLOC_SIZE(count);
        std::unique_ptr<cpu_set_t, FreeCpuMask> mask(CPU_ALLOC(count));
        if (!mask) throw std::runtime_error("cannot allocate power worker affinity");
        CPU_ZERO_S(size, mask.get());
        CPU_SET_S(static_cast<std::size_t>(configuration.worker_cpu), size, mask.get());
        sched_param parameter{};
        if (sched_setscheduler(0, SCHED_OTHER, &parameter) != 0 || sched_setaffinity(0, size, mask.get()) != 0)
            throw std::runtime_error("cannot set power worker scheduler/affinity");
        const auto policy = read_host_policy();
        if (policy.scheduler != SCHED_OTHER || policy.priority != 0 || policy.cpus != std::vector<int>{configuration.worker_cpu})
            throw std::runtime_error("power worker policy readback differs");
        acquire();
        ready.set_value(); announced = true;
        auto next = std::chrono::steady_clock::now();
        for (;;) {
            next += std::chrono::nanoseconds(configuration.period_ns);
            std::unique_lock<std::mutex> lock(mutex);
            if (wake.wait_until(lock, next, [this] { return stopping; })) break;
            lock.unlock();
            acquire();
            if (std::chrono::steady_clock::now() > next + std::chrono::nanoseconds(configuration.period_ns))
                throw std::runtime_error("power acquisition polling schedule overrun");
        }
        acquire();
    } catch (...) {
        failure = std::current_exception();
        failed.store(true, std::memory_order_release);
        if (!announced) ready.set_exception(failure);
    }
}
void PowerJournal::start() {
    if (!output.is_open()) throw std::runtime_error("power journal is closed");
    {
        std::lock_guard<std::mutex> lock(mutex);
        if (stopping) throw std::runtime_error("power worker is stopped");
    }
    if (worker.joinable()) throw std::runtime_error("power worker already started");
    std::promise<void> ready;
    auto initial = ready.get_future();
    worker = std::thread(&PowerJournal::collect, this, std::move(ready));
    initial.get();
}
void PowerJournal::check() {
    if (failed.load(std::memory_order_acquire)) std::rethrow_exception(failure);
}
void PowerJournal::stop() noexcept {
    { std::lock_guard<std::mutex> lock(mutex); stopping = true; }
    wake.notify_all();
    if (worker.joinable()) worker.join();
}
void PowerJournal::finish() {
    if (!output.is_open()) throw std::runtime_error("power journal is closed");
    if (!worker.joinable()) {
        check();
        throw std::runtime_error("power worker has not started");
    }
    stop(); check();
    const auto result = output.close("power journal is closed");
    if (result != 0) throw std::runtime_error("cannot finish power journal");
}
RunHooks PowerJournal::hooks() {
    return {[this] { start(); }, [this] { check(); }, [this] { finish(); }};
}
} // namespace witness
