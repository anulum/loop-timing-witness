# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete actual capture loading and projection controls

"""Exercise whole capture loading through actual original RTL files and counters."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from loop_timing_witness.neural_capture import (
    NeuralCaptureConfiguration,
    NeuralChannelFiles,
    load_neural_capture,
)
from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError, decode_neural_channel

if TYPE_CHECKING:
    from test_neural_event_stream import CaptureStreams

CaptureBinding = tuple[
    Path,
    tuple[NeuralChannelFiles, NeuralChannelFiles, NeuralChannelFiles],
    dict[str, object],
    tuple[bytes, bytes, bytes],
]
CaptureBindings = Callable[[int, int, int, int, int], CaptureBinding]
pytest_plugins = ("test_neural_event_stream",)


@pytest.fixture
def capture_bindings(tmp_path: Path, capture_streams: CaptureStreams) -> CaptureBindings:
    """Derive bound references and original projections from the actual RTL export.

    Parameters
    ----------
    tmp_path
        Isolated producer and projection allocation.
    capture_streams
        Actual shared-counter Icarus/vvp producer.

    Returns
    -------
    CaptureBindings
        Producer returning directory, original references and original capture bytes.
    """

    def run(empty_service: int, overflow: int, phase: int, count: int, bits: int) -> CaptureBinding:
        streams = capture_streams(empty_service, overflow, phase, count, bits)
        directory = tmp_path / f"capture-{empty_service}-{overflow}-{phase}-{count}-{bits}"
        files = []
        for index, role in enumerate(("input", "state", "service")):
            payload = streams[index] if overflow else streams[index][16:-16]
            markers = b"" if overflow else streams[index][:16] + streams[index][-16:]
            (directory / f"payload-{index}.bin").write_bytes(payload)
            (directory / f"markers-{index}.bin").write_bytes(markers)
            references = [
                {"path": name, "sha256": hashlib.sha256(raw).hexdigest(), "byte_length": len(raw)}
                for name, raw in (
                    (f"channel-{index}.bin", streams[index]),
                    (f"payload-{index}.bin", payload),
                    (f"markers-{index}.bin", markers),
                )
            ]
            files.append(NeuralChannelFiles(role, references[0], references[1], references[2]))
        receipt = (directory / "capture-counts.json").read_bytes()
        counter_ref: dict[str, object] = {
            "path": "capture-counts.json",
            "sha256": hashlib.sha256(receipt).hexdigest(),
            "byte_length": len(receipt),
        }
        return directory, (files[0], files[1], files[2]), counter_ref, streams

    return run


@pytest.mark.parametrize(("empty_service", "count"), [(0, 4), (1, 4), (0, 1000), (1, 1000)])
def test_actual_complete_capture_loads_all_original_bytes_and_findings(
    capture_bindings: CaptureBindings,
    empty_service: int,
    count: int,
) -> None:
    """Load full actual files, exact projections, counters and registered-step timing.

    Parameters
    ----------
    capture_bindings
        Original instrument-port control files and exact reference derivations.
    empty_service
        Marker-only service channel, not a fabricated packet.
    count
        Complete four-step or 1,000-step requested population.
    """
    directory, files, counter_ref, streams = capture_bindings(empty_service, 0, 1, count, 32)
    plan = NeuralCaptureConfiguration(count, 0 if empty_service else count, count + 100)
    result = load_neural_capture(directory, files, counter_ref, plan)
    assert result.captures == streams
    assert result.counter_receipt == (directory / "capture-counts.json").read_bytes()
    assert result.refusals == ()
    assert [channel.role for channel in result.channels] == ["input", "state", "service"]
    assert [len(channel.events) for channel in result.channels] == [
        count,
        count,
        plan.service_packets,
    ]
    assert [item.identity for item in result.steps.intervals] == list(range(count))
    assert [item.ticks for item in result.steps.intervals] == [1] * count
    assert [item.refusals for item in result.accounting] == [(), (), ()]
    assert [item.attempts for item in result.counts] == [
        count + 2,
        count + 2,
        plan.service_packets + 2,
    ]


def test_actual_bound_projection_files_cannot_replace_original_observations(
    capture_bindings: CaptureBindings,
) -> None:
    """Refuse separately hashed but wrong payload/marker projections of an intact capture.

    Parameters
    ----------
    capture_bindings
        Unchanged actual raw streams and their original projections.
    """
    directory, files, counter_ref, streams = capture_bindings(0, 0, 1, 4, 32)
    channel = decode_neural_channel(streams[0], "input", 4)
    payload = bytearray(channel.payload_bytes)
    payload[8] ^= 1
    markers = bytearray(channel.marker_bytes)
    markers[8] ^= 1
    (directory / "damaged-payload.bin").write_bytes(payload)
    (directory / "damaged-markers.bin").write_bytes(markers)
    altered = replace(
        files[0],
        payload={
            "path": "damaged-payload.bin",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "byte_length": len(payload),
        },
        markers={
            "path": "damaged-markers.bin",
            "sha256": hashlib.sha256(markers).hexdigest(),
            "byte_length": len(markers),
        },
    )
    result = load_neural_capture(
        directory, (altered, files[1], files[2]), counter_ref, NeuralCaptureConfiguration(4, 4, 100)
    )
    assert result.captures == streams
    assert result.refusals == (
        "input: payload file differs from original capture projection",
        "input: marker file differs from original capture projection",
    )


def test_actual_missing_service_row_remains_a_located_gap(
    capture_bindings: CaptureBindings,
) -> None:
    """Keep service IDs after loss and reconcile the shorter export with original drain counts.

    Parameters
    ----------
    capture_bindings
        Actual shared counter exports and original hardware count snapshot.
    """
    directory, files, counter_ref, streams = capture_bindings(0, 0, 1, 4, 32)
    partial = streams[2][:32] + streams[2][48:]
    channel = decode_neural_channel(partial, "service", 4)
    (directory / "partial-service.bin").write_bytes(partial)
    (directory / "partial-service-payload.bin").write_bytes(channel.payload_bytes)
    altered = replace(
        files[2],
        capture={
            "path": "partial-service.bin",
            "sha256": hashlib.sha256(partial).hexdigest(),
            "byte_length": len(partial),
        },
        payload={
            "path": "partial-service-payload.bin",
            "sha256": hashlib.sha256(channel.payload_bytes).hexdigest(),
            "byte_length": len(channel.payload_bytes),
        },
    )
    result = load_neural_capture(
        directory, (files[0], files[1], altered), counter_ref, NeuralCaptureConfiguration(4, 4, 100)
    )
    assert [event.identity for event in result.channels[2].events] == [0, 2, 3]
    assert result.counts[2].drained == 6
    assert result.accounting[2].observed_records == 5
    assert result.refusals == (
        "service: exported records differ from drain count",
        "service: packet population differs from requested identities",
    )


def test_actual_saturated_loss_preserves_partial_capture_findings(
    capture_bindings: CaptureBindings,
) -> None:
    """Load actual isolated FIFO loss without repairing markers, populations or intervals.

    Parameters
    ----------
    capture_bindings
        Real stopped-drain overflow control with a saturating three-bit counter.
    """
    directory, files, counter_ref, streams = capture_bindings(0, 1, 0, 4, 3)
    result = load_neural_capture(
        directory, files, counter_ref, NeuralCaptureConfiguration(25, 0, 100)
    )
    assert result.captures == streams
    assert [len(channel.events) for channel in result.channels] == [8, 25, 0]
    assert result.accounting[0].dropped_lower_bound == 7
    assert result.accounting[0].drop_count_exact is False
    assert "input: capture lost records" in result.refusals
    assert "input: attempts differ from requested data and alignment markers" in result.refusals
    assert "service: missing alignment marker" in result.refusals
    assert [item.identity for item in result.steps.intervals] == list(range(8))
    assert [item.ticks for item in result.steps.intervals] == [0] * 8


def test_actual_capture_loading_refuses_configuration_role_and_receipt_damage(
    capture_bindings: CaptureBindings,
) -> None:
    """Reject unsupported declarations before I/O and refuse a bound foreign counter schema.

    Parameters
    ----------
    capture_bindings
        Actual source for all unchanged baseline references.
    """
    directory, files, counter_ref, _ = capture_bindings(0, 0, 1, 4, 32)
    for plan in [
        NeuralCaptureConfiguration(0, 0, 100),
        NeuralCaptureConfiguration(1001, 0, 100),
        NeuralCaptureConfiguration(step_count=True, service_packets=0, capture_horizon_edges=100),
        NeuralCaptureConfiguration(4, -1, 100),
        NeuralCaptureConfiguration(4, 5, 100),
        NeuralCaptureConfiguration(step_count=4, service_packets=True, capture_horizon_edges=100),
        NeuralCaptureConfiguration(4, 4, 0),
        NeuralCaptureConfiguration(4, 4, 65536),
        NeuralCaptureConfiguration(step_count=4, service_packets=4, capture_horizon_edges=True),
    ]:
        with pytest.raises(NeuralCaptureRefusalError, match="configuration"):
            load_neural_capture(directory / "missing-run", files, counter_ref, plan)
    with pytest.raises(NeuralCaptureRefusalError, match="input, state, service order"):
        load_neural_capture(
            directory,
            (files[1], files[0], files[2]),
            counter_ref,
            NeuralCaptureConfiguration(4, 4, 100),
        )
    value = json.loads((directory / "capture-counts.json").read_bytes())
    value["schema_id"] = "foreign"
    receipt = json.dumps(value).encode()
    (directory / "foreign-counts.json").write_bytes(receipt)
    foreign_ref = {
        "path": "foreign-counts.json",
        "sha256": hashlib.sha256(receipt).hexdigest(),
        "byte_length": len(receipt),
    }
    with pytest.raises(NeuralCaptureRefusalError, match="receipt schema"):
        load_neural_capture(directory, files, foreign_ref, NeuralCaptureConfiguration(4, 4, 100))
