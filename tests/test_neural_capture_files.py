# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — whole actual capture file and original-projection binding

"""Bind actual RTL exports before decoding and refuse wrong bytes or escaped sources."""

from __future__ import annotations

import hashlib
import json
import sys
from typing import TYPE_CHECKING

import pytest

from loop_timing_witness.neural_capture_counts import (
    decode_neural_capture_counts,
    reconcile_neural_capture,
)
from loop_timing_witness.neural_capture_files import read_neural_bound_file
from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError, decode_neural_channel

if TYPE_CHECKING:
    from pathlib import Path

    from test_neural_event_stream import CaptureStreams

pytest_plugins = ("test_neural_event_stream",)


def test_actual_whole_files_and_zero_payload_are_bound_before_decoding(
    capture_streams: CaptureStreams,
    tmp_path: Path,
) -> None:
    """Read actual capture/count files and their exact present zero-byte projection.

    Parameters
    ----------
    capture_streams
        Actual shared-counter instrument exporter.
    tmp_path
        Its source directory and controlled projection allocation.
    """
    first, second, third = capture_streams(1, 0, 1, 1000, 32)
    directory = tmp_path / "capture-1-0-1-1000-32"
    receipt = (directory / "capture-counts.json").read_bytes()
    receipt_ref = {
        "path": "capture-counts.json",
        "sha256": hashlib.sha256(receipt).hexdigest(),
        "byte_length": len(receipt),
    }
    snapshots = decode_neural_capture_counts(read_neural_bound_file(directory, receipt_ref, 16384))
    for index, original in enumerate((first, second, third)):
        ref = {
            "path": f"channel-{index}.bin",
            "sha256": hashlib.sha256(original).hexdigest(),
            "byte_length": len(original),
        }
        bound = read_neural_bound_file(directory, ref, 16384)
        assert bound == original
        snapshot = snapshots[index]
        channel = decode_neural_channel(bound, snapshot.role, 0 if index == 2 else 1000)
        report = reconcile_neural_capture(channel, snapshot)
        assert report.refusals == ()
        (directory / f"payload-{index}.bin").write_bytes(channel.payload_bytes)
        payload_ref = {
            "path": f"payload-{index}.bin",
            "sha256": hashlib.sha256(channel.payload_bytes).hexdigest(),
            "byte_length": len(channel.payload_bytes),
        }
        payload = read_neural_bound_file(directory, payload_ref, 0 if index == 2 else 16000)
        assert payload == channel.payload_bytes
    assert (directory / "payload-2.bin").read_bytes() == b""


def test_actual_capture_reference_and_full_digest_refuse_damage(
    capture_streams: CaptureStreams,
    tmp_path: Path,
) -> None:
    """Refuse wrong lengths, digests, types and unadmitted allocations of real files.

    Parameters
    ----------
    capture_streams
        Actual capture bytes forming the original baseline.
    tmp_path
        Its existing file reference directory.
    """
    first, _, _ = capture_streams(0, 0, 1, 4, 3)
    directory = tmp_path / "capture-0-0-1-4-3"
    baseline = {
        "path": "channel-0.bin",
        "sha256": hashlib.sha256(first).hexdigest(),
        "byte_length": len(first),
    }
    variants: list[dict[str, object]] = [
        {"extra": 0},
        {"path": ""},
        {"path": "\x00"},
        {"path": []},
        {"sha256": None},
        {"sha256": "short"},
        {"byte_length": True},
        {"byte_length": -1},
        {"byte_length": len(first) + 1},
        {"byte_length": len(first) - 1},
        {"sha256": "0" * 64},
    ]
    for changes in variants:
        with pytest.raises(NeuralCaptureRefusalError):
            read_neural_bound_file(directory, baseline | changes, 16384)
    with pytest.raises(NeuralCaptureRefusalError, match="allocation"):
        read_neural_bound_file(directory, baseline, len(first) - 1)
    for unrepresentable in (sys.maxsize, (1 << 64) - 1):
        with pytest.raises(NeuralCaptureRefusalError, match="allocation"):
            read_neural_bound_file(
                directory, baseline | {"byte_length": unrepresentable}, unrepresentable
            )
    for limit in [-1, True]:
        with pytest.raises(NeuralCaptureRefusalError, match="allocation"):
            read_neural_bound_file(directory, baseline, limit)
    with pytest.raises(NeuralCaptureRefusalError, match="reference fields"):
        read_neural_bound_file(directory, json.loads("[]"), 16384)
    changed = bytearray(first)
    changed[8] ^= 1
    (directory / "damaged-capture.bin").write_bytes(changed)
    with pytest.raises(NeuralCaptureRefusalError, match="SHA-256 mismatch"):
        read_neural_bound_file(directory, baseline | {"path": "damaged-capture.bin"}, 16384)


def test_actual_file_placement_and_missing_exports_are_refused(
    capture_streams: CaptureStreams,
    tmp_path: Path,
) -> None:
    """Reject escape paths, external symlinks, directories and absent payload files.

    Parameters
    ----------
    capture_streams
        Real existing file source for path-reference controls.
    tmp_path
        Controlled run and adjacent outside-run file allocation on Samsung.
    """
    first, _, _ = capture_streams(0, 0, 1, 4, 3)
    directory = tmp_path / "capture-0-0-1-4-3"
    baseline = {
        "path": "channel-0.bin",
        "sha256": hashlib.sha256(first).hexdigest(),
        "byte_length": len(first),
    }
    for name in [str(directory / "channel-0.bin"), "../outside.bin"]:
        with pytest.raises(NeuralCaptureRefusalError, match="must stay within"):
            read_neural_bound_file(directory, baseline | {"path": name}, 16384)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(first)
    (directory / "external-link.bin").symlink_to(outside)
    (directory / "internal-link.bin").symlink_to(directory / "channel-0.bin")
    with pytest.raises(NeuralCaptureRefusalError, match="not a regular file within"):
        read_neural_bound_file(directory, baseline | {"path": "external-link.bin"}, 16384)
    assert (
        read_neural_bound_file(directory, baseline | {"path": "internal-link.bin"}, 16384) == first
    )
    (directory / "folder").mkdir()
    with pytest.raises(NeuralCaptureRefusalError, match="not a regular file within"):
        read_neural_bound_file(directory, baseline | {"path": "folder"}, 16384)
    empty_ref = {
        "path": "missing-payload.bin",
        "sha256": hashlib.sha256(b"").hexdigest(),
        "byte_length": 0,
    }
    with pytest.raises(NeuralCaptureRefusalError, match="Cannot read"):
        read_neural_bound_file(directory, empty_ref, 0)
    with pytest.raises(NeuralCaptureRefusalError, match="Cannot read"):
        read_neural_bound_file(tmp_path / "missing-run", baseline, 16384)
