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
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

MakeRtlRun = Callable[[], tuple[Path, dict[str, Any]]]
RunTool = Callable[..., subprocess.CompletedProcess[str]]


@pytest.mark.parametrize(
    ("variant", "finding"),
    [
        ("empty", "event file is empty"),
        ("partial", "whole number of 16-byte records"),
        ("reserved", "reserved bits must be zero"),
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
    if variant == "empty":
        raw.clear()
    elif variant == "partial":
        raw.pop()
    elif variant == "reserved":
        raw[1] = 1
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
    elif variant == "duplicate_event":
        raw[16] = 1
    (run / "events.bin").write_bytes(raw)
    manifest["files"]["events"]["sha256"] = hashlib.sha256(raw).hexdigest()
    (run / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    output = tmp_path / "report"
    result = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert result.returncode == 1
    assert finding in result.stderr
    assert not output.exists()
