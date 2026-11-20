# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — binary event stream tests

"""Refuse corrupt fabric records through the published host command."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from conftest import REPOSITORY_ROOT
from loop_timing_witness.event_stream import Event, ReferenceEdge, decode_events, decode_stream
from loop_timing_witness.manifest_io import load_json_object

MakeRtlRun = Callable[[], tuple[Path, dict[str, Any]]]
RunTool = Callable[..., subprocess.CompletedProcess[str]]


def _corrupt(raw: bytearray, variant: str) -> None:
    """Apply one corruption to a real CONTROL event stream.

    Parameters
    ----------
    raw
        Event stream, changed in place.
    variant
        Corruption: an empty or partial stream, a set reserved bit or word, an
        unknown or foreign event code, a cycle outside the run, regressing ticks
        or cycle, or a repeated event.
    """
    if variant == "empty":
        raw.clear()
    elif variant == "partial":
        raw.pop()
    elif variant == "reserved":
        raw[1] = 1
    elif variant == "reserved_word":
        raw[2:4] = (1).to_bytes(2, "little")
    elif variant == "unknown_code":
        raw[0] = 255
    elif variant == "foreign_profile":
        raw[0] = 8
    elif variant == "cycle_outside":
        raw[4:8] = (3).to_bytes(4, "little")
    elif variant == "ticks_regress":
        raw[16 + 8 : 16 + 16] = (5).to_bytes(8, "little")
    elif variant == "cycle_regress":
        raw[5 * 16 + 4 : 5 * 16 + 8] = (0).to_bytes(4, "little")
    else:
        assert variant == "duplicate_event"
        raw[16] = 1


@pytest.mark.parametrize(
    ("variant", "finding"),
    [
        ("empty", "event file is empty"),
        ("partial", "whole number of 16-byte records"),
        ("reserved", "reserved bits must be zero"),
        ("reserved_word", "reserved bits must be zero"),
        ("unknown_code", "not in CONTROL"),
        ("foreign_profile", "not in CONTROL"),
        ("cycle_outside", "cycle is outside the run"),
        ("ticks_regress", "order is not monotonic"),
        ("cycle_regress", "order is not monotonic"),
        ("duplicate_event", "duplicate SAMPLE_READY"),
    ],
)
def test_corrupt_rtl_event_record_is_refused(
    variant: str,
    finding: str,
    make_rtl_run: MakeRtlRun,
    run_tool: RunTool,
    tmp_path: Path,
) -> None:
    """A valid file digest cannot make an invalid binary stream acceptable.

    Parameters
    ----------
    variant
        One real-file corruption to apply to the simulated stream.
    finding
        Expected public error text.
    make_rtl_run
        Icarus Verilog producer.
    run_tool
        Host command runner.
    tmp_path
        New report path.
    """
    run, manifest = make_rtl_run()
    raw = bytearray((run / "events.bin").read_bytes())
    _corrupt(raw, variant)
    (run / "events.bin").write_bytes(raw)
    manifest["files"]["events"]["sha256"] = hashlib.sha256(raw).hexdigest()
    (run / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    output = tmp_path / "report"
    result = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert result.returncode == 1
    assert finding in result.stderr
    assert not output.exists()


def _records(*fields: tuple[int, int, int, int, int]) -> bytes:
    """Pack event records.

    Parameters
    ----------
    *fields
        Code, reserved byte, reserved word, cycle or sequence number and ticks of each record.

    Returns
    -------
    bytes
        The little-endian records in order.
    """
    return b"".join(struct.pack("<BBHIQ", *record) for record in fields)


def _contracts() -> dict[str, Any]:
    """Return the packaged measurement domain's design contracts.

    Returns
    -------
    dict[str, Any]
        Contracts with the CONTROL profile's PPS reference event.
    """
    domain = load_json_object(
        REPOSITORY_ROOT / "src/loop_timing_witness/data/measurement-domain.json"
    )
    return dict(domain["design_contracts"])


def test_reference_records_decode_apart_from_the_cycle_order() -> None:
    """A PPS record may follow a later cycle record; it leaves the cycle events unchanged."""
    content = _records(
        (1, 0, 0, 0, 10), (18, 0, 0, 0, 5), (2, 0, 0, 0, 20), (18, 0, 0, 2, 30), (1, 0, 0, 1, 21)
    )
    events, edges = decode_stream(content, _contracts(), "CONTROL", 3)
    assert events == (
        Event("SAMPLE_READY", 0, 10),
        Event("SAMPLE_READ", 0, 20),
        Event("SAMPLE_READY", 1, 21),
    )
    assert edges == (ReferenceEdge("PPS", 0, 5), ReferenceEdge("PPS", 2, 30))
    assert decode_events(content, _contracts(), "CONTROL", 3) == events


@pytest.mark.parametrize(
    ("records", "refusal"),
    [
        ([(18, 0, 1, 0, 1)], "event record 0: reserved bits must be zero"),
        ([(18, 1, 0, 0, 1)], "event record 0: reserved bits must be zero"),
        ([(18, 0, 0, 4, 100), (18, 0, 0, 4, 200)], "event record 1: PPS order is not monotonic"),
        ([(18, 0, 0, 4, 100), (18, 0, 0, 5, 100)], "event record 1: PPS order is not monotonic"),
    ],
)
def test_malformed_reference_records_are_refused(
    records: list[tuple[int, int, int, int, int]], refusal: str
) -> None:
    """A PPS record needs zero reserved bits and a later sequence number and counter value.

    Parameters
    ----------
    records
        Records of one CONTROL run.
    refusal
        Expected refusal text.
    """
    with pytest.raises(ValueError, match=refusal):
        decode_stream(_records(*records), _contracts(), "CONTROL", 3)


def test_a_profile_without_reference_events_refuses_the_pps_code() -> None:
    """The COMPUTE profile declares no reference event, so code 18 is foreign to it."""
    with pytest.raises(ValueError, match="event record 0: code 18 is not in COMPUTE"):
        decode_stream(_records((18, 0, 0, 0, 1)), _contracts(), "COMPUTE", 3)
