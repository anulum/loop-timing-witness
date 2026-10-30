# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual capture observations in JSON report components

"""Report original RTL observations and raw references through the actual JSON boundary."""

from __future__ import annotations

import hashlib
import struct
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from loop_timing_witness.manifest_io import canonical_json_bytes, parse_json_object
from loop_timing_witness.neural_capture import NeuralCaptureConfiguration, load_neural_capture
from loop_timing_witness.neural_capture_report import neural_capture_report

if TYPE_CHECKING:
    from test_neural_capture import CaptureBindings

pytest_plugins = ("test_neural_capture",)


@pytest.mark.parametrize("empty_service", [0, 1])
def test_actual_capture_report_retains_complete_references_and_record_positions(
    capture_bindings: CaptureBindings,
    empty_service: int,
) -> None:
    """Serialize complete 1,000-step findings and locate every original raw data record.

    Parameters
    ----------
    capture_bindings
        Actual instrument-port producer and independent raw-byte projections.
    empty_service
        Full service-port population or marker-only service without packet invention.
    """
    directory, files, counter_ref, streams = capture_bindings(empty_service, 0, 1, 1000, 32)
    configuration = NeuralCaptureConfiguration(1000, 0 if empty_service else 1000, 4096)
    capture = load_neural_capture(directory, files, counter_ref, configuration)
    report = parse_json_object(
        canonical_json_bytes(neural_capture_report(capture)), "capture report"
    )
    assert report["scope"] == "capture"
    assert report["unit"] == "shared-counter ticks"
    assert report["requested"] == {
        "step_count": 1000,
        "service_packets": configuration.service_packets,
        "capture_horizon_edges": 4096,
    }
    assert report["refusals"] == []
    assert report["step_refusals"] == []
    assert len(report["step_observations"]) == 1000
    assert report["step_observations"][0] == {
        "identity": 0,
        "applied_tick": 20,
        "observed_tick": 21,
        "interval_ticks": 1,
    }
    assert report["step_observations"][-1] == {
        "identity": 999,
        "applied_tick": 1019,
        "observed_tick": 1020,
        "interval_ticks": 1,
    }
    receipt = (directory / "capture-counts.json").read_bytes()
    assert report["counter_receipt"] == {
        "sha256": hashlib.sha256(receipt).hexdigest(),
        "byte_length": len(receipt),
    }
    for index, channel in enumerate(report["channels"]):
        assert channel["sources"]["capture"] == {
            "sha256": hashlib.sha256(streams[index]).hexdigest(),
            "byte_length": len(streams[index]),
        }
        assert channel["start_marker_tick"] == 10
        assert channel["end_marker_tick"] == 1030
        assert channel["drop_counter"] == {"bits": 32, "value": 0, "lower_bound": 0, "exact": True}
        for event in channel["events"]:
            original = struct.unpack_from("<BBHIQ", streams[index], event["record_byte_offset"])
            assert original == (14 + index, 0, 0, event["identity"], event["ticks"])
    service = report["channels"][2]
    assert service["observed_data_records"] == configuration.service_packets
    assert service["observed_total_records"] == configuration.service_packets + 2
    if empty_service:
        assert service["events"] == []
        assert service["sources"]["payload"] == {
            "sha256": hashlib.sha256(b"").hexdigest(),
            "byte_length": 0,
        }


