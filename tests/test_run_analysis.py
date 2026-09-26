# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — event analysis tests

"""Drive timing and fault edge cases through binary files and the host CLI."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from run_analysis import distribution

MakeRtlRun = Callable[[], tuple[Path, dict[str, Any]]]
RunTool = Callable[..., subprocess.CompletedProcess[str]]
RECORD_BYTES = 16


def _records(path: Path) -> list[bytes]:
    """Split a real RTL event file into fixed-size records for corruption tests.

    Parameters
    ----------
    path
        Binary event file.

    Returns
    -------
    list[bytes]
        Records in fabric-capture order.
    """
    raw = path.read_bytes()
    return [raw[offset : offset + RECORD_BYTES] for offset in range(0, len(raw), RECORD_BYTES)]


def _alter(variant: str, records: list[bytes], manifest: dict[str, Any]) -> list[bytes]:
    """Apply one temporally valid fault-analysis mutation.

    Parameters
    ----------
    variant
        Named edge case.
    records
        Real RTL output records.
    manifest
        Mutable run declaration.

    Returns
    -------
    list[bytes]
        Modified records.
    """
    filters: dict[str, Callable[[bytes], bool]] = {
        "consecutive_misses": lambda record: not (record[0] == 3 and record[4] == 1),
        "missing_deadline": lambda record: not (record[0] == 4 and record[4] == 1),
        "no_deadlines": lambda record: record[0] not in {4, 5},
        "undetected_fault": lambda record: record[0] != 7,
        "unmatched_detection": lambda record: record[0] != 6,
        "no_interval_samples": lambda record: record[0] != 2,
    }
    if variant in {"unmatched_detection", "unmatched_schedule"}:
        manifest["fault_schedule"] = []
    if variant == "missing_write":
        return records[:-1]
    if variant in filters:
        return [record for record in records if filters[variant](record)]
    if variant == "safe_without_miss":
        records.insert(4, struct.pack("<BBHIQ", 5, 0, 0, 0, 5001))
    elif variant == "overlapping_injections":
        records.insert(7, struct.pack("<BBHIQ", 6, 0, 0, 1, 5040))
        manifest["fault_schedule"].insert(0, {"cycle": 1, "kind": "delay", "delay_periods": 1})
    elif variant == "negative_interval":
        records[1] = bytes([3]) + records[1][1:]
        records[2] = bytes([2]) + records[2][1:]
    elif variant == "no_analysed_events":
        manifest["warmup_cycles"] = 2
        manifest["fault_schedule"] = []
        manifest["files"]["tracking"] = None
        manifest["files"]["power"] = None
        return [record for record in records if record[4] == 0]
    return records


@pytest.mark.parametrize(
    ("variant", "finding"),
    [
        ("unmatched_detection", "fault detection lacks a prior injection"),
        ("unmatched_schedule", "fault schedule does not match"),
        ("safe_without_miss", "safe state lacks a prior missed deadline"),
        ("overlapping_injections", "fault injection overlaps an undetected fault"),
        ("negative_interval", "ends before it starts"),
    ],
)
def test_inconsistent_fault_or_interval_refused(
    variant: str,
    finding: str,
    make_rtl_run: MakeRtlRun,
    run_tool: RunTool,
    tmp_path: Path,
) -> None:
    """Hash-valid event changes cannot invent a coherent timing result.

    Parameters
    ----------
    variant
        One event inconsistency.
    finding
        Expected refusal text.
    make_rtl_run
        Icarus Verilog producer.
    run_tool
        Host command runner.
    tmp_path
        New report path.
    """
    run, manifest = make_rtl_run()
    changed = _alter(variant, _records(run / "events.bin"), manifest)
    raw = b"".join(changed)
    (run / "events.bin").write_bytes(raw)
    manifest["files"]["events"]["sha256"] = hashlib.sha256(raw).hexdigest()
    (run / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    output = tmp_path / "report"
    result = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert result.returncode == 1
    assert finding in result.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    "variant",
    [
        "missing_write",
        "consecutive_misses",
        "missing_deadline",
        "no_deadlines",
        "undetected_fault",
        "no_analysed_events",
        "no_interval_samples",
    ],
)
def test_partial_event_observation_is_explicit(
    variant: str, make_rtl_run: MakeRtlRun, run_tool: RunTool, tmp_path: Path
) -> None:
    """Partial simulated streams report missing samples or invalidity honestly.

    Parameters
    ----------
    variant
        One absent event class.
    make_rtl_run
        Icarus Verilog producer.
    run_tool
        Host command runner.
    tmp_path
        New report path.
    """
    run, manifest = make_rtl_run()
    changed = _alter(variant, _records(run / "events.bin"), manifest)
    raw = b"".join(changed)
    (run / "events.bin").write_bytes(raw)
    manifest["files"]["events"]["sha256"] = hashlib.sha256(raw).hexdigest()
    (run / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    output = tmp_path / "report"
    result = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert result.returncode == 0, result.stderr
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["source_kind"] == "rtl_simulation"
    if variant in {"missing_deadline", "no_deadlines", "no_analysed_events"}:
        assert report["valid"] is False
    if variant == "undetected_fault":
        assert report["events"]["control"]["undetected_faults"] == 1
    if variant == "consecutive_misses":
        assert report["events"]["control"]["deadline_misses"] == 2
    if variant == "no_interval_samples":
        assert report["events"]["intervals"]["scheduling_latency"]["sample_count"] == 0


def test_negative_distribution_interval_is_refused() -> None:
    """The public distribution API refuses an impossible negative interval."""
    with pytest.raises(ValueError, match="negative event interval"):
        distribution([-1])
