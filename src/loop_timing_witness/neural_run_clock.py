# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete neural run observations

"""Bind the original source clock schedule and finite simulator horizon."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .neural_run_native_clock import native_clock
from .neural_run_receipt_io import FILE, FLAG, TEXT, UNSIGNED, decode_actual_receipt

__all__ = ["FILE", "FLAG", "TEXT", "UNSIGNED", "analyze_source_clock", "decode_actual_receipt"]

if TYPE_CHECKING:
    from .neural_run_binding import BoundNeuralRun


def _clock(run: BoundNeuralRun) -> dict[str, Any]:
    """Bind the actual schedule to the frozen producer body before interpretation.

    Parameters
    ----------
    run
        Complete original bytes and admitted sources.

    Returns
    -------
    dict[str, Any]
        Strict original clock/edge schedule.

    Raises
    ------
    ValueError
        If the nested source reference does not bind the actual admitted producer.
    """
    fields: dict[str, Any] = dict.fromkeys(
        (
            "capture_half_period_units",
            "drain_half_period_units",
            "first_input_tick",
            "requested_contiguous_steps",
            "expected_state_observation_offset_ticks",
            "dedicated_start_marker_tick",
            "dedicated_end_marker_tick",
            "tail_checked_after_edge_tick",
            "observed_final_counter",
            "capture_horizon_edges",
        ),
        UNSIGNED,
    )
    return native_clock(run, fields)


def analyze_source_clock(run: BoundNeuralRun, completion: dict[str, Any]) -> tuple[str, ...]:
    """Reconcile the original simulator schedule with actual producer and horizon.

    Parameters
    ----------
    run
        Whole original bound run and actual frozen producer body.
    completion
        Admitted actual producer termination receipt.

    Returns
    -------
    tuple[str, ...]
        Located original schedule, clock and full-horizon inconsistencies.

    Raises
    ------
    ValueError
        If original schedule or its producer binding is uninterpretable.
    """
    clock = _clock(run)
    count = run.manifest["step_count"]
    failures = []
    if run.files["declared_clock_schedule"] != run.files["clock_schedule_ref"]:
        failures.append("Root and tool receipt clock schedule bytes differ.")
    expected_clock = {
        "simulation_time_unit": "1ns",
        "capture_half_period_units": 5,
        "drain_half_period_units": 5,
        "first_input_tick": 20,
        "requested_contiguous_steps": count,
        "expected_state_observation_offset_ticks": 1,
        "dedicated_start_marker_tick": 10,
        "dedicated_end_marker_tick": 30 + count,
        "tail_checked_after_edge_tick": 23 + count,
        "observed_final_counter": completion["final_counter"],
        "capture_horizon_edges": run.manifest["capture_horizon_edges"],
    }
    for name, expected in expected_clock.items():
        if clock[name] != expected:
            failures.append(f"Actual source clock schedule differs: {name}.")
    if not 30 + count < completion["final_counter"] < run.manifest["capture_horizon_edges"]:
        failures.append("Full final counter does not fit the admitted post-marker horizon.")
    return tuple(failures)