def test_actual_report_locates_service_identity_gaps_without_relabelling(
    capture_bindings: CaptureBindings,
) -> None:
    """Report original missing-service IDs and the corresponding actual raw byte positions.

    Parameters
    ----------
    capture_bindings
        Actual intact captures and original drain snapshot before controlled damage.
    """
    directory, files, counter_ref, streams = capture_bindings(0, 0, 1, 4, 32)
    partial = streams[2][:32] + streams[2][48:]
    payload = partial[16:-16]
    (directory / "partial-service.bin").write_bytes(partial)
    (directory / "partial-service-payload.bin").write_bytes(payload)
    changed = replace(
        files[2],
        capture={
            "path": "partial-service.bin",
            "sha256": hashlib.sha256(partial).hexdigest(),
            "byte_length": len(partial),
        },
        payload={
            "path": "partial-service-payload.bin",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "byte_length": len(payload),
        },
    )
    capture = load_neural_capture(
        directory, (files[0], files[1], changed), counter_ref, NeuralCaptureConfiguration(4, 4, 100)
    )
    report = parse_json_object(
        canonical_json_bytes(neural_capture_report(capture)), "partial capture"
    )
    service = report["channels"][2]
    assert [event["identity"] for event in service["events"]] == [0, 2, 3]
    assert [event["record_byte_offset"] for event in service["events"]] == [16, 32, 48]
    assert service["drained"] == 6
    assert service["observed_total_records"] == 5
    for event in service["events"]:
        original = struct.unpack_from("<BBHIQ", partial, event["record_byte_offset"])
        assert original == (16, 0, 0, event["identity"], event["ticks"])
    assert report["refusals"] == [
        "service: exported records differ from drain count",
        "service: packet population differs from requested identities",
    ]


def test_actual_loss_report_preserves_requested_population_and_saturation_bound(
    capture_bindings: CaptureBindings,
) -> None:
    """Keep 25 requested steps, eight available pairs and null markers after actual FIFO loss.

    Parameters
    ----------
    capture_bindings
        Actual isolated full FIFO and saturating counter source.
    """
    directory, files, counter_ref, streams = capture_bindings(0, 1, 0, 4, 3)
    capture = load_neural_capture(
        directory, files, counter_ref, NeuralCaptureConfiguration(25, 0, 100)
    )
    report = parse_json_object(canonical_json_bytes(neural_capture_report(capture)), "loss capture")
    assert report["requested"]["step_count"] == 25
    assert len(report["step_observations"]) == 8
    assert [item["interval_ticks"] for item in report["step_observations"]] == [0] * 8
    assert "input: capture lost records" in report["refusals"]
    assert "service: missing alignment marker" in report["step_refusals"]
    first = report["channels"][0]
    assert first["start_marker_tick"] is None
    assert first["end_marker_tick"] is None
    assert first["drop_counter"] == {"bits": 3, "value": 7, "lower_bound": 7, "exact": False}
    assert first["attempts"] == 25
    assert first["accepted"] == 8
    assert first["observed_data_records"] == 8
    assert first["events"][0]["record_byte_offset"] == 0
    assert first["sources"]["capture"]["sha256"] == hashlib.sha256(streams[0]).hexdigest()


def test_actual_report_keeps_declared_and_derived_projection_hashes_distinct(
    capture_bindings: CaptureBindings,
) -> None:
    """Identify the actual wrong payload file as well as its correct original derivation.

    Parameters
    ----------
    capture_bindings
        Actual capture sources and their independently extracted original projections.
    """
    directory, files, counter_ref, streams = capture_bindings(0, 0, 1, 4, 32)
    original = streams[0][16:-16]
    wrong = bytearray(original)
    wrong[8] ^= 1
    (directory / "wrong-payload.bin").write_bytes(wrong)
    changed = replace(
        files[0],
        payload={
            "path": "wrong-payload.bin",
            "sha256": hashlib.sha256(wrong).hexdigest(),
            "byte_length": len(wrong),
        },
    )
    capture = load_neural_capture(
        directory, (changed, files[1], files[2]), counter_ref, NeuralCaptureConfiguration(4, 4, 100)
    )
    report = parse_json_object(
        canonical_json_bytes(neural_capture_report(capture)), "wrong projection"
    )
    first = report["channels"][0]
    assert first["sources"]["payload"]["sha256"] == hashlib.sha256(wrong).hexdigest()
    assert first["derived_projections"]["payload"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert capture.payloads[0] == bytes(wrong)
    assert capture.channels[0].payload_bytes == original
    assert report["refusals"] == ["input: payload file differs from original capture projection"]
