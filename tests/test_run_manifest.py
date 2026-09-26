# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — run manifest contract tests

"""Exercise schema, semantic and hash refusal through the host command."""

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


def _change_manifest(run: Path, manifest: dict[str, Any], variant: str) -> None:
    """Apply one manifest or file-reference violation to a real RTL run.

    Parameters
    ----------
    run
        Simulation run directory.
    manifest
        Mutable versioned run declaration.
    variant
        Named refusal case.
    """
    if variant == "directory":
        (run / "directory").mkdir()
    if variant == "escape_symlink":
        (run / "outside.bin").symlink_to("/etc/hosts")
    changes: dict[str, tuple[tuple[str | int, ...], object]] = {
        "schema_id": (("schema",), "loop-timing-witness.run-manifest.v2"),
        "non_utc": (("started_utc",), "2026-09-26T02:00:00+02:00"),
        "placement": (("placement",), "unknown"),
        "rate": (("sample_period_ticks",), 1),
        "compute_period": (("profile",), "COMPUTE"),
        "missing_period": (("sample_period_ticks",), None),
        "warmup": (("warmup_cycles",), 3),
        "fault_cycle": (("fault_schedule", 0, "cycle"), 3),
        "fault_delay": (("fault_schedule", 0, "kind"), "drop"),
        "event_digest": (("files", "events", "sha256"), "0" * 64),
        "domain_digest": (("measurement_domain", "sha256"), "0" * 64),
        "source_digest": (("source", "files", 0, "sha256"), "0" * 64),
        "traversal": (("files", "events", "path"), "sub/../events.bin"),
        "directory": (("files", "events", "path"), "directory"),
        "escape_symlink": (("files", "events", "path"), "outside.bin"),
        "missing_source": (("source", "files", 0, "path"), "absent.sv"),
        "board_without_evidence": (("source", "kind"), "board"),
    }
    keys, value = changes[variant]
    target: Any = manifest
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value


@pytest.mark.parametrize(
    ("variant", "finding"),
    [
        ("schema_id", "run manifest schema"),
        ("non_utc", "started_utc must use UTC"),
        ("placement", "placement is not declared"),
        ("rate", "outside the declared control rate"),
        ("compute_period", "controller"),
        ("missing_period", "sample_period_ticks"),
        ("warmup", "warmup_cycles must leave"),
        ("fault_cycle", "fault schedule cycle is outside"),
        ("fault_delay", "nonzero for a non-delay fault"),
        ("event_digest", "input SHA-256 mismatch"),
        ("domain_digest", "input SHA-256 mismatch"),
        ("source_digest", "artefact SHA-256 mismatch"),
        ("traversal", "input path must stay within"),
        ("directory", "not a regular file inside"),
        ("escape_symlink", "not a regular file inside"),
        ("missing_source", "not a regular file inside"),
        ("board_without_evidence", "board_supply_only"),
    ],
)
def test_run_manifest_refuses_invalid_provenance(
    variant: str,
    finding: str,
    make_rtl_run: MakeRtlRun,
    run_tool: RunTool,
    tmp_path: Path,
) -> None:
    """A changed declaration never turns a simulated file into evidence.

    Parameters
    ----------
    variant
        One manifest or file violation.
    finding
        Expected public refusal text.
    make_rtl_run
        Icarus Verilog producer.
    run_tool
        Host command runner.
    tmp_path
        New report path.
    """
    run, manifest = make_rtl_run()
    _change_manifest(run, manifest, variant)
    (run / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    output = tmp_path / "report"
    result = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert result.returncode == 1
    assert finding in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("raw", [b"{", b'{"run_id":1,"run_id":2}'])
def test_run_manifest_refuses_invalid_json(
    raw: bytes, make_rtl_run: MakeRtlRun, run_tool: RunTool, tmp_path: Path
) -> None:
    """JSON syntax errors and repeated keys fail before report creation.

    Parameters
    ----------
    raw
        Invalid manifest bytes.
    make_rtl_run
        Icarus Verilog producer.
    run_tool
        Host command runner.
    tmp_path
        New report path.
    """
    run, _ = make_rtl_run()
    (run / "manifest.json").write_bytes(raw)
    output = tmp_path / "report"
    result = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert result.returncode == 1
    assert not output.exists()


@pytest.mark.parametrize(
    ("variant", "finding"),
    [
        ("schema", "measurement domain invalid"),
        ("semantic", "measurement domain invalid"),
        ("wire", "differs from the 16-byte host wire layout"),
    ],
)
def test_host_refuses_changed_measurement_domain(
    variant: str, finding: str, make_rtl_run: MakeRtlRun, run_tool: RunTool, tmp_path: Path
) -> None:
    """The public CLI refuses a hash-bound run snapshot with domain drift.

    Parameters
    ----------
    variant
        Structural, semantic or wire-layout drift in the run package.
    finding
        Expected refusal text.
    make_rtl_run
        Icarus Verilog producer.
    run_tool
        Host command runner.
    tmp_path
        Report parent.
    """
    run, manifest = make_rtl_run()
    domain_path = run / "measurement-domain.json"
    domain = json.loads(domain_path.read_text(encoding="utf-8"))
    if variant == "schema":
        domain["design_contracts"].pop("event_record")
    elif variant == "semantic":
        domain["claims"] = ["unmeasured claim"]
    else:
        record = domain["design_contracts"]["event_record"]
        record["fields"][0]["type"] = "u16"
        for field in record["fields"][1:]:
            field["offset_bytes"] += 1
        record["record_size_bytes"] = 17
    domain_path.write_text(json.dumps(domain) + "\n", encoding="utf-8")
    manifest["measurement_domain"]["sha256"] = hashlib.sha256(domain_path.read_bytes()).hexdigest()
    (run / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    output = tmp_path / "report"
    result = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert result.returncode == 1
    assert finding in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("variant", ["overflow", "artefact_digest"])
def test_forged_board_input_is_refused(
    variant: str, make_rtl_run: MakeRtlRun, run_tool: RunTool, tmp_path: Path
) -> None:
    """An intentionally false board declaration fails without producing a report.

    Parameters
    ----------
    variant
        Missing acceptance condition or mismatched declared artefact.
    make_rtl_run
        Icarus Verilog producer.
    run_tool
        Host command runner.
    tmp_path
        New report path.
    """
    run, manifest = make_rtl_run()
    manifest["source"]["kind"] = "board"
    reference = manifest["source"]["files"][0]
    manifest["hardware_artifacts"] = {
        name: reference.copy()
        for name in ("bitstream", "firmware", "linux_image", "controller_binary")
    }
    manifest["hardware_artifacts"]["libero_version"] = "declared-for-refusal-test"
    manifest["hardware_artifacts"]["toolchain_version"] = "declared-for-refusal-test"
    manifest["instrument"].update(
        {
            "floor_ticks": 0,
            "known_period_pass": True,
            "injected_delay_pass": True,
            "overflow_pass": True,
            "bus_offset_pass": True,
        }
    )
    manifest["environment"] = {"room_temperature_c": 20, "board_supply_only": True}
    if variant == "overflow":
        manifest["instrument"]["fifo_overflow_count"] = 1
    else:
        manifest["hardware_artifacts"]["controller_binary"]["sha256"] = "0" * 64
    (run / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    output = tmp_path / "report"
    result = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert result.returncode == 1
    expected = "overflow" if variant == "overflow" else "SHA-256 mismatch"
    assert expected in result.stderr
    assert not output.exists()
