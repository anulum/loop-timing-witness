# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — real shared-capture stream decoding and refusal controls

"""Decode actual RTL exports and refuse damaged channel records through the public API."""

from __future__ import annotations

import json
import struct
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError, decode_neural_channel

CaptureStreams = Callable[[int, int, int, int, int], tuple[bytes, bytes, bytes]]


@pytest.fixture
def capture_streams(tmp_path: Path) -> CaptureStreams:
    """Compile the actual shared-counter RTL and export its three channel files.

    Parameters
    ----------
    tmp_path
        Isolated compiler and raw-export allocation.

    Returns
    -------
    CaptureStreams
        Runner selecting a genuine empty service channel or isolated FIFO loss.
    """
    repository = Path(__file__).resolve().parents[1]

    def run(
        empty_service: int, overflow: int, phase: int, count: int, counter_bits: int
    ) -> tuple[bytes, bytes, bytes]:
        directory = tmp_path / f"capture-{empty_service}-{overflow}-{phase}-{count}-{counter_bits}"
        directory.mkdir()
        binary = directory / "shared-capture.vvp"
        subprocess.run(
            [
                "iverilog",
                "-g2012",
                "-s",
                "shared_event_witness_tb",
                "-o",
                str(binary),
                "-Pshared_event_witness_tb.NEURAL_FORMAT=1",
                f"-Pshared_event_witness_tb.NEURAL_PHASE={phase}",
                f"-Pshared_event_witness_tb.NORMAL_COUNT={count}",
                f"-Pshared_event_witness_tb.ADDRESS_BITS={10 if count == 1000 else 3}",
                f"-Pshared_event_witness_tb.EMPTY_SERVICE={int(empty_service)}",
                f"-Pshared_event_witness_tb.OVERFLOW_RUN={int(overflow)}",
                f"-Pshared_event_witness_tb.OVERFLOW_COUNTER_BITS={counter_bits}",
                "-Pshared_event_witness_tb.DRAIN_HALF_PERIOD=3",
                str(repository / "rtl/clock_reset_release.sv"),
                str(repository / "rtl/event_record_fifo.sv"),
                str(repository / "rtl/shared_event_witness.sv"),
                str(repository / "tests/rtl/shared_event_witness_tb.sv"),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        result = subprocess.run(
            ["vvp", str(binary), f"+EVENT_DIRECTORY={directory}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "SHARED_CAPTURE_PASS reset_pass=1" in result.stdout
        return (
            (directory / "channel-0.bin").read_bytes(),
            (directory / "channel-1.bin").read_bytes(),
            (directory / "channel-2.bin").read_bytes(),
        )

    return run


@pytest.mark.parametrize("empty_service", [0, 1])
def test_complete_rtl_channel_projections_keep_original_bytes(
    capture_streams: CaptureStreams, empty_service: int
) -> None:
    """Retain actual role-specific records, markers and a finalized empty payload.

    Parameters
    ----------
    capture_streams
        Actual Icarus/vvp capture producer.
    empty_service
        Select a marker-only service channel with no fabricated packet.
    """
    raw = capture_streams(empty_service, 0, 0, 4, 3)
    for index, role in enumerate(("input", "state", "service")):
        limit = 0 if empty_service and role == "service" else 4
        channel = decode_neural_channel(raw[index], role, limit)
        assert channel.role == role
        assert channel.start_tick == 10
        assert channel.end_tick == 40
        assert [event.identity for event in channel.events] == list(range(limit))
        assert [event.ticks for event in channel.events] == [20 + 3 * step for step in range(limit)]
        assert channel.payload_bytes == raw[index][16:-16]
        assert channel.marker_bytes == raw[index][:16] + raw[index][-16:]
        assert len(channel.payload_bytes) == 16 * limit


def test_actual_overflow_and_removed_rows_remain_partial(capture_streams: CaptureStreams) -> None:
    """Preserve missing markers and identity gaps without shifting the remaining rows.

    Parameters
    ----------
    capture_streams
        Actual independent-FIFO overflow producer.
    """
    raw_input, raw_state, raw_service = capture_streams(0, 1, 0, 4, 3)
    first = decode_neural_channel(raw_input, "input", 25)
    second = decode_neural_channel(raw_state, "state", 25)
    empty = decode_neural_channel(raw_service, "service", 0)
    assert len(first.events) == 8
    assert len(second.events) == 25
    assert first.start_tick is None
    assert first.end_tick is None
    assert second.start_tick is None
    assert second.end_tick is None
    assert first.payload_bytes == raw_input
    assert first.marker_bytes == b""
    assert empty.events == ()
    assert empty.payload_bytes == b""
    assert empty.start_tick is None
    assert empty.end_tick is None
    gap = decode_neural_channel(raw_state[:16] + raw_state[32:], "state", 25)
    assert [event.identity for event in gap.events] == [0, *range(2, 25)]
    assert gap.payload_bytes == raw_state[:16] + raw_state[32:]


def test_damaged_rtl_records_and_channel_declarations_are_refused(
    capture_streams: CaptureStreams,
) -> None:
    """Reject malformed frames, cross-channel codes, misplaced markers and tick drift.

    Parameters
    ----------
    capture_streams
        Actual marker/data stream used as the unchanged negative-control baseline.
    """
    raw, _, _ = capture_streams(0, 0, 0, 4, 3)
    variants: list[bytes] = [raw[:-1], raw[16:32] + raw]
    for offset, replacement in [
        (1, b"\x01"),
        (2, b"\x01\x00"),
        (16, b"\x03"),
        (16, b"\x0f"),
        (4, struct.pack("<I", 2)),
        (20, struct.pack("<I", 4)),
        (36, struct.pack("<I", 0)),
        (40, struct.pack("<Q", 20)),
        (40, struct.pack("<Q", 19)),
        (40, struct.pack("<Q", 65536)),
    ]:
        damaged = bytearray(raw)
        damaged[offset : offset + len(replacement)] = replacement
        variants.append(bytes(damaged))
    variants.extend([raw[:32] + raw[:16] + raw[32:], raw[:48] + raw[-16:] + raw[48:]])
    for content in variants:
        with pytest.raises(NeuralCaptureRefusalError):
            decode_neural_channel(content, "input", 4)
    for limit in [-1, 0, 1001, True]:
        with pytest.raises(NeuralCaptureRefusalError, match="Invalid neural capture population"):
            decode_neural_channel(raw, "input", limit)
    with pytest.raises(NeuralCaptureRefusalError, match="Unknown neural capture channel role"):
        decode_neural_channel(raw, "control", 4)
    with pytest.raises(NeuralCaptureRefusalError, match="Unknown neural capture channel role"):
        decode_neural_channel(raw, json.loads("[]"), 4)
    with pytest.raises(NeuralCaptureRefusalError, match="whole sequence"):
        decode_neural_channel(json.loads('"not bytes"'), "input", 4)
