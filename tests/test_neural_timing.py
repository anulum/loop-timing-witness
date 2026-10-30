# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — real neural step population and observation-phase controls

"""Correlate actual shared-counter exports and retain lost or shifted observations."""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

import pytest

from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError, decode_neural_channel
from loop_timing_witness.neural_timing import correlate_neural_steps

if TYPE_CHECKING:
    from test_neural_event_stream import CaptureStreams

pytest_plugins = ("test_neural_event_stream",)


@pytest.mark.parametrize(("empty_service", "step_count"), [(0, 4), (1, 4), (0, 1000), (1, 1000)])
def test_real_phased_step_join_and_empty_service(
    capture_streams: CaptureStreams, empty_service: int, step_count: int
) -> None:
    """Join actual known-edge instrument stimuli through the public decoder and correlator.

    Parameters
    ----------
    capture_streams
        Actual shared-witness producer; this is a port control, not a neural wrapper.
    empty_service
        Select a marker-only service stream with different data endpoints.
    step_count
        Small control population or the whole bounded 1,000-step stream before drain.
    """
    first, second, third = capture_streams(empty_service, 0, 1, step_count, 3)
    channels = (
        decode_neural_channel(first, "input", step_count),
        decode_neural_channel(second, "state", step_count),
        decode_neural_channel(third, "service", 0 if empty_service else step_count),
    )
    result = correlate_neural_steps(channels, step_count, step_count + 100)
    assert result.refusals == ()
    assert [interval.identity for interval in result.intervals] == list(range(step_count))
    assert [interval.applied_tick for interval in result.intervals] == list(
        range(20, 20 + step_count)
    )
    assert [interval.observed_tick for interval in result.intervals] == list(
        range(21, 21 + step_count)
    )
    assert [interval.ticks for interval in result.intervals] == [1] * step_count
    assert [event.ticks for event in channels[2].events] == (
        [] if empty_service else list(range(22, 22 + step_count))
    )


def test_real_step_join_retains_loss_and_refuses_changed_phases(
    capture_streams: CaptureStreams,
) -> None:
    """Preserve actual gaps and refuse marker drift, extra rows and shifted sample edges.

    Parameters
    ----------
    capture_streams
        Real known-edge capture bytes used as the damage-control baseline.
    """
    first, second, third = capture_streams(0, 0, 1, 4, 3)
    baseline = (
        decode_neural_channel(first, "input", 4),
        decode_neural_channel(second, "state", 4),
        decode_neural_channel(third, "service", 4),
    )
    missing_input = decode_neural_channel(first[:32] + first[48:], "input", 4)
    result = correlate_neural_steps((missing_input, baseline[1], baseline[2]), 4, 100)
    assert [interval.identity for interval in result.intervals] == [0, 2, 3]
    assert result.refusals == (
        "input: step population differs from requested identities",
        "input step 2: application cadence differs from one tick",
    )
    missing_state = decode_neural_channel(second[:32] + second[48:], "state", 4)
    result = correlate_neural_steps((baseline[0], missing_state, baseline[2]), 4, 100)
    assert [interval.identity for interval in result.intervals] == [0, 2, 3]
    assert result.refusals == ("state: step population differs from requested identities",)
    absent_input = decode_neural_channel(b"", "input", 4)
    result = correlate_neural_steps((absent_input, baseline[1], baseline[2]), 4, 100)
    assert result.intervals == ()
    assert "input: missing alignment marker" in result.refusals
    shifted = bytearray(second)
    for index in range(4):
        struct.pack_into("<Q", shifted, 16 * (index + 1) + 8, 20 + index)
    shifted_state = decode_neural_channel(bytes(shifted), "state", 4)
    result = correlate_neural_steps((baseline[0], shifted_state, baseline[2]), 4, 100)
    assert [interval.ticks for interval in result.intervals] == [0] * 4
    assert result.refusals == tuple(
        f"state step {index}: observation phase differs from one tick" for index in range(4)
    )
    changed_marker = bytearray(third)
    struct.pack_into("<Q", changed_marker, 8, 11)
    changed_service = decode_neural_channel(bytes(changed_marker), "service", 4)
    result = correlate_neural_steps((baseline[0], baseline[1], changed_service), 4, 100)
    assert result.refusals == ("channels: alignment marker ticks differ",)
    result = correlate_neural_steps(baseline, 4, 34)
    assert result.refusals == tuple(
        f"{role}: end marker exceeds capture horizon" for role in ("input", "state", "service")
    )
    result = correlate_neural_steps(baseline, 3, 100)
    assert result.refusals == (
        "input: step population differs from requested identities",
        "state: step population differs from requested identities",
    )


def test_real_neural_step_declarations_refuse_unbounded_or_mislabelled_runs(
    capture_streams: CaptureStreams,
) -> None:
    """Reject swapped channel roles, invalid populations and encoder-wrap horizons.

    Parameters
    ----------
    capture_streams
        Actual phased stream producer for the unchanged declaration baseline.
    """
    first, second, third = capture_streams(0, 0, 1, 4, 3)
    channels = (
        decode_neural_channel(first, "input", 4),
        decode_neural_channel(second, "state", 4),
        decode_neural_channel(third, "service", 4),
    )
    with pytest.raises(NeuralCaptureRefusalError, match="channels in that order"):
        correlate_neural_steps((channels[1], channels[0], channels[2]), 4, 100)
    for population in [-1, 0, 1001, True]:
        with pytest.raises(NeuralCaptureRefusalError, match="step population"):
            correlate_neural_steps(channels, population, 100)
    for horizon in [-1, 0, 65536, True]:
        with pytest.raises(NeuralCaptureRefusalError, match="no-wrap horizon"):
            correlate_neural_steps(channels, 4, horizon)
