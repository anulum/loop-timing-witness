# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — bounded complete worker readiness frames

"""Read one bounded readiness frame with a deadline covering all of its bytes."""

from __future__ import annotations

import math
import os
import select
import time
from typing import BinaryIO

from manifest_io import parse_json_object

READINESS_TIMEOUT_SECONDS = 10
MAX_READINESS_BYTES = 4096


def read_ready_pid(stream: BinaryIO, timeout: float = READINESS_TIMEOUT_SECONDS) -> int:
    """Require a complete readiness line, exact field types and a positive process ID.

    Parameters
    ----------
    stream
        Actual parent read end of the exclusively owned worker pipe.
    timeout
        Finite positive seconds for the entire frame, without resetting between chunks.

    Returns
    -------
    int
        Positive integer PID from an actual Boolean-true readiness frame.

    Raises
    ------
    TimeoutError
        If the full line does not arrive before the single deadline.
    ValueError
        If timeout, framing, strict UTF-8 JSON or readiness fields are invalid, or the frame
        exceeds 4096 bytes including its terminating newline.
    OSError
        If the actual pipe cannot be selected or read.
    """
    if not math.isfinite(timeout) or timeout <= 0:
        message = "readiness timeout must be finite and positive"
        raise ValueError(message)
    deadline = time.monotonic() + timeout
    frame = bytearray()
    while b"\n" not in frame:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([stream], [], [], remaining)[0]:
            message = "complete worker readiness timed out"
            raise TimeoutError(message)
        chunk = os.read(stream.fileno(), MAX_READINESS_BYTES + 1 - len(frame))
        if not chunk:
            message = "worker readiness ended before a complete newline frame"
            raise ValueError(message)
        frame.extend(chunk)
        if len(frame) > MAX_READINESS_BYTES:
            message = "worker readiness exceeds the 4096-byte frame limit"
            raise ValueError(message)
    ready = parse_json_object(bytes(frame), "worker readiness")
    if ready.keys() != {"ready", "pid"} or ready["ready"] is not True:
        message = "worker readiness requires exactly Boolean ready and integer pid fields"
        raise ValueError(message)
    pid = ready["pid"]
    if type(pid) is not int or pid <= 0:
        message = "worker readiness pid must be a positive integer"
        raise ValueError(message)
    return pid
