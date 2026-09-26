// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — controllers/c/controller_cli.c

#include "witness_controller.h"

#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>

/** Read one complete text record and reject embedded NUL before string parsing. */
static int read_row(char **line, size_t *capacity) {
    const ssize_t length = getline(line, capacity, stdin);
    if (length < 0) {
        return ferror(stdin) != 0 ? -1 : 0;
    }
    if (memchr(*line, '\0', (size_t)length) != NULL) {
        return -1;
    }
    return 1;
}

/** Release the getline buffer before completing any public CLI exit path. */
static int finish(char *line, int status) {
    free(line);
    return status;
}

/** Parse exactly count comma-separated integers with no trailing content. */
static bool parse_row(char *line, int64_t *values, size_t count) {
    char *cursor = line;
    for (size_t index = 0; index < count; index++) {
        if ((*cursor < '0' || *cursor > '9') && *cursor != '+' && *cursor != '-') {
            return false;
        }
        errno = 0;
        char *end;
        intmax_t value = strtoimax(cursor, &end, 10);
        if (errno == ERANGE || end == cursor || value < INT32_MIN || value > UINT32_MAX) {
            return false;
        }
        values[index] = (int64_t)value;
        if (index + 1 < count) {
            if (*end != ',') {
                return false;
            }
            cursor = end + 1;
        } else if (strcmp(end, "\n") != 0 && strcmp(end, "\r\n") != 0 && *end != '\0') {
            return false;
        }
    }
    return true;
}

/** Parser already checks INT32_MIN; refuse unsigned-only values before narrowing. */
static bool signed_fields(const int64_t *values, size_t begin, size_t count) {
    for (size_t index = begin; index < count; index++) {
        if (values[index] > INT32_MAX) {
            return false;
        }
    }
    return true;
}

/** Run the host streaming CLI; processor register/interrupt adapters are separate. */
int main(int argc, char **argv) {
    char *line = NULL;
    size_t capacity = 0;
    if (argc != 2 || (strcmp(argv[1], "pid") != 0 && strcmp(argv[1], "lqr") != 0)) {
        fputs("usage: controller_cli pid|lqr < vectors.csv\n", stderr);
        return finish(line, EXIT_FAILURE);
    }
    const bool lqr = strcmp(argv[1], "lqr") == 0;
    /* Write each command immediately; printf reports any actual write failure. */
    setbuf(stdout, NULL);
    int64_t values[11];
    if (read_row(&line, &capacity) != 1 ||
        !parse_row(line, values, 11) || !signed_fields(values, 0, 11)) {
        fputs("invalid coefficient row\n", stderr);
        return finish(line, EXIT_FAILURE);
    }
    const witness_coefficients coefficients = {
        (int32_t)values[0], (int32_t)values[1], (int32_t)values[2], (int32_t)values[3],
        (int32_t)values[4], (int32_t)values[5], (int32_t)values[6], (int32_t)values[7],
        (int32_t)values[8], (int32_t)values[9], (int32_t)values[10]
    };
    if (!witness_coefficients_valid(&coefficients)) {
        fputs("invalid coefficients\n", stderr);
        return finish(line, EXIT_FAILURE);
    }
    witness_pid_state state;
    witness_pid_reset(&state);
    int read_status;
    while ((read_status = read_row(&line, &capacity)) == 1) {
        if (strcmp(line, "reset\n") == 0 || strcmp(line, "reset\r\n") == 0 ||
            strcmp(line, "reset") == 0) {
            witness_pid_reset(&state);
            continue;
        }
        if (!parse_row(line, values, 4) || !signed_fields(values, 1, 4) || values[0] < 0 || line[0] == '-') {
            fputs("invalid sample row\n", stderr);
            return finish(line, EXIT_FAILURE);
        }
        witness_command command;
        if (lqr) {
            (void)witness_lqr_step(&coefficients, (uint32_t)values[0], (int32_t)values[1],
                                   (int32_t)values[2], (int32_t)values[3], &command);
        } else {
            (void)witness_pid_step(&coefficients, &state, (uint32_t)values[0],
                                  (int32_t)values[1], (int32_t)values[2], &command);
        }
        if (printf("%" PRIu32 ",%" PRId32 ",%" PRId32 ",%" PRId32 ",%u,%u\n",
                   command.cycle, command.command, command.integral, command.derivative,
                   (unsigned)command.clipped, (unsigned)command.integral_held) < 0) {
            fputs("cannot write command stream\n", stderr);
            return finish(line, EXIT_FAILURE);
        }
    }
    if (read_status < 0) {
        fputs("cannot read/write controller stream\n", stderr);
        return finish(line, EXIT_FAILURE);
    }
    return finish(line, EXIT_SUCCESS);
}
