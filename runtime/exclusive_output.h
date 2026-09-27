// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — exclusive native output stream ownership

#ifndef WITNESS_EXCLUSIVE_OUTPUT_H
#define WITNESS_EXCLUSIVE_OUTPUT_H
#include <cstdio>
#include <stdexcept>

namespace witness {
/** Native output encoding; both selections always require an exclusive create. */
enum class OutputFormat { text, binary };
/** Own one exclusive stream, retain partial bytes and refuse access after close. */
class ExclusiveOutput {
    std::FILE *file;
public:
    /** Open exclusively; destruction closes an earlier stream if later setup fails. */
    ExclusiveOutput(const char *path, OutputFormat format, const char *error)
        : file(std::fopen(path, format == OutputFormat::binary ? "wbx" : "wx")) {
        if (!file) throw std::runtime_error(error);
    }
    /** Close once during failure cleanup without masking the original exception. */
    ~ExclusiveOutput() { if (file) std::fclose(file); }
    ExclusiveOutput(const ExclusiveOutput &) = delete;
    ExclusiveOutput &operator=(const ExclusiveOutput &) = delete;
    /** Report stream ownership without touching a released FILE. */
    bool is_open() const noexcept { return file != nullptr; }
    /** Borrow the owned stream for a checked native write or flush. */
    std::FILE *stream(const char *closed_error) const {
        if (!file) throw std::runtime_error(closed_error);
        return file;
    }
    /** Release ownership even on flush failure; the caller checks the return status. */
    int close(const char *closed_error) {
        auto *owned = stream(closed_error);
        file = nullptr;
        return std::fclose(owned);
    }
};
} // namespace witness
#endif
