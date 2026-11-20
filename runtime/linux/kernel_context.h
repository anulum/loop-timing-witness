// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — Linux real-time context of a native run

/** @file kernel_context.h
 * Linux real-time context of a native run, read once before the run.
 */

#ifndef WITNESS_LINUX_KERNEL_CONTEXT_H
#define WITNESS_LINUX_KERNEL_CONTEXT_H
#include "../refusal.h"
#include <array>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <string>
#include <sys/utsname.h>
#include <unistd.h>
#include <vector>

namespace witness {
/** Files a kernel context is read from; the API tests point them at their own files. */
struct KernelContextSources {
    const char *realtime = "/sys/kernel/realtime";
    const char *isolated = "/sys/devices/system/cpu/isolated";
    const char *nohz_full = "/sys/devices/system/cpu/nohz_full";
    const char *command_line = "/proc/cmdline";
    const char *status = "/proc/self/status";
    const char *dma_latency = "/dev/cpu_dma_latency";
};

/** Linux real-time context of a run: a record of the host, not a timing qualification. */
struct KernelContext {
    std::string release;
    std::string version;
    bool realtime = false;
    std::string isolated_cpus;
    bool nohz_full_known = false;
    std::string nohz_full_cpus;
    std::vector<std::string> boot_parameters;
    unsigned long long locked_memory_kib = 0;
    bool dma_latency_known = false;
    std::int32_t dma_latency_us = 0;
};

/** Boot parameter keys recorded from the command line: isolation, tick, RCU, interrupt
 * affinity, preemption, idle states, watchdogs, clock source and mitigations. */
inline constexpr std::array<const char *, 20> kernel_boot_keys = {"isolcpus",
                                                                  "nohz",
                                                                  "nohz_full",
                                                                  "rcu_nocbs",
                                                                  "rcu_nocb_poll",
                                                                  "irqaffinity",
                                                                  "kthread_cpus",
                                                                  "preempt",
                                                                  "threadirqs",
                                                                  "skew_tick",
                                                                  "idle",
                                                                  "cpuidle.off",
                                                                  "processor.max_cstate",
                                                                  "intel_idle.max_cstate",
                                                                  "nosoftlockup",
                                                                  "nowatchdog",
                                                                  "nmi_watchdog",
                                                                  "clocksource",
                                                                  "tsc",
                                                                  "mitigations"};

/** Whether a character may appear in recorded kernel text: printable ASCII without the
 * characters a JSON string would escape and without the brackets and caret the schema
 * pattern classes cannot name. */
inline bool kernel_text_character(char character) {
    const auto code = static_cast<unsigned char>(character);
    return (code >= 0x20 && code <= 0x21) || (code >= 0x23 && code <= 0x5a) ||
           (code >= 0x5f && code <= 0x7e);
}

/** Return text that the metadata may carry verbatim, or refuse it. */
inline std::string kernel_text(const std::string &text, std::size_t limit, const char *what) {
    bool valid = !text.empty() && text.size() <= limit;
    for (char character : text)
        valid = valid && kernel_text_character(character);
    if (!valid)
        throw witness::RuntimeRefused(std::string("unsupported Linux ") + what + " text");
    return text;
}

/** Return a kernel CPU list without its final newline, or refuse anything but CPU numbers
 * and ranges separated by commas. The empty list stays empty. */
inline std::string kernel_cpu_list(std::string text, const char *what) {
    if (!text.empty() && text.back() == '\n')
        text.pop_back();
    bool valid = true, digit = false, range = false;
    for (char character : text) {
        if (character >= '0' && character <= '9') {
            digit = true;
        } else if (digit && ((character == '-' && !range) || character == ',')) {
            range = character == '-';
            digit = false;
        } else {
            valid = false;
        }
    }
    if (!valid || (!text.empty() && !digit))
        throw witness::RuntimeRefused(std::string("malformed Linux ") + what + " CPU list");
    return text;
}

/** Outcome of opening one small kernel file. */
enum class KernelFile {
    present, ///< Opened and read whole.
    absent,  ///< The path does not exist.
    denied   ///< The caller may not open it.
};

/** Read a whole small kernel file; an absent or unreadable file is reported, not refused. */
inline KernelFile read_kernel_file(const char *path, std::string &text) {
    const int descriptor = ::open(path, O_RDONLY | O_CLOEXEC);
    if (descriptor < 0) {
        if (errno == ENOENT)
            return KernelFile::absent;
        if (errno == EACCES)
            return KernelFile::denied;
        throw witness::RuntimeRefused(std::string("cannot open ") + path);
    }
    std::array<char, 8192> buffer{};
    std::size_t used = 0;
    ssize_t count = 0;
    while (used < buffer.size() &&
           (count = ::read(descriptor, buffer.data() + used, buffer.size() - used)) > 0)
        used += static_cast<std::size_t>(count);
    ::close(descriptor);
    if (count < 0 || used == buffer.size())
        throw witness::RuntimeRefused(std::string("cannot read the whole of ") + path);
    text.assign(buffer.data(), used);
    return KernelFile::present;
}

/** Read a kernel file that every Linux host this runtime supports provides to every user. */
inline std::string required_kernel_file(const char *path) {
    std::string text;
    if (read_kernel_file(path, text) != KernelFile::present)
        throw witness::RuntimeRefused(std::string("cannot read ") + path);
    return text;
}

/** Return the recorded boot parameters of a command line, in boot order. */
inline std::vector<std::string> kernel_boot_parameters(const std::string &command_line) {
    std::vector<std::string> result;
    std::size_t start = 0;
    while (start < command_line.size()) {
        const auto end = command_line.find_first_of(" \t\n", start);
        const auto token = command_line.substr(start, end - start);
        const auto key = token.substr(0, token.find('='));
        for (const char *known : kernel_boot_keys)
            if (key == known)
                result.push_back(kernel_text(token, 256, "boot parameter"));
        start = end == std::string::npos ? command_line.size() : end + 1;
    }
    return result;
}

/** Return the locked memory of this process in KiB from its status text: the VmLck line,
 * blanks, at most 15 decimal digits and the unit. */
inline unsigned long long kernel_locked_memory(const std::string &status) {
    const auto at = status.find("\nVmLck:");
    auto position = at == std::string::npos ? status.size() : at + 7;
    while (position < status.size() && (status[position] == ' ' || status[position] == '\t'))
        ++position;
    const auto first = position;
    unsigned long long value = 0;
    while (position < status.size() && position - first < 15 && status[position] >= '0' &&
           status[position] <= '9')
        value = value * 10 + static_cast<unsigned>(status[position++] - '0');
    if (position == first || status.compare(position, 4, " kB\n") != 0)
        throw witness::RuntimeRefused("cannot read locked memory of this process");
    return value;
}

/** Read the Linux real-time context before the run acquires any device or output. */
inline KernelContext read_kernel_context(const KernelContextSources &sources = {}) {
    KernelContext result;
    utsname kernel{};
    if (::uname(&kernel) != 0)
        throw witness::RuntimeRefused("cannot read Linux kernel identity");
    result.release = kernel_text(kernel.release, 64, "kernel release");
    result.version = kernel_text(kernel.version, 64, "kernel version");
    std::string text;
    const auto realtime = read_kernel_file(sources.realtime, text);
    if (realtime == KernelFile::denied || (realtime == KernelFile::present && text != "1\n"))
        throw witness::RuntimeRefused("unsupported Linux realtime flag");
    result.realtime = realtime == KernelFile::present;
    result.isolated_cpus = kernel_cpu_list(required_kernel_file(sources.isolated), "isolated");
    text.clear();
    const auto nohz_full = read_kernel_file(sources.nohz_full, text);
    if (nohz_full == KernelFile::denied)
        throw witness::RuntimeRefused("cannot read Linux full dynamic tick CPUs");
    result.nohz_full_known = nohz_full == KernelFile::present;
    // Without a full dynamic tick mask the kernel prints its null mask: Linux 6.8 as "(null)"
    // padded with spaces to the CPU count, Linux 7.0 as an empty line.
    const auto first = text.find_first_not_of(' ');
    const auto shown = first == std::string::npos ? std::string() : text.substr(first);
    if (result.nohz_full_known && shown != "(null)\n")
        result.nohz_full_cpus = kernel_cpu_list(shown, "full dynamic tick");
    result.boot_parameters = kernel_boot_parameters(required_kernel_file(sources.command_line));
    result.locked_memory_kib = kernel_locked_memory(required_kernel_file(sources.status));
    text.clear();
    result.dma_latency_known = read_kernel_file(sources.dma_latency, text) == KernelFile::present;
    if (result.dma_latency_known && text.size() != sizeof result.dma_latency_us)
        throw witness::RuntimeRefused("unsupported Linux CPU latency request value");
    if (result.dma_latency_known)
        std::memcpy(&result.dma_latency_us, text.data(), sizeof result.dma_latency_us);
    if (result.dma_latency_us < 0)
        throw witness::RuntimeRefused("unsupported Linux CPU latency request value");
    return result;
}

/** Append the native-run JSON member of a kernel context, ending with a comma and newline. */
inline void append_kernel_context_json(std::string &text, const KernelContext &context) {
    text += "  \"host_kernel\": {\"release\": \"";
    text += context.release;
    text += "\", \"version\": \"";
    text += context.version;
    text += "\", \"realtime\": ";
    text += context.realtime ? "true" : "false";
    text += ", \"isolated_cpus\": \"";
    text += context.isolated_cpus;
    text += "\", \"nohz_full_cpus\": ";
    if (context.nohz_full_known) {
        text += '"';
        text += context.nohz_full_cpus;
        text += '"';
    } else {
        text += "null";
    }
    text += ", \"boot_parameters\": [";
    for (std::size_t index = 0; index < context.boot_parameters.size(); ++index) {
        text += index ? ", \"" : "\"";
        text += context.boot_parameters[index];
        text += '"';
    }
    text += "], \"locked_memory_kib\": ";
    text += std::to_string(context.locked_memory_kib);
    text += ", \"cpu_dma_latency_us\": ";
    if (context.dma_latency_known)
        text += std::to_string(context.dma_latency_us);
    else
        text += "null";
    text += "},\n";
}
} // namespace witness
/** @var witness::KernelContextSources::realtime
 * Present with the content 1 only on PREEMPT_RT kernels.
 */
