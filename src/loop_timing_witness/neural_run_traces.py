# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete neural run observations

"""Interpret complete original ASCII traces and join exact witness identities."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .neural_event_stream import NeuralCaptureRefusalError

if TYPE_CHECKING:
    from .neural_run_binding import BoundNeuralRun

MIN_S16 = -(1 << 15)
MAX_S16 = (1 << 15) - 1
MIN_S64 = -(1 << 63)
MAX_S64 = (1 << 63) - 1
TICK_LIMIT = 1 << 16


@dataclass(frozen=True, slots=True)
class NeuralTraceAnalysis:
    """Independent findings from all complete original trace rows.

    Attributes
    ----------
    raw_spikes, service_packets
        Counts derived from complete raw-spike and service traces.
    numerical, source, service, joins
        Located failures for oracle equality, original input/raw provenance,
        one-neuron packet origin and exact-identity witness joins respectively.
    """

    raw_spikes: int
    service_packets: int
    numerical: tuple[str, ...]
    source: tuple[str, ...]
    service: tuple[str, ...]
    joins: tuple[str, ...]


def decode_rows(raw: bytes, columns: int, source: str) -> list[tuple[int, ...]]:
    """Decode LF-terminated ASCII signed64 rows without whitespace repairs.

    Parameters
    ----------
    raw
        Complete file bytes already bound to the full manifest.
    columns
        Fixed original producer column count.
    source
        Semantic role used for an authored refusal.

    Returns
    -------
    list[tuple[int, ...]]
        All original fields in original order; empty service files stay empty.

    Raises
    ------
    ValueError
        If ASCII, LF termination, exact columns, decimal grammar or signed64 bounds fail.
    """
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        message = f"Original {source} trace is not ASCII."
        raise NeuralCaptureRefusalError(message) from exc
    if text and not text.endswith("\n"):
        message = f"Original {source} trace lacks its final newline."
        raise NeuralCaptureRefusalError(message)
    rows = []
    for line in text.split("\n")[:-1]:
        fields = line.split(" ")
        if len(fields) != columns or any(
            re.fullmatch(r"[+-]?[0-9]{1,20}", field) is None for field in fields
        ):
            message = f"Malformed original {source} trace row."
            raise NeuralCaptureRefusalError(message)
        row = tuple(int(field) for field in fields)
        if any(not MIN_S64 <= value <= MAX_S64 for value in row):
            message = f"Original {source} trace integer outside signed64 range."
            raise NeuralCaptureRefusalError(message)
        rows.append(row)
    return rows


def _full_rows(run: BoundNeuralRun) -> dict[str, list[tuple[int, ...]]]:
    """Require complete original identity sequences, finite ranges and projections.

    Parameters
    ----------
    run
        Whole bound run and original file bytes.

    Returns
    -------
    dict[str, list[tuple[int, ...]]]
        All full typed rows after population/identity/range admission.

    Raises
    ------
    ValueError
        If complete required sequences, original identities or numeric ranges fail.
    """
    widths = {
        "original_stimulus": 4,
        "reference_projection": 2,
        "input_trace": 7,
        "numerical_trace": 5,
        "raw_spike_trace": 4,
        "numerical_projection": 2,
        "service_trace": 5,
    }
    rows = {name: decode_rows(run.files[name], width, name) for name, width in widths.items()}
    count = run.manifest["step_count"]
    epoch = run.manifest["epoch"]
    for name, data in rows.items():
        if name != "service_trace" and len(data) != count:
            message = f"Complete requested population required: {name}."
            raise NeuralCaptureRefusalError(message)
    for name in ("input_trace", "numerical_trace", "raw_spike_trace"):
        if tuple(row[:2] for row in rows[name]) != tuple((epoch, index) for index in range(count)):
            message = f"Original epoch/step sequence differs: {name}."
            raise NeuralCaptureRefusalError(message)
    _validate_ranges(rows, run.manifest["capture_horizon_edges"], epoch)
    return rows


def _validate_ranges(rows: dict[str, list[tuple[int, ...]]], horizon: int, epoch: int) -> None:
    """Require the original numeric ranges and complete service identities.

    Parameters
    ----------
    rows
        Complete admitted original full-population trace rows.
    horizon
        Admitted exclusive no-wrap observation horizon.
    epoch
        Original root epoch, required by every identified trace.

    Raises
    ------
    ValueError
        If any numeric range or service identity is invalid.
    """
    for name in ("original_stimulus", "input_trace"):
        values = [
            value
            for row in rows[name]
            for value in (row if name == "original_stimulus" else row[2:6])
        ]
        if any(not MIN_S16 <= value <= MAX_S16 for value in values):
            message = f"Original signed16 stimulus outside range: {name}."
            raise NeuralCaptureRefusalError(message)
    for name in ("reference_projection", "numerical_projection", "numerical_trace"):
        pairs = [row[2:4] if name == "numerical_trace" else row for row in rows[name]]
        if any(
            spike not in (0, 1) or not MIN_S16 <= voltage <= MAX_S16 for spike, voltage in pairs
        ):
            message = f"Original binary spike/signed16 state outside range: {name}."
            raise NeuralCaptureRefusalError(message)
    if any(row[2] not in (0, 1) for row in rows["raw_spike_trace"]):
        message = "Original raw spike outside binary range."
        raise NeuralCaptureRefusalError(message)
    for name in ("input_trace", "numerical_trace", "raw_spike_trace", "service_trace"):
        if any(not 0 <= row[-1] < horizon for row in rows[name]):
            message = f"Original observed tick outside no-wrap horizon: {name}."
            raise NeuralCaptureRefusalError(message)
    service = rows["service_trace"]
    if tuple(row[:3] for row in service) != tuple(
        (epoch, index, 0) for index in range(len(service))
    ):
        message = "Original service epoch/ordinal/neuron identity sequence differs."
        raise NeuralCaptureRefusalError(message)
    if any(not 0 <= row[3] < TICK_LIMIT for row in service):
        message = "Original embedded service timestamp outside unsigned16 range."
        raise NeuralCaptureRefusalError(message)


def _service_findings(
    service: list[tuple[int, ...]],
    spikes: list[tuple[int, ...]],
) -> tuple[str, ...]:
    """Compare actual single-neuron service phases with all original raw spikes.

    Parameters
    ----------
    service
        Admitted original service ordinal rows.
    spikes
        All asserted original raw-spike rows in complete source order.

    Returns
    -------
    tuple[str, ...]
        Independent packet-population and embedded/source phase failures.
        Non-coalescence source monitor admission remains a receipt predicate.
    """
    failures = []
    if len(service) != len(spikes):
        failures.append("Service population differs from complete original raw spikes.")
    for ordinal, row in enumerate(service):
        if row[4] != row[3] + 1:
            failures.append(f"Service {ordinal}: embedded-to-observed phase differs.")
        if ordinal >= len(spikes) or row[4] != spikes[ordinal][3] + 2:
            failures.append(f"Service {ordinal}: raw-spike-to-service phase differs.")
    return tuple(failures)


def analyze_original_traces(run: BoundNeuralRun) -> NeuralTraceAnalysis:
    """Interpret all complete source traces and independently recompute equality.

    Parameters
    ----------
    run
        Full bound original run. No files are re-read or projected onto disk.

    Returns
    -------
    NeuralTraceAnalysis
        Actual derived counts and distinct numerical, source, service and join
        findings. Numerical equality alone cannot establish timing acceptance.

    Raises
    ------
    ValueError
        If full population, identity or numeric grammar prevents reliable analysis.
    """
    rows = _full_rows(run)
    numerical = rows["numerical_trace"]
    expected = rows["reference_projection"]
    actual = [row[2:4] for row in numerical]
    numeric = [
        f"Numerical step {index}: original oracle differs."
        for index, pair in enumerate(actual)
        if pair != expected[index]
    ]
    source = []
    if actual != rows["numerical_projection"]:
        source.append("Declared numerical projection differs from the full identified trace.")
    for index, row in enumerate(rows["input_trace"]):
        if row[2:6] != rows["original_stimulus"][index]:
            source.append(f"Input step {index}: original stimulus fields differ.")
    inputs = rows["input_trace"]
    for index, row in enumerate(rows["raw_spike_trace"]):
        if row[2] != expected[index][0] or row[3] != inputs[index][6] + 1:
            source.append(f"Raw step {index}: original spike or source phase differs.")
    spikes = [row for row in rows["raw_spike_trace"] if row[2] == 1]
    joins: list[str] = []
    for channel, name in zip(
        run.capture.channels, ("input_trace", "numerical_trace", "service_trace"), strict=True
    ):
        observed = {event.identity: event.ticks for event in channel.events}
        joins.extend(
            f"{channel.role} identity {row[1]}: witness unavailable or differs."
            for row in rows[name]
            if observed.get(row[1]) != row[-1]
        )
    return NeuralTraceAnalysis(
        len(spikes),
        len(rows["service_trace"]),
        tuple(numeric),
        tuple(source),
        _service_findings(rows["service_trace"], spikes),
        tuple(joins),
    )
