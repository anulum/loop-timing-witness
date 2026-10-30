# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual joint reset and fresh-epoch analysis

"""Reconcile the actual abandoned prefix, joint reset and fresh complete epoch."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .neural_event_stream import NeuralCaptureRefusalError
from .neural_run_clock import FLAG, UNSIGNED, decode_actual_receipt
from .neural_run_traces import decode_rows

if TYPE_CHECKING:
    from .neural_run_binding import BoundNeuralRun

MIN_PREFIX_INPUTS = 2
PREFIX_WIDTHS = {"input": 7, "numerical": 5, "raw_spike": 4, "service": 5}
RESET_FLAGS = (
    "encoder_pending_before_reset",
    "all_three_fifos_queued_before_reset",
    "all_three_fifos_empty_after_reset",
    "model_and_encoder_quiescent_after_reset",
)


def _prefix_rows(run: BoundNeuralRun) -> dict[str, list[tuple[int, ...]]]:
    """Decode all original abandoned source traces and retain their epoch/IDs.

    Parameters
    ----------
    run
        Whole fresh-epoch run with full original prefix references.

    Returns
    -------
    dict[str, list[tuple[int, ...]]]
        All original prefix fields in their original source sequence.

    Raises
    ------
    ValueError
        If abandoned epoch/step/service identity or numeric grammar is ambiguous.
    """
    rows = {
        name: decode_rows(run.files[f"abandoned_{name}_trace"], width, f"abandoned {name}")
        for name, width in PREFIX_WIDTHS.items()
    }
    for name, data in rows.items():
        if tuple(row[:2] for row in data) != tuple((0, index) for index in range(len(data))):
            message = f"Original abandoned epoch/identity sequence differs: {name}."
            raise NeuralCaptureRefusalError(message)
    return rows


def _prefix_findings(
    run: BoundNeuralRun,
    rows: dict[str, list[tuple[int, ...]]],
) -> tuple[str, ...]:
    """Compare all original abandoned source fields and phases with original fixture.

    Parameters
    ----------
    run
        Whole source-bound original stimulus and oracle.
    rows
        Admitted original abandoned source sequences.

    Returns
    -------
    tuple[str, ...]
        Original input/raw/numerical/packet-phase inconsistencies, without
        inferring a complete capture of the deliberately abandoned epoch.
    """
    stimuli = decode_rows(run.files["original_stimulus"], 4, "original stimulus")
    expected = decode_rows(run.files["reference_projection"], 2, "original reference")
    failures = []
    for index, row in enumerate(rows["input"]):
        if index >= len(stimuli) or row[2:6] != stimuli[index] or row[6] != 20 + index:
            failures.append(f"Abandoned input {index}: original fixture or source phase differs.")
    for index, row in enumerate(rows["numerical"]):
        if index >= len(expected) or row[2:4] != expected[index] or row[4] != 21 + index:
            failures.append(
                f"Abandoned numerical {index}: original oracle or source phase differs."
            )
    for index, row in enumerate(rows["raw_spike"]):
        if index >= len(expected) or row[2] != expected[index][0] or row[3] != 21 + index:
            failures.append(f"Abandoned raw spike {index}: original flag or source phase differs.")
    if rows["service"]:
        failures.append("Abandoned encoder pending spike was already serviced before reset.")
    return tuple(failures)


def analyze_actual_reset(run: BoundNeuralRun) -> tuple[str, ...]:
    """Reconcile real queued/inflight/pending reset evidence with fresh original run.

    Parameters
    ----------
    run
        Complete source-bound original run. Epoch0 source has no reset claim;
        only the exact admitted reset producer requires all bound prefix evidence.

    Returns
    -------
    tuple[str, ...]
        Known joint-reset/prefix/epoch inconsistencies. Empty findings in epoch0
        do not imply this reset experiment was exercised.

    Raises
    ------
    ValueError
        If original reset receipt or prefix grammar prevents reliable analysis.
    """
    if "reset_epoch_receipt" not in run.files:
        return ()
    counts = (
        "abandoned_epoch",
        "next_epoch",
        "prefix_inputs",
        "prefix_states",
        "prefix_raw_rows",
        "prefix_raw_spikes",
        "prefix_services",
        "counter_before_reset",
        "uncommitted_input_records_before_reset",
        "reset_counter",
        "reset_service_ordinal",
    )
    arrays = ("prefix_attempts", "prefix_accepted", "reset_attempts", "reset_accepted")
    triple = {"type": "array", "minItems": 3, "maxItems": 3, "items": UNSIGNED}
    receipt = decode_actual_receipt(
        run.files["reset_epoch_receipt"],
        "actual joint reset",
        {
            **dict.fromkeys(counts, UNSIGNED),
            **dict.fromkeys(arrays, triple),
            **dict.fromkeys(RESET_FLAGS, FLAG),
        },
    )
    rows = _prefix_rows(run)
    inputs = len(rows["input"])
    states = len(rows["numerical"])
    raw = len(rows["raw_spike"])
    actual = {
        "abandoned_epoch": 0,
        "next_epoch": run.manifest["epoch"],
        "prefix_inputs": inputs,
        "prefix_states": states,
        "prefix_raw_rows": raw,
        "prefix_raw_spikes": sum(row[2] for row in rows["raw_spike"]),
        "prefix_services": len(rows["service"]),
        "counter_before_reset": 20 + inputs,
        "uncommitted_input_records_before_reset": 1,
        "prefix_attempts": [inputs, states, 1],
        "prefix_accepted": [inputs, states, 1],
        "reset_counter": 0,
        "reset_attempts": [0, 0, 0],
        "reset_accepted": [0, 0, 0],
        "reset_service_ordinal": 0,
        **dict.fromkeys(RESET_FLAGS, True),
    }
    failures = [
        f"Actual joint reset predicate differs: {name}."
        for name, value in actual.items()
        if receipt[name] != value
    ]
    if not (
        inputs >= MIN_PREFIX_INPUTS
        and states == raw == inputs - 1
        and receipt["prefix_raw_spikes"] == 1
        and not rows["service"]
    ):
        failures.append(
            "Actual prefix did not establish the selected queued/inflight/pending reset."
        )
    return (*_prefix_findings(run, rows), *failures)
