# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original ISA logger completion and corruption regression tests

"""Validate real Spike/production-RTL capture bytes and reject corrupted drain evidence."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from amp_completion import PREFIX, AmpCompletion, completion_receipt, validate_capture

ROOT = Path(__file__).resolve().parents[1]

# Captured from RV64 hart 2 with production RTL; hart 1 parked in WFI, 2026-09-27.
EVENTS = bytes.fromhex(
    "0100000000000000a5020000000000000200000000000000d80400000000000003000000000000004c050000000000000400000000000000a5820000000000000100000001000000a5820000000000000200000001000000cc85000000000000030000000100000040860000000000000400000001000000a5020100000000000100000002000000a5020100000000000200000002000000c006010000000000030000000200000034070100000000000400000002000000a5820100000000000100000003000000a5820100000000000200000003000000bc85010000000000030000000300000030860100000000000400000003000000a5020200000000000100000004000000a5020200000000000200000004000000b006020000000000030000000400000024070200000000000400000004000000a5820200000000000100000005000000a5820200000000000200000005000000ac85020000000000030000000500000020860200000000000400000005000000a5020300000000000100000006000000a5020300000000000200000006000000a006030000000000030000000600000014070300000000000400000006000000a5820300000000000100000007000000a58203000000000002000000070000009c85030000000000030000000700000010860300000000000400000007000000a5020400000000000100000008000000a50204000000000002000000080000009006040000000000030000000800000004070400000000000400000008000000a5820400000000000100000009000000a58204000000000002000000090000008c85040000000000030000000900000000860400000000000400000009000000a502050000000000"
)
TRACKING = (
    b"cycle,reference_raw,output_raw,velocity_raw,command_raw,integral_raw,derivative_raw,clipped,integral_held,submitted,sample_ticks,irq_generation,overload_work\n"
    b"0,16777216,0,0,16777216,0,0,0,1,1,1240,1,0\n"
    b"1,16777216,8,16769,16777208,0,0,0,0,1,34252,2,0\n"
    b"2,16777216,32,33521,16777184,0,0,0,0,1,67264,3,0\n"
    b"3,16777216,73,50256,16777143,0,0,0,0,1,99772,4,0\n"
    b"4,16777216,131,66974,16777085,0,0,0,0,1,132784,5,0\n"
    b"5,16777216,205,83675,16777011,0,0,0,0,1,165292,6,0\n"
    b"6,16777216,296,100359,16776920,0,0,0,0,1,198304,7,0\n"
    b"7,16777216,404,117027,16776812,0,0,0,0,1,230812,8,0\n"
    b"8,16777216,528,133678,16776688,0,0,0,0,1,263824,9,0\n"
    b"9,16777216,669,150312,16776547,0,0,0,0,1,296332,10,0\n"
)
LOG = (
    b'WITNESS_AMP_COMPLETION {"samples":10,"events":40,"misses":0,"overflow":0,'
    b'"safe":false,"thermal":false}\n'
)


def test_actual_logger_receipt_and_capture() -> None:
    """Admit original target-closed outputs with their actual logger counters."""
    completion = completion_receipt(LOG)
    assert completion == AmpCompletion(10, 40, 0, 0, safe=False, thermal=False)
    validate_capture(
        completion, EVENTS, TRACKING, (ROOT / "measurement-domain.json").read_bytes(), 10
    )


@pytest.mark.parametrize("log", [b"", b"exit 0\n", LOG + LOG])
def test_missing_or_duplicate_drain(log: bytes) -> None:
    """Refuse an exit alone or conflicting completion owners.

    Parameters
    ----------
    log
        Actual receipt removed or duplicated.
    """
    with pytest.raises(ValueError, match="exactly one"):
        completion_receipt(log)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("thermal", 0),
        ("safe", 0),
        ("safe", "false"),
        ("extra", 1),
        ("samples", True),
        ("samples", -1),
        ("events", 1 << 64),
        ("misses", 1 << 32),
        ("overflow", -1),
        ("events", "40"),
    ],
)
def test_malformed_native_counter(field: str, value: object) -> None:
    """Reject wrong scalar types, bounds and unexpected receipt fields.

    Parameters
    ----------
    field
        Actual receipt field to corrupt.
    value
        Invalid replacement or additional field.
    """
    original = json.loads(LOG.removeprefix(PREFIX))
    original[field] = value
    with pytest.raises(ValueError, match=r"invalid|outside"):
        completion_receipt(PREFIX + json.dumps(original).encode("ascii"))


@pytest.mark.parametrize("fault", ["overflow", "events", "samples", "cycle", "reserved", "missing"])
def test_corrupt_capture_refused(fault: str) -> None:
    """Refuse inconsistent or lost records while preserving genuine missing-cycle semantics.

    Parameters
    ----------
    fault
        Exact observed-counter or raw-stream corruption.
    """
    completion = completion_receipt(LOG)
    events, tracking = EVENTS, TRACKING
    if fault == "overflow":
        completion = replace(completion, overflow=1)
    elif fault == "events":
        completion = replace(completion, events=39)
    elif fault == "samples":
        completion = replace(completion, samples=9)
    elif fault == "cycle":
        tracking = tracking.replace(b"0,16777216", b"1,16777216", 1)
    elif fault == "reserved":
        events = events[:1] + b"\x01" + events[2:]
    else:
        events = events[:16] + events[32:]
        completion = replace(completion, events=39)
    with pytest.raises(ValueError, match=r"AMP|native|reserved"):
        validate_capture(
            completion, events, tracking, (ROOT / "measurement-domain.json").read_bytes(), 10
        )
