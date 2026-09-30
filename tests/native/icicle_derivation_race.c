// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — test-owned Icicle derivation filesystem races

#define _GNU_SOURCE
#include <fcntl.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

static int writes_observed;
static int injected;

/** Return whether one staging path ends with the explicitly selected owned suffix. */
static int selected_path(const char *path) {
    const char *suffix = getenv("WITNESS_ICICLE_RACE_SUFFIX");
    if (suffix == NULL || strstr(path, "/.icicle-derive-") == NULL) return 0;
    const size_t path_length = strlen(path);
    const size_t suffix_length = strlen(suffix);
    return path_length >= suffix_length
        && strcmp(path + path_length - suffix_length, suffix) == 0;
}

/** Leave a kernel-created receipt proving that the selected race actually occurred. */
static void mark_injection(void) {
    const char *marker = getenv("WITNESS_ICICLE_RACE_MARKER");
    if (marker == NULL) return;
    const int receipt = (int)syscall(SYS_openat, AT_FDCWD, marker,
                                     O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    if (receipt >= 0) (void)syscall(SYS_close, receipt);
}

/** Change a selected staging file immediately before the guarded production read. */
static void mutate_staging_file(const char *path) {
    const int source = (int)syscall(SYS_openat, AT_FDCWD, path,
                                    O_WRONLY | O_TRUNC | O_CLOEXEC, 0);
    if (source < 0) return;
    const char changed[] = "changed during derivation\n";
    (void)syscall(SYS_write, source, changed, sizeof(changed) - 1);
    (void)syscall(SYS_close, source);
    injected = 1;
    mark_injection();
}

/** Create a competing output and sentinel immediately before manifest publication. */
static void create_destination(void) {
    const char *destination = getenv("WITNESS_ICICLE_RACE_DESTINATION");
    if (destination == NULL || syscall(SYS_mkdir, destination, 0700) != 0) return;
    const int directory = (int)syscall(SYS_openat, AT_FDCWD, destination,
                                       O_RDONLY | O_DIRECTORY | O_CLOEXEC, 0);
    if (directory >= 0) {
        const int sentinel = (int)syscall(SYS_openat, directory, "keep",
                                          O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
        if (sentinel >= 0) {
            const char content[] = "preserved\n";
            (void)syscall(SYS_write, sentinel, content, sizeof(content) - 1);
            (void)syscall(SYS_close, sentinel);
        }
        (void)syscall(SYS_close, directory);
    }
    injected = 1;
    mark_injection();
}

/** Forward one open while injecting only the configured test-owned filesystem race. */
static int original_open(const char *path, int flags, mode_t mode) {
    if (!injected && selected_path(path)) {
        const int access = flags & O_ACCMODE;
        if (access != O_RDONLY && (flags & (O_CREAT | O_TRUNC)) != 0) ++writes_observed;
        const char *destination = getenv("WITNESS_ICICLE_RACE_DESTINATION");
        if (destination != NULL && access != O_RDONLY) {
            create_destination();
        } else if (access == O_RDONLY) {
            const char *required_text = getenv("WITNESS_ICICLE_RACE_WRITES");
            const int required = required_text == NULL ? 1 : atoi(required_text);
            if (writes_observed >= required) mutate_staging_file(path);
        }
    }
    return (int)syscall(SYS_openat, AT_FDCWD, path, flags, mode);
}

/** Observe Python's ordinary file opens and forward them to the real kernel. */
int open(const char *path, int flags, ...) {
    mode_t mode = 0;
    if ((flags & O_CREAT) != 0) {
        va_list arguments;
        va_start(arguments, flags);
        mode = (mode_t)va_arg(arguments, int);
        va_end(arguments);
    }
    return original_open(path, flags, mode);
}

/** Observe Python's large-file opens through the same real kernel boundary. */
int open64(const char *path, int flags, ...) {
    mode_t mode = 0;
    if ((flags & O_CREAT) != 0) {
        va_list arguments;
        va_start(arguments, flags);
        mode = (mode_t)va_arg(arguments, int);
        va_end(arguments);
    }
    return original_open(path, flags, mode);
}
