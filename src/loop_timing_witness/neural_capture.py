# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete original channel and projection capture loading

"""Bind and reconcile the complete timing-capture inputs of a neural run."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from .neural_capture_counts import decode_neural_capture_counts, reconcile_neural_capture
from .neural_capture_files import read_neural_bound_file
from .neural_event_stream import (
    ENCODER_TICK_LIMIT,
    MAX_CHANNEL_POPULATION,
    NEURAL_RECORD,
    NeuralCaptureRefusalError,
    decode_neural_channel,
)
from .neural_timing import correlate_neural_steps

if TYPE_CHECKING:
    from pathlib import Path

    from .neural_capture_counts import NeuralCaptureAccounting, NeuralCaptureCounts
    from .neural_event_stream import NeuralChannel
    from .neural_timing import NeuralStepTiming

COUNTER_RECEIPT_MAX_BYTES: Final = 4096
ALIGNMENT_MARKER_COUNT: Final = 2


@dataclass(frozen=True, slots=True)
class NeuralChannelFiles:
    """Original file references extracted from a source-owned run binding.

    Attributes
    ----------
    role
        Input, state or service, in that fixed semantic order.
    capture, payload, markers
        Closed path/SHA-256/byte-length references to the full original stream and
        its exact data and marker projections. No file is synthesized by loading.
    """

    role: str
    capture: object
    payload: object
    markers: object


@dataclass(frozen=True, slots=True)
class NeuralCaptureConfiguration:
    """Finite capture populations and shared-counter horizon from the full run.

    Attributes
    ----------
    step_count
        Requested input/state steps, one through 1,000.
    service_packets
        Requested complete service-ordinal population, zero through step_count.
        It is not inferred from captured rows or equated with raw spike count.
    capture_horizon_edges
        Exclusive capture-tick bound, below the 16-bit encoder wrap horizon.
    """

    step_count: int
    service_packets: int
    capture_horizon_edges: int


@dataclass(frozen=True, slots=True)
class NeuralCaptureBundle:
    """Bound capture inputs and their independent completeness findings.

    Attributes
    ----------
    configuration
        Original requested populations and horizon, never inferred after loss.
    captures, payloads, markers, counter_receipt
        Complete declared file bytes verified against their references, for reuse.
        Declared projections remain distinct from projections of the raw capture.
    channels
        Original decoded records and projections, preserving missing identities.
    counts, accounting
        Bound original counter fields and per-channel loss/export findings.
    steps
        Available exact-identity intervals and population/marker/phase findings.
    refusals
        All located capture failures, including projection and service population.
        An empty tuple establishes capture predicates only; numerical equality,
        service provenance/tail, source qualification and whole-run acceptance
        still require the full run verifier and its actual source-owned traces.
    """

    configuration: NeuralCaptureConfiguration
    captures: tuple[bytes, bytes, bytes]
    payloads: tuple[bytes, bytes, bytes]
    markers: tuple[bytes, bytes, bytes]
    counter_receipt: bytes
    channels: tuple[NeuralChannel, NeuralChannel, NeuralChannel]
    counts: tuple[NeuralCaptureCounts, NeuralCaptureCounts, NeuralCaptureCounts]
    accounting: tuple[NeuralCaptureAccounting, NeuralCaptureAccounting, NeuralCaptureAccounting]
    steps: NeuralStepTiming
    refusals: tuple[str, ...]


def _validate_configuration(configuration: NeuralCaptureConfiguration) -> None:
    """Refuse unsupported populations and wrap horizons before opening files.

    Parameters
    ----------
    configuration
        Original admitted full-run capture declarations.

    Raises
    ------
    NeuralCaptureRefusalError
        If a value is not a finite supported integer, including boolean counts.
    """
    fields = (
        (configuration.step_count, 1, MAX_CHANNEL_POPULATION, "step_count"),
        (configuration.service_packets, 0, configuration.step_count, "service_packets"),
        (configuration.capture_horizon_edges, 1, ENCODER_TICK_LIMIT - 1, "capture_horizon_edges"),
    )
    for value, minimum, maximum, field in fields:
        if type(value) is not int or not minimum <= value <= maximum:
            message = f"Invalid neural capture configuration: {field}."
            raise NeuralCaptureRefusalError(message)


def _load_channel(
    directory: Path, files: NeuralChannelFiles, counts: NeuralCaptureCounts, population: int
) -> tuple[bytes, bytes, bytes, NeuralChannel, NeuralCaptureAccounting, list[str]]:
    """Bind one original stream, check exact projections and reconcile its counts.

    Parameters
    ----------
    directory
        Immutable source-custodied run directory.
    files
        Original full/payload/marker references for the declared channel.
    counts
        Original corresponding fields from the bound counter receipt.
    population
        Requested step or service-ordinal population.

    Returns
    -------
    tuple[bytes, bytes, bytes, NeuralChannel, NeuralCaptureAccounting, list[str]]
        Original capture/payload/marker bytes, observations, accounting and failures.
    """
    raw = read_neural_bound_file(
        directory, files.capture, (population + ALIGNMENT_MARKER_COUNT) * NEURAL_RECORD.size
    )
    channel = decode_neural_channel(raw, files.role, population)
    payload = read_neural_bound_file(directory, files.payload, population * NEURAL_RECORD.size)
    markers = read_neural_bound_file(
        directory, files.markers, ALIGNMENT_MARKER_COUNT * NEURAL_RECORD.size
    )
    accounting = reconcile_neural_capture(channel, counts)
    refusals = list(accounting.refusals)
    if payload != channel.payload_bytes:
        refusals.append(f"{files.role}: payload file differs from original capture projection")
    if markers != channel.marker_bytes:
        refusals.append(f"{files.role}: marker file differs from original capture projection")
    if counts.attempts != population + ALIGNMENT_MARKER_COUNT:
        refusals.append(f"{files.role}: attempts differ from requested data and alignment markers")
    return raw, payload, markers, channel, accounting, refusals


def load_neural_capture(
    directory: Path,
    files: tuple[NeuralChannelFiles, NeuralChannelFiles, NeuralChannelFiles],
    counter_reference: object,
    configuration: NeuralCaptureConfiguration,
) -> NeuralCaptureBundle:
    """Load complete source-bound capture inputs and aggregate independent failures.

    Parameters
    ----------
    directory
        Immutable run directory; files remain frozen throughout full verification.
    files
        Input/state/service references from the complete run binding, in that order.
    counter_reference
        Closed path/SHA-256/byte-length reference to the original counter receipt.
        Its complete source-owned body is bounded to 4,096 bytes.
    configuration
        Requested full populations and finite no-wrap horizon, not observed counts.

    Returns
    -------
    NeuralCaptureBundle
        Verified original bytes, all observations, counts and located capture failures.
        A partial capture remains visible, with its original IDs and drop-count bounds.

    Raises
    ------
    NeuralCaptureRefusalError
        If configuration, role order, raw file binding, receipt or record grammar
        prevents reliable interpretation. Known population, projection, loss and
        phase failures instead remain explicit in the returned capture findings.
    """
    _validate_configuration(configuration)
    if tuple(item.role for item in files) != ("input", "state", "service"):
        message = "Neural capture files require input, state, service order."
        raise NeuralCaptureRefusalError(message)
    counter_receipt = read_neural_bound_file(
        directory, counter_reference, COUNTER_RECEIPT_MAX_BYTES
    )
    counts = decode_neural_capture_counts(counter_receipt)
    captures = []
    payloads = []
    markers = []
    channels = []
    reports = []
    refusals = []
    for index, item in enumerate(files):
        population = (
            configuration.service_packets if item.role == "service" else configuration.step_count
        )
        raw, payload, marker, channel, accounting, failures = _load_channel(
            directory, item, counts[index], population
        )
        captures.append(raw)
        payloads.append(payload)
        markers.append(marker)
        channels.append(channel)
        reports.append(accounting)
        refusals.extend(failures)
    ordered_channels = (channels[0], channels[1], channels[2])
    steps = correlate_neural_steps(
        ordered_channels, configuration.step_count, configuration.capture_horizon_edges
    )
    refusals.extend(steps.refusals)
    if tuple(event.identity for event in channels[2].events) != tuple(
        range(configuration.service_packets)
    ):
        refusals.append("service: packet population differs from requested identities")
    return NeuralCaptureBundle(
        configuration,
        (captures[0], captures[1], captures[2]),
        (payloads[0], payloads[1], payloads[2]),
        (markers[0], markers[1], markers[2]),
        counter_receipt,
        ordered_channels,
        counts,
        (reports[0], reports[1], reports[2]),
        steps,
        tuple(refusals),
    )
