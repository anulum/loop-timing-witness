# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original neural step identity and observation phase

"""Join decoded neural steps without repairing loss or changing their identities."""

from __future__ import annotations

from dataclasses import dataclass

from .neural_event_stream import (
    ENCODER_TICK_LIMIT,
    MAX_CHANNEL_POPULATION,
    NeuralCaptureRefusalError,
    NeuralChannel,
)


@dataclass(frozen=True, slots=True)
class NeuralStepInterval:
    """One available input/state pair, including an invalid observed interval.

    Attributes
    ----------
    identity
        Unchanged step identity shared by the two original records.
    applied_tick, observed_tick
        Original common-counter stamps for input and registered state observation.
    ticks
        Signed observed-minus-applied interval; invalid phases remain visible.
    """

    identity: int
    applied_tick: int
    observed_tick: int
    ticks: int


@dataclass(frozen=True, slots=True)
class NeuralStepTiming:
    """Step-population and phase findings, separate from complete run acceptance.

    Attributes
    ----------
    intervals
        Available pairs in original input order, retaining gaps and invalid phases.
    refusals
        Located failures of markers, population, cadence or one-edge observation.
        An empty tuple establishes these predicates only. Numerical equality,
        encoder provenance, capture counters, source pins and export finalisation
        require the complete run verifier independently.
    """

    intervals: tuple[NeuralStepInterval, ...]
    refusals: tuple[str, ...]


def _alignment_refusals(channels: tuple[NeuralChannel, ...], horizon: int) -> list[str]:
    """Check dedicated marker presence, channel equality and the declared horizon.

    Parameters
    ----------
    channels
        Validated input, state and service streams in that order.
    horizon
        Exclusive bound on all capture ticks.

    Returns
    -------
    list[str]
        Actual marker failures; no data endpoints substitute for missing markers.
    """
    refusals = []
    for channel in channels:
        if channel.start_tick is None or channel.end_tick is None:
            refusals.append(f"{channel.role}: missing alignment marker")
        elif channel.end_tick >= horizon:
            refusals.append(f"{channel.role}: end marker exceeds capture horizon")
    markers = {(channel.start_tick, channel.end_tick) for channel in channels}
    if len(markers) != 1:
        refusals.append("channels: alignment marker ticks differ")
    return refusals


def _population_refusals(channel: NeuralChannel, step_count: int) -> list[str]:
    """Check the full requested step sequence without sorting or relabelling.

    Parameters
    ----------
    channel
        Decoded input or state stream preserving original row order.
    step_count
        Requested finite step population.

    Returns
    -------
    list[str]
        A located population failure, or an empty list for the exact sequence.
    """
    if tuple(event.identity for event in channel.events) != tuple(range(step_count)):
        return [f"{channel.role}: step population differs from requested identities"]
    return []


def correlate_neural_steps(
    channels: tuple[NeuralChannel, NeuralChannel, NeuralChannel],
    step_count: int,
    capture_horizon_edges: int,
) -> NeuralStepTiming:
    """Check continuous input and one-edge state observation through exact step keys.

    Parameters
    ----------
    channels
        Public-decoder results in input, state, service order, with exact raw bytes
        already bound to their run. Service contributes dedicated alignment markers;
        this function makes no packet-to-spike or encoder-service assertion.
    step_count
        Requested population, between one and 1,000 inclusive.
    capture_horizon_edges
        Exclusive common-counter horizon, less than the 16-bit encoder wrap limit.

    Returns
    -------
    NeuralStepTiming
        Every available same-identity interval and explicit contract refusals.
        Missing pairs stay absent; no zip truncation, interpolation or shifted IDs.

    Raises
    ------
    NeuralCaptureRefusalError
        If channel roles, population or horizon declarations are unsupported.
    """
    if tuple(channel.role for channel in channels) != ("input", "state", "service"):
        message = "Neural timing requires input, state, service channels in that order."
        raise NeuralCaptureRefusalError(message)
    if type(step_count) is not int or not 1 <= step_count <= MAX_CHANNEL_POPULATION:
        message = "Invalid neural timing step population."
        raise NeuralCaptureRefusalError(message)
    if type(capture_horizon_edges) is not int or not 0 < capture_horizon_edges < ENCODER_TICK_LIMIT:
        message = "Invalid neural timing no-wrap horizon."
        raise NeuralCaptureRefusalError(message)
    applied, observed, _ = channels
    refusals = _alignment_refusals(channels, capture_horizon_edges)
    refusals.extend(_population_refusals(applied, step_count))
    refusals.extend(_population_refusals(observed, step_count))
    state_by_identity = {event.identity: event.ticks for event in observed.events}
    intervals = []
    previous_tick: int | None = None
    for event in applied.events:
        if previous_tick is not None and event.ticks != previous_tick + 1:
            refusals.append(
                f"input step {event.identity}: application cadence differs from one tick"
            )
        previous_tick = event.ticks
        observed_tick = state_by_identity.get(event.identity)
        if observed_tick is None:
            continue
        ticks = observed_tick - event.ticks
        intervals.append(NeuralStepInterval(event.identity, event.ticks, observed_tick, ticks))
        if ticks != 1:
            refusals.append(f"state step {event.identity}: observation phase differs from one tick")
    return NeuralStepTiming(tuple(intervals), tuple(refusals))