/** @var witness::KernelContextSources::isolated
 * CPUs isolated from the scheduler at boot.
 */
/** @var witness::KernelContextSources::nohz_full
 * CPUs in full dynamic tick mode; absent without CONFIG_NO_HZ_FULL.
 */
/** @var witness::KernelContextSources::command_line
 * Kernel boot command line.
 */
/** @var witness::KernelContextSources::status
 * Status of the calling process, for its locked memory.
 */
/** @var witness::KernelContextSources::dma_latency
 * CPU latency PM QoS device; opening it adds a request at the default value.
 */
/** @var witness::KernelContext::release
 * Kernel release from uname.
 */
/** @var witness::KernelContext::version
 * Kernel version from uname, which names the preemption model.
 */
/** @var witness::KernelContext::realtime
 * Whether the kernel is a PREEMPT_RT kernel.
 */
/** @var witness::KernelContext::isolated_cpus
 * Isolated CPU list, empty when none.
 */
/** @var witness::KernelContext::nohz_full_known
 * Whether the kernel reports full dynamic tick CPUs.
 */
/** @var witness::KernelContext::nohz_full_cpus
 * Full dynamic tick CPU list, empty when none.
 */
/** @var witness::KernelContext::boot_parameters
 * Recorded boot parameters in boot order.
 */
/** @var witness::KernelContext::locked_memory_kib
 * Memory locked by this process before the run, in KiB.
 */
/** @var witness::KernelContext::dma_latency_known
 * Whether the CPU latency request could be read.
 */
/** @var witness::KernelContext::dma_latency_us
 * Current CPU latency PM QoS target in microseconds.
 */

#endif
