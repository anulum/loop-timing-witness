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
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from loop_timing_witness import load_run

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
        ("non_utc", "started_utc must be an RFC 3339 date-time in UTC"),
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


def test_bound_binary_file_cannot_substitute_for_native_receipt(
    make_rtl_run: MakeRtlRun, run_tool: RunTool, tmp_path: Path
) -> None:
    """Bind an actual optional input but refuse its incompatible receipt format.

    Parameters
    ----------
    make_rtl_run
        Real witness capture with its original event bytes and manifest hashes.
    run_tool
        Public analyser command, including native receipt interpretation.
    tmp_path
        Exclusive report path that must remain absent on refusal.
    """
    run, manifest = make_rtl_run()
    original = (run / "events.bin").read_bytes()
    manifest["native_metadata"] = manifest["files"]["events"].copy()
    path = run / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    inputs = load_run(path)
    assert inputs.files["native_metadata"] == inputs.files["events"] == original
    assert inputs.manifest["native_metadata"]["sha256"] == hashlib.sha256(original).hexdigest()
    output = tmp_path / "wrong-receipt-report"
    result = run_tool("analyze_run", str(path), "--output-dir", str(output))
    assert result.returncode == 1
    assert "native metadata:" in result.stderr
    assert not output.exists()
    assert (run / "events.bin").read_bytes() == original


@pytest.mark.parametrize(
    "started_utc",
    [
        "2026-09-26t00:00:00z",
        "2026-09-26T00:00:00z",
        "2026-09-26t00:00:00Z",
        "2026-09-26T00:00:00+00:00",
        "2026-09-26T00:00:00-00:00",
        "2026-09-26T00:00:00.123456789Z",
    ],
)
def test_schema_valid_utc_notation_reaches_the_real_report(
    started_utc: str, make_rtl_run: MakeRtlRun, run_tool: RunTool, tmp_path: Path
) -> None:
    """Accept schema-valid UTC spellings without rewriting run provenance.

    Parameters
    ----------
    started_utc
        Case variants of the RFC3339 separators or explicit zero UTC offset.
    make_rtl_run
        Real RTL capture with original source and input hashes.
    run_tool
        Public analyser command through schema, loader and report transaction.
    tmp_path
        Exclusive report output.
    """
    run, manifest = make_rtl_run()
    manifest["started_utc"] = started_utc
    path = run / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    inputs = load_run(path)
    assert inputs.manifest["started_utc"] == started_utc
    output = tmp_path / "utc-report"
    result = run_tool("analyze_run", str(path), "--output-dir", str(output))
    assert result.returncode == 0, result.stderr
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["started_utc"] == started_utc
    assert report["evidence_status"] == "simulation_only"
    assert report["input_sha256"]["events"] == manifest["files"]["events"]["sha256"]


@pytest.mark.parametrize(
    "started_utc",
    [
        "2026-09-26T02:00:00+02:00",
        "2026-09-26T00:00:60Z",
        "2026-02-30T00:00:00Z",
        "0000-01-01T00:00:00Z",
        "2026-09-26T24:00:00Z",
        "2026-09-26T00:00Z",
        "2026-09-26T00:00:00Z\n",
        "2026-09-26 00:00:00Z",
        "2026-09-26T00:00:00.Z",
        "\uff12026-09-26T00:00:00Z",
    ],
)
def test_started_utc_must_name_one_real_utc_instant(
    started_utc: str, make_rtl_run: MakeRtlRun
) -> None:
    """Refuse other offsets, impossible instants and loose spellings with one authored text.

    Parameters
    ----------
    started_utc
        Schema-valid string that is not one RFC 3339 UTC instant.
    make_rtl_run
        Real RTL capture with original source and input hashes.
    """
    run, manifest = make_rtl_run()
    manifest["started_utc"] = started_utc
    path = run / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match=r"^started_utc must be an RFC 3339 date-time in UTC$"):
        load_run(path)


def test_schema_refusals_name_only_the_failing_locations(make_rtl_run: MakeRtlRun) -> None:
    """Report the first run location, and every distinct domain location, without library text.

    Parameters
    ----------
    make_rtl_run
        Real RTL capture with original source and input hashes.
    """
    run, manifest = make_rtl_run()
    path = run / "manifest.json"
    changed = {**manifest, "files": {**manifest["files"], "events": {"path": "events.bin"}}}
    changed.pop("cycle_count")
    path.write_text(json.dumps(changed), encoding="utf-8")
    expected = "run manifest (root): does not satisfy the run manifest schema"
    with pytest.raises(ValueError, match=f"^{re.escape(expected)}$"):
        load_run(path)
    changed["cycle_count"] = manifest["cycle_count"]
    path.write_text(json.dumps(changed), encoding="utf-8")
    expected = "run manifest files/events: does not satisfy the run manifest schema"
    with pytest.raises(ValueError, match=f"^{re.escape(expected)}$"):
        load_run(path)
    domain_path = run / "measurement-domain.json"
    domain = json.loads(domain_path.read_text(encoding="utf-8"))
    for name in ("timebase", "event_record"):
        domain["design_contracts"].pop(name)
    domain["license"] = "MIT"
    domain_path.write_text(json.dumps(domain), encoding="utf-8")
    manifest["measurement_domain"]["sha256"] = hashlib.sha256(domain_path.read_bytes()).hexdigest()
    path.write_text(json.dumps(manifest), encoding="utf-8")
    expected = (
        "measurement domain invalid: "
        "schema: design_contracts: does not satisfy the measurement-domain schema; "
        "schema: license: does not satisfy the measurement-domain schema"
    )
    with pytest.raises(ValueError, match=f"^{re.escape(expected)}$"):
        load_run(path)
