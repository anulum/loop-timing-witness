# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual capture counter and export accounting controls

"""Reconcile actual RTL counter receipts and refuse damaged counts or exports."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from loop_timing_witness.neural_capture_counts import (
    decode_neural_capture_counts,
    reconcile_neural_capture,
)
from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError, decode_neural_channel

if TYPE_CHECKING:
    from pathlib import Path

    from test_neural_event_stream import CaptureStreams

pytest_plugins = ("test_neural_event_stream",)


@pytest.mark.parametrize(("empty_service", "count", "bits"), [(0, 4, 3), (1, 1000, 32)])
def test_actual_lossless_capture_counters_match_original_exports(
    capture_streams: CaptureStreams, tmp_path: Path, empty_service: int, count: int, bits: int
) -> None:
    """Reconcile real phase-mode exports, including 1,000 steps and marker-only service.

    Parameters
    ----------
    capture_streams
        Actual shared-counter RTL producer.
    tmp_path
        Its isolated raw-export and receipt directory.
    empty_service
        Select zero service data, without omitting dedicated markers.
    count
        Complete requested data population.
    bits
        Compiled overflow-counter width.
    """
    streams = capture_streams(empty_service, 0, 1, count, bits)
    receipt = tmp_path / f"capture-{empty_service}-0-1-{count}-{bits}/capture-counts.json"
    counts = decode_neural_capture_counts(receipt.read_bytes())
    for index, snapshot in enumerate(counts):
        population = 0 if empty_service and index == 2 else count
        channel = decode_neural_channel(streams[index], snapshot.role, population)
        report = reconcile_neural_capture(channel, snapshot)
        assert snapshot.drop_counter_bits == bits
        assert snapshot.attempts == population + 2
        assert snapshot.accepted == population + 2
        assert snapshot.drained == population + 2
        assert snapshot.dropped == 0
        assert snapshot.overflowed is False
        assert report.observed_records == population + 2
        assert report.dropped_lower_bound == 0
        assert report.drop_count_exact is True
        assert report.refusals == ()


@pytest.mark.parametrize("bits", [3, 32])
def test_actual_fifo_loss_retains_exact_or_saturated_drop_counts(
    capture_streams: CaptureStreams, tmp_path: Path, bits: int
) -> None:
    """Distinguish actual 17-drop loss from a real three-bit saturated lower bound.

    Parameters
    ----------
    capture_streams
        Real stopped-drain and independent-FIFO overflow producer.
    tmp_path
        Original hardware counter receipt allocation.
    bits
        Three-bit saturating control or actual default 32-bit unsaturated control.
    """
    first, second, third = capture_streams(0, 1, 0, 4, bits)
    counts = decode_neural_capture_counts(
        (tmp_path / f"capture-0-1-0-4-{bits}/capture-counts.json").read_bytes()
    )
    lost = reconcile_neural_capture(decode_neural_channel(first, "input", 25), counts[0])
    assert lost.observed_records == 8
    assert lost.dropped_lower_bound == (7 if bits == 3 else 17)
    assert lost.drop_count_exact is (bits == 32)
    assert lost.refusals == (
        ("input: capture lost records", "input: drop counter is a lower bound at saturation")
        if bits == 3
        else ("input: capture lost records",)
    )
    other = reconcile_neural_capture(decode_neural_channel(second, "state", 25), counts[1])
    assert other.observed_records == 25
    assert other.refusals == ()
    empty = reconcile_neural_capture(decode_neural_channel(third, "service", 0), counts[2])
    assert empty.observed_records == 0
    assert empty.refusals == ()


def test_actual_counts_refuse_damaged_export_and_incoherent_snapshots(
    capture_streams: CaptureStreams,
    tmp_path: Path,
) -> None:
    """Keep original rows and counts distinct when metadata or drained bytes disagree.

    Parameters
    ----------
    capture_streams
        Actual capture producer for the unchanged positive baseline.
    tmp_path
        Original receipt path, read unchanged before controlled damage.
    """
    first, _, _ = capture_streams(0, 0, 1, 4, 3)
    receipt = (tmp_path / "capture-0-0-1-4-3/capture-counts.json").read_bytes()
    snapshots = decode_neural_capture_counts(receipt)
    channel = decode_neural_channel(first, "input", 4)
    report = reconcile_neural_capture(channel, snapshots[1])
    assert report.refusals == ("input: counter snapshot belongs to another channel",)
    missing = decode_neural_channel(first[:32] + first[48:], "input", 4)
    report = reconcile_neural_capture(missing, snapshots[0])
    assert report.observed_records == 5
    assert report.refusals == ("input: exported records differ from drain count",)
    cases = [
        ({"attempts": 7}, ("attempted, accepted and dropped counts disagree",)),
        (
            {"accepted": 7},
            (
                "attempted, accepted and dropped counts disagree",
                "accepted records were not completely drained",
            ),
        ),
        (
            {"drained": 5},
            (
                "accepted records were not completely drained",
                "exported records differ from drain count",
            ),
        ),
        (
            {"attempts": 7, "dropped": 1},
            (
                "overflow flag and drop counter disagree",
                "capture lost records",
            ),
        ),
        (
            {"overflowed": True},
            (
                "overflow flag and drop counter disagree",
                "capture lost records",
            ),
        ),
        (
            {"attempts": 7, "dropped": 7, "overflowed": True},
            (
                "attempted, accepted and dropped counts disagree",
                "capture lost records",
                "drop counter is a lower bound at saturation",
            ),
        ),
    ]
    for changes, expected in cases:
        value = json.loads(receipt)
        value["channels"][0].update(changes)
        altered = decode_neural_capture_counts(json.dumps(value).encode())[0]
        report = reconcile_neural_capture(channel, altered)
        assert report.refusals == tuple(f"input: {message}" for message in expected)


def test_actual_counter_receipt_schema_and_types_refuse_damage(
    capture_streams: CaptureStreams,
    tmp_path: Path,
) -> None:
    """Reject malformed JSON, duplicate keys, bad role order and non-finite declarations.

    Parameters
    ----------
    capture_streams
        Actual counter producer, not a hand-authored positive metadata fixture.
    tmp_path
        Original actual receipt bytes.
    """
    capture_streams(0, 0, 1, 4, 3)
    receipt = (tmp_path / "capture-0-0-1-4-3/capture-counts.json").read_bytes()
    damaged = [
        b"{",
        b"\xff",
        b"[]",
        receipt.replace(b'"attempts":', b'"attempts":0,"attempts":', 1),
    ]
    for changes in [
        {"schema_id": "other"},
        {"extra": 0},
        {"drop_counter_bits": 0},
        {"drop_counter_bits": 33},
        {"drop_counter_bits": True},
        {"channels": {}},
        {"channels": []},
    ]:
        value = json.loads(receipt)
        value.update(changes)
        damaged.append(json.dumps(value).encode())
    for changes in [
        {"role": "service"},
        {"extra": 0},
        {"overflowed": 0},
        {"attempts": True},
        {"attempts": -1},
        {"accepted": 1 << 64},
        {"dropped": 8},
        {"drained": 1.0},
    ]:
        value = json.loads(receipt)
        value["channels"][0].update(changes)
        damaged.append(json.dumps(value).encode())
    value = json.loads(receipt)
    value["channels"][0] = None
    damaged.append(json.dumps(value).encode())
    for content in damaged:
        with pytest.raises(NeuralCaptureRefusalError):
            decode_neural_capture_counts(content)
    with pytest.raises(NeuralCaptureRefusalError, match="must be bytes"):
        decode_neural_capture_counts(json.loads('"not bytes"'))
