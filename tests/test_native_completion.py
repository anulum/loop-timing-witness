# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — native completion receipt integrity

"""Bind actual native completion receipts to the public hash-verifying analyzer."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest
from native_simulation_manifest import write_native_manifest
from test_native_run import configuration, native_run

from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import RunTool

__all__ = ["native_run"]


@pytest.mark.parametrize(
    "mutation",
    [
        "none",
        "records",
        "misses",
        "overflow",
        "cycles",
        "source",
        "samples",
        "safe",
        "warmup",
        "schema",
        "eventsha",
        "eventbytes",
        "configsha",
        "fault_kind",
        "fault_cycle",
        "fault_delay",
        "fault_absent",
        "fault_valid_drop",
        "fault_valid_delay",
        "fault_valid_freeze",
        "fault_valid_overload",
    ],
)
def test_bound_completion(
    native_run: Path, tmp_path: Path, run_tool: RunTool, mutation: str
) -> None:
    """Verify original counters and reject rehashed but contradictory native receipts.

    Parameters
    ----------
    native_run
        Actual production RTL/controller executable.
    tmp_path
        Exclusive capture allocation.
    run_tool
        Public analyzer process.
    mutation
        Original receipt or deliberate semantic corruption after real execution.
    """
    config = tmp_path / "configuration.txt"
    fault = {
        "fault_cycle": "drop",
        "fault_delay": "delay",
        "fault_absent": "drop",
        "fault_valid_drop": "drop",
        "fault_valid_delay": "delay",
        "fault_valid_freeze": "freeze",
        "fault_valid_overload": "overload",
    }.get(mutation, "none")
    config.write_text(configuration("pid", fault), encoding="utf-8")
    program = tmp_path / "run_simulation"
    shutil.copyfile(native_run, program)
    shutil.copyfile(
        REPOSITORY_ROOT / "measurement-domain.json", tmp_path / "measurement-domain.json"
    )
    metadata = tmp_path / "native_metadata.json"
    result = subprocess.run(
        [
            str(native_run),
            str(config),
            str(tmp_path / "events.bin"),
            str(tmp_path / "tracking_raw.csv"),
            "--metadata",
            str(metadata),
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    version = subprocess.run(
        ["verilator", "--version"], check=True, text=True, capture_output=True, timeout=10
    ).stdout.strip()
    path = write_native_manifest(
        tmp_path, "2026-09-27T00:00:00Z", [program, config, metadata], version
    )
    manifest = json.loads(path.read_text())
    facts = json.loads(metadata.read_text())
    if mutation in {"records", "misses", "overflow"}:
        facts["result"][mutation] += 1
    elif mutation in {"schema", "samples", "safe"}:
        field, value = {
            "schema": ("overflow", -1),
            "samples": ("samples", facts["result"]["samples"] - 1),
            "safe": ("safe", True),
        }[mutation]
        facts["result"][field] = value
    elif mutation == "warmup":
        manifest["warmup_cycles"] = 8
    elif mutation in {"fault_kind", "fault_cycle", "fault_delay", "fault_absent"}:
        field, value = {
            "fault_kind": ("kind", "drop"),
            "fault_cycle": ("cycle", facts["fault"]["cycle"] + 1),
            "fault_delay": ("duration_periods", facts["fault"]["duration_periods"] + 1),
            "fault_absent": ("kind", "none"),
        }[mutation]
        facts["fault"][field] = value
    elif mutation in {"cycles", "source", "eventsha", "eventbytes", "configsha"}:
        target, key, value = {
            "cycles": (facts, "cycles", facts["cycles"] + 1),
            "source": (facts, "source_kind", "uio_unqualified"),
            "eventsha": (facts["artifacts"]["events"], "sha256", "0" * 64),
            "eventbytes": (
                facts["artifacts"]["events"],
                "bytes",
                facts["artifacts"]["events"]["bytes"] + 1,
            ),
            "configsha": (facts["artifacts"]["configuration"], "sha256", "0" * 64),
        }[mutation]
        target[key] = value
    metadata.write_text(json.dumps(facts), encoding="utf-8")
    digest = hashlib.sha256(metadata.read_bytes()).hexdigest()
    manifest["native_metadata"]["sha256"] = digest
    for reference in manifest["source"]["files"]:
        if reference["path"] == "native_metadata.json":
            reference["sha256"] = digest
    path.write_text(json.dumps(manifest), encoding="utf-8")
    result = run_tool("analyze_run", str(path), "--output-dir", str(tmp_path / "report"))
    if mutation in {"none", "warmup"} or mutation.startswith("fault_valid_"):
        assert result.returncode == 0, result.stdout + result.stderr
        report = json.loads((tmp_path / "report/report.json").read_text())
        assert report["native_completion"] == facts["result"]
        assert report["input_sha256"]["native_metadata"] == digest
        assert report["tracking_error"]["sample_count"] == (
            24 if mutation == "warmup" else facts["result"]["samples"]
        )
    else:
        assert result.returncode == 1
        assert "native" in result.stderr
        assert not (tmp_path / "report").exists()
