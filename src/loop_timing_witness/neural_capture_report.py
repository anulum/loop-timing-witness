# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original capture observations and located report findings

"""Report verified capture bytes and findings without inventing whole-run acceptance."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from .neural_event_stream import NEURAL_RECORD

if TYPE_CHECKING:
    from .neural_capture import NeuralCaptureBundle


def _channel_report(capture: NeuralCaptureBundle, index: int) -> dict[str, object]:
    """Retain one channel's original byte references, record positions and counters.

    Parameters
    ----------
    capture
        Bound complete capture inputs and independently located failures.
    index
        Fixed input, state or service channel index.

    Returns
    -------
    dict[str, object]
        JSON-compatible original observations, markers, counters and source hashes.
    """
    channel = capture.channels[index]
    counts = capture.counts[index]
    accounting = capture.accounting[index]
    sources = {
        name: {"sha256": hashlib.sha256(content).hexdigest(), "byte_length": len(content)}
        for name, content in (
            ("capture", capture.captures[index]),
            ("payload", capture.payloads[index]),
            ("markers", capture.markers[index]),
        )
    }
    first_data_record = 1 if channel.start_tick is not None else 0
    return {
        "role": channel.role,
        "sources": sources,
        "derived_projections": {
            name: {"sha256": hashlib.sha256(content).hexdigest(), "byte_length": len(content)}
            for name, content in (
                ("payload", channel.payload_bytes),
                ("markers", channel.marker_bytes),
            )
        },
        "start_marker_tick": channel.start_tick,
        "end_marker_tick": channel.end_tick,
        "observed_data_records": len(channel.events),
        "observed_total_records": accounting.observed_records,
        "attempts": counts.attempts,
        "accepted": counts.accepted,
        "drained": counts.drained,
        "overflowed": counts.overflowed,
        "drop_counter": {
            "bits": counts.drop_counter_bits,
            "value": counts.dropped,
            "lower_bound": accounting.dropped_lower_bound,
            "exact": accounting.drop_count_exact,
        },
        "events": [
            {
                "identity": event.identity,
                "ticks": event.ticks,
                "record_byte_offset": (ordinal + first_data_record) * NEURAL_RECORD.size,
            }
            for ordinal, event in enumerate(channel.events)
        ],
        "accounting_refusals": list(accounting.refusals),
    }


def neural_capture_report(capture: NeuralCaptureBundle) -> dict[str, object]:
    """Produce the capture component of a complete run report from verified bytes.

    Parameters
    ----------
    capture
        Actual load_neural_capture result. Original source custody stays frozen;
        neither file content nor declared metadata is read again for reporting.

    Returns
    -------
    dict[str, object]
        JSON-compatible requested populations, original byte references, all
        available observations and located capture failures. Ticks are shared
        counter values, without physical frequency or calibrated latency.
        This component makes no numerical, encoder-tail, source qualification,
        whole-run, SPIKE-LOG or SIM-REAL acceptance statement.
    """
    configuration = capture.configuration
    return {
        "scope": "capture",
        "unit": "shared-counter ticks",
        "requested": {
            "step_count": configuration.step_count,
            "service_packets": configuration.service_packets,
            "capture_horizon_edges": configuration.capture_horizon_edges,
        },
        "counter_receipt": {
            "sha256": hashlib.sha256(capture.counter_receipt).hexdigest(),
            "byte_length": len(capture.counter_receipt),
        },
        "channels": [_channel_report(capture, index) for index in range(len(capture.channels))],
        "step_observations": [
            {
                "identity": interval.identity,
                "applied_tick": interval.applied_tick,
                "observed_tick": interval.observed_tick,
                "interval_ticks": interval.ticks,
            }
            for interval in capture.steps.intervals
        ],
        "step_refusals": list(capture.steps.refusals),
        "refusals": list(capture.refusals),
    }
