// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — stop kernel tracing when a run misses a deadline

/** @file trace_stop.h
 * Stop the kernel's function tracer when the fabric reports a missed deadline or the safe state,
 * as `cyclictest -b` does at its latency threshold, so the trace ends at the cause.
 */

#ifndef WITNESS_LINUX_TRACE_STOP_H
#define WITNESS_LINUX_TRACE_STOP_H
#include "../refusal.h"
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <string>
#include <time.h>
#include <unistd.h>

namespace witness {
/** What a trace stop records for the run metadata. */
struct TraceStopReport {
    std::string condition;
    std::string tracefs;
    std::string trace_clock;
    bool triggered = false;
    std::uint32_t misses = 0;
    bool safe = false;
    std::uint64_t monotonic_ns = 0;
};

/** Whether a text is absolute and holds only printable ASCII that needs no JSON escape and no
 * bracket or caret, the characters the native-run schema allows in a tracefs path. */
inline bool plain_trace_path(const std::string &text) {
    if (text.empty() || text.size() > 256 || text.front() != '/')
        return false;
    for (const char character : text)
        if (character < ' ' || character > '~' || character == '"' ||
            (character >= '[' && character <= '^'))
            return false;
    return true;
}

/** Read one small tracefs control file whole; refuse an unreadable or oversized file. */
inline std::string read_trace_control(const std::string &path) {
    const int descriptor = open(path.c_str(), O_RDONLY | O_CLOEXEC);
    if (descriptor < 0)
        throw witness::RuntimeRefused("cannot open tracefs control: " + path);
    std::string text(512, '\0');
    const auto count = ::read(descriptor, text.data(), text.size());
    ::close(descriptor);
    if (count < 0 || static_cast<std::size_t>(count) == text.size())
        throw witness::RuntimeRefused("cannot read tracefs control: " + path);
    text.resize(static_cast<std::size_t>(count));
    return text;
}

/** The clock that a tracefs `trace_clock` file selects, the name in brackets. */
inline std::string selected_trace_clock(const std::string &text) {
    const auto open_bracket = text.find('[');
    const auto close_bracket = text.find(']', open_bracket);
    if (open_bracket == std::string::npos || close_bracket == std::string::npos ||
        close_bracket == open_bracket + 1 || close_bracket - open_bracket > 33)
        throw witness::RuntimeRefused("tracefs trace_clock names no selected clock");
    const auto name = text.substr(open_bracket + 1, close_bracket - open_bracket - 1);
    for (const char character : name)
        if (!((character >= 'a' && character <= 'z') || (character >= '0' && character <= '9') ||
              character == '_' || character == '-'))
            throw witness::RuntimeRefused("tracefs trace_clock names no selected clock");
    return name;
}

/** Write one whole control text; a short or failed write refuses the run. */
inline void write_trace_control(int descriptor, const std::string &text, const char *what) {
    const auto written = ::write(descriptor, text.data(), text.size());
    if (written != static_cast<ssize_t>(text.size()))
        throw witness::RuntimeRefused(std::string("cannot write tracefs ") + what + " (errno " +
                                      std::to_string(errno) + ")");
}

/** Append the native-run JSON member of a trace stop, ending with a comma and newline. */
inline void append_trace_stop_json(std::string &text, const TraceStopReport &stop) {
    text += "  \"trace_stop\": {\"condition\": \"";
    text += stop.condition;
    text += "\", \"tracefs\": \"";
    text += stop.tracefs;
    text += "\", \"trace_clock\": \"";
    text += stop.trace_clock;
    text += "\", \"triggered\": ";
    text += stop.triggered ? "true" : "false";
    text += ", \"misses\": ";
    text += std::to_string(stop.misses);
    text += ", \"safe\": ";
    text += stop.safe ? "true" : "false";
    text += ", \"monotonic_ns\": ";
    text += std::to_string(stop.monotonic_ns);
    text += "},\n";
}

/** One threshold stop of kernel tracing, armed for the whole run. */
class TraceStop {
  public:
    /** Require active tracing under `tracefs` and open its marker and switch for writing.
     * `condition` is `miss` (the first missed deadline) or `safe` (the latched safe state). */
    TraceStop(const std::string &tracefs, const std::string &condition) {
        if (condition != "miss" && condition != "safe")
            throw witness::RuntimeRefused("trace stop condition must be miss or safe");
        if (!plain_trace_path(tracefs))
            throw witness::RuntimeRefused("tracefs must be an absolute plain ASCII path");
        state.condition = condition;
        state.tracefs = tracefs;
        if (read_trace_control(tracefs + "/tracing_on") != "1\n")
            throw witness::RuntimeRefused("kernel tracing is not on");
        state.trace_clock = selected_trace_clock(read_trace_control(tracefs + "/trace_clock"));
        marker = open((tracefs + "/trace_marker").c_str(), O_WRONLY | O_CLOEXEC);
        switch_off = open((tracefs + "/tracing_on").c_str(), O_WRONLY | O_CLOEXEC);
        if (marker < 0 || switch_off < 0) {
            close();
            throw witness::RuntimeRefused("cannot open the tracefs marker and switch");
        }
    }
    TraceStop(const TraceStop &) = delete;
    TraceStop &operator=(const TraceStop &) = delete;
    ~TraceStop() { close(); }

    /** Stop tracing once, at the first observation that meets the condition: write a marker
     * that names the cause, then switch tracing off and record the monotonic time. */
    void observe(std::uint32_t misses, bool safe) {
        if (state.triggered || (state.condition == "miss" ? misses == 0 : !safe))
            return;
        std::string text = "loop-timing-witness trace stop: ";
        text += state.condition;
        text += " misses=";
        text += std::to_string(misses);
        text += safe ? " safe=1\n" : " safe=0\n";
        write_trace_control(marker, text, "marker");
        write_trace_control(switch_off, "0", "tracing_on");
        timespec stamp{};
        clock_gettime(CLOCK_MONOTONIC, &stamp);
        state.triggered = true;
        state.misses = misses;
        state.safe = safe;
        state.monotonic_ns = static_cast<std::uint64_t>(stamp.tv_sec) * 1000000000 +
                             static_cast<std::uint64_t>(stamp.tv_nsec);
    }

    /** The stop's record for the run metadata. */
    const TraceStopReport &report() const { return state; }

  private:
    void close() noexcept {
        if (marker >= 0)
            ::close(marker);
        if (switch_off >= 0)
            ::close(switch_off);
        marker = switch_off = -1;
    }
    TraceStopReport state;
    int marker = -1;
    int switch_off = -1;
};
} // namespace witness
/** @var witness::TraceStopReport::condition
 * `miss` or `safe`, the observation that stops tracing.
 */
/** @var witness::TraceStopReport::tracefs
 * Tracefs directory whose marker and switch the run writes.
 */
/** @var witness::TraceStopReport::trace_clock
 * Clock that the trace's timestamps use, as tracefs selected it at the start.
 */
/** @var witness::TraceStopReport::triggered
 * Whether the condition occurred and tracing was stopped.
 */
/** @var witness::TraceStopReport::misses
 * Fabric deadline-miss count at the stop.
 */
/** @var witness::TraceStopReport::safe
 * Fabric safe-state flag at the stop.
 */
/** @var witness::TraceStopReport::monotonic_ns
 * CLOCK_MONOTONIC time of the stop, in nanoseconds.
 */

#endif
