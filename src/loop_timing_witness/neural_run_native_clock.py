# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — native precision clock source binding

"""Bind the actual native driver and precision before shared schedule analysis."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from .neural_event_stream import NeuralCaptureRefusalError
from .neural_run_receipt_io import FILE, TEXT, UNSIGNED, decode_actual_receipt

NATIVE_HALF_PERIOD_PS = 5000

if TYPE_CHECKING:
    from .neural_run_binding import BoundNeuralRun


def native_clock(run: BoundNeuralRun, fields: dict[str, Any]) -> dict[str, Any]:
    """Require the real native producer and its nanosecond/picosecond precision.

    Parameters
    ----------
    run
        Bound complete native source and schedule.
    fields
        Common schedule count/edge fields already required for every producer.

    Returns
    -------
    dict[str, Any]
        Complete native schedule for independent common edge comparisons.

    Raises
    ------
    ValueError
        If native precision or complete source binding cannot be interpreted.
    """
    clock = decode_actual_receipt(
        run.files["clock_schedule_ref"],
        "native clock",
        {
            **fields,
            "scope": TEXT,
            "source_producer": FILE,
            "simulation_time_unit": TEXT,
            "simulation_time_precision": TEXT,
            "driver_half_period_precision_ticks": UNSIGNED,
        },
    )
    reference = clock["source_producer"]
    body = run.sources["native/native_trial.cpp"]
    if (
        reference["path"] != "native/native_trial.cpp"
        or reference["sha256"] != hashlib.sha256(body).hexdigest()
        or reference["byte_length"] != len(body)
        or clock["simulation_time_precision"] != "1ps"
        or clock["driver_half_period_precision_ticks"] != NATIVE_HALF_PERIOD_PS
    ):
        message = "Actual native clock/source/precision differs."
        raise NeuralCaptureRefusalError(message)
    return clock
