// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — mutate one owned Rust input at its second real filesystem read

#define _GNU_SOURCE
#include <fcntl.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

static int observed_reads;

/** Open a real file and change the selected owned input immediately before its second read. */
static int original_open(const char *path, int flags, mode_t mode) {
    const char *target = getenv("WITNESS_DRIFT_PATH");
    if (target != NULL && strcmp(path, target) == 0 && (flags & O_ACCMODE) == O_RDONLY) {
        ++observed_reads;
        if (observed_reads == 2) {
            int source = (int)syscall(SYS_openat, AT_FDCWD, path, O_WRONLY | O_CLOEXEC, 0);
            if (source >= 0) {
                (void)syscall(SYS_pwrite64, source, "X", 1, 0);
                (void)syscall(SYS_close, source);
                const char *marker = getenv("WITNESS_DRIFT_MARKER");
                if (marker != NULL) {
                    int receipt = (int)syscall(SYS_openat, AT_FDCWD, marker,
                                               O_WRONLY | O_CREAT | O_EXCL, 0600);
                    if (receipt >= 0) (void)syscall(SYS_close, receipt);
                }
            }
        }
    }
    return (int)syscall(SYS_openat, AT_FDCWD, path, flags, mode);
}

/** Forward a selected Python open to the real kernel syscall after observing owned bytes. */
int open(const char *path, int flags, ...) {
    mode_t mode = 0;
    if (flags & O_CREAT) {
        va_list args;
        va_start(args, flags);
        mode = (mode_t)va_arg(args, int);
        va_end(args);
    }
    return original_open(path, flags, mode);
}

/** Cover Python's large-file open variant using the same real kernel syscall. */
int open64(const char *path, int flags, ...) {
    mode_t mode = 0;
    if (flags & O_CREAT) {
        va_list args;
        va_start(args, flags);
        mode = (mode_t)va_arg(args, int);
        va_end(args);
    }
    return original_open(path, flags, mode);
}
