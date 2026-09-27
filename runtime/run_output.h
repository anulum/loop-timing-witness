// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — exclusive raw event and controller trace output

#ifndef WITNESS_RUN_OUTPUT_H
#define WITNESS_RUN_OUTPUT_H
#include "run_configuration.h"
#include "exclusive_output.h"
#include <array>
#include <cstdio>
#include <stdexcept>

namespace witness {
/** Raw files are created exclusively; a failed run retains its partial evidence. */
class RunOutput {
    ExclusiveOutput events, tracking;
public:
    /** Refuse existing paths and flush the raw trace header before run configuration. */
    RunOutput(const char *event_path, const char *tracking_path)
        : events(event_path, OutputFormat::binary, "cannot create exclusive event output"),
          tracking(tracking_path, OutputFormat::text, "cannot create exclusive tracking output") {
        auto *trace = tracking.stream("tracking output is closed");
        if (std::fputs("cycle,reference_raw,output_raw,velocity_raw,command_raw,integral_raw,derivative_raw,clipped,integral_held,submitted,sample_ticks,irq_generation,overload_work\n", trace) < 0 || std::fflush(trace) != 0)
            throw std::runtime_error("cannot write tracking header");
    }
    /** Owned streams retain partial evidence and close during failure cleanup. */
    ~RunOutput() = default;
    RunOutput(const RunOutput &) = delete;
    RunOutput &operator=(const RunOutput &) = delete;

    /** Store exactly four little-endian words from the actual held FIFO window. */
    void event(const std::array<std::uint32_t, 4> &words) {
        auto *stream = events.stream("event output is closed");
        std::array<unsigned char, 16> bytes{};
        for (std::size_t word = 0; word < 4; ++word)
            for (unsigned byte = 0; byte < 4; ++byte)
                bytes[word * 4 + byte] = static_cast<unsigned char>(words[word] >> (byte * 8));
        if (std::fwrite(bytes.data(), 1, bytes.size(), stream) != bytes.size()) throw std::runtime_error("cannot write event record");
    }
    /** Preserve actual input, returned command/state, original ticks and IRQ generation. */
    void sample(std::int32_t reference, std::int32_t position, std::int32_t velocity,
                const witness_command &command, bool submitted, std::uint64_t ticks,
                std::uint64_t generation, std::uint64_t work) {
        auto *stream = tracking.stream("tracking output is closed");
        if (std::fprintf(stream, "%u,%d,%d,%d,%d,%d,%d,%u,%u,%u,%llu,%llu,%llu\n",
            command.cycle, reference, position, velocity, command.command, command.integral,
            command.derivative, static_cast<unsigned>(command.clipped), static_cast<unsigned>(command.integral_held),
            static_cast<unsigned>(submitted), static_cast<unsigned long long>(ticks),
            static_cast<unsigned long long>(generation), static_cast<unsigned long long>(work)) < 0)
            throw std::runtime_error("cannot write tracking sample");
    }
    /** Flush and close once; refuse later writes or repeated completion. */
    void finish() {
        if (!events.is_open() || !tracking.is_open()) throw std::runtime_error("run output is closed");
        const int event_status = events.close("event output is closed");
        const int tracking_status = tracking.close("tracking output is closed");
        if (event_status || tracking_status) throw std::runtime_error("cannot finish run output");
    }
};
} // namespace witness
#endif
