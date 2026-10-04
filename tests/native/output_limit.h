// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — reversible actual child file-size restriction

#ifndef WITNESS_TEST_OUTPUT_LIMIT_H
#define WITNESS_TEST_OUTPUT_LIMIT_H
#include <cassert>
#include <csignal>
#include <sys/resource.h>

/** Restrict real writes, then restore resources before GCC profiling exit writes. */
class ScopedOutputLimit {
    struct rlimit saved {};
    struct sigaction saved_signal {};

  public:
    /** Lower only the soft file-size limit in this owned native test process. */
    explicit ScopedOutputLimit(rlim_t maximum) {
        assert(getrlimit(RLIMIT_FSIZE, &saved) == 0);
        assert(maximum <= saved.rlim_max);
        struct sigaction ignored {};
        ignored.sa_handler = SIG_IGN;
        assert(sigemptyset(&ignored.sa_mask) == 0);
        assert(sigaction(SIGXFSZ, &ignored, &saved_signal) == 0);
        const struct rlimit restricted {
            maximum, saved.rlim_max
        };
        assert(setrlimit(RLIMIT_FSIZE, &restricted) == 0);
    }
    /** Restore both the original limit and signal disposition on every exit. */
    ~ScopedOutputLimit() {
        assert(setrlimit(RLIMIT_FSIZE, &saved) == 0);
        assert(sigaction(SIGXFSZ, &saved_signal, nullptr) == 0);
    }
    ScopedOutputLimit(const ScopedOutputLimit &) = delete;
    ScopedOutputLimit &operator=(const ScopedOutputLimit &) = delete;
};
#endif
