# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — observed dedicated-hart capture to run-analysis manifest

"""Convert original AMP configuration and tracking without adding unobserved samples."""

from __future__ import annotations

import csv
import io
from typing import Any

from .amp_run_input import read_amp_run
from .native_tracking import decode_tracking


def fault_schedule(configuration: bytes) -> list[dict[str, Any]]:
    """Convert an admitted complete native fault schedule to the public run contract.

    Parameters
    ----------
    configuration
        Original complete native run configuration bytes.

    Returns
    -------
    list of dict of str to Any
        Actual configured fault kind, cycle and delay with no inferred fault.
    """
    read_amp_run(configuration)
    words = configuration.decode("ascii").split()
    fault = words[19]
    return (
        []
        if fault == "none"
        else [
            {
                "cycle": int(words[20]),
                "kind": "overload_request" if fault == "overload" else fault,
                "delay_periods": int(words[21]) if fault == "delay" else 0,
            }
        ]
    )


def tracking_csv(content: bytes, cycles: int, samples: int) -> bytes:
    """Convert original bounded Q8.24 observations to reproducible public CSV bytes.

    Parameters
    ----------
    content
        Original complete raw controller tracking stream.
    cycles
        Configured native cycle bound.
    samples
        Actual final logger sample count.

    Returns
    -------
    bytes
        Complete canonical observed tracking CSV, with no interpolated rows.
    """
    observations = decode_tracking(content, cycles, samples)
    with io.StringIO(newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["cycle", "reference", "output"])
        writer.writerows(observations)
        return stream.getvalue().encode("utf-8")
