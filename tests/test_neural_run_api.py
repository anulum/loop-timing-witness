# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — public neural analysis admission and command controls

"""Exercise complete public entry points without fabricating source admission."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from copy import copy
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

import loop_timing_witness as package
from loop_timing_witness.manifest_io import canonical_json_bytes
from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError
from loop_timing_witness.neural_run_api import NeuralRunInputs

if TYPE_CHECKING:
    from conftest import MakeRtlRun

_ROOT = Path(__file__).resolve().parents[1]
_ORIGINAL_DIGEST = "c5397e9146741b23a9e85f686d0e47b5bbc1dafb8e0f1c70df92c999e6c13315"


def _declaration() -> dict[str, Any]:
    """Derive a public declaration without creating a public acquisition.

    Returns
    -------
    dict[str, Any]
        Actual original declarations carrying the still-unadmitted private policy.
    """
    raw = (_ROOT / "tests/data/neural-native-original.run.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == _ORIGINAL_DIGEST
    value: dict[str, Any] = json.loads(raw)
    value.update(
        schema_id="loop-timing-witness.neural-step-run.v1",
        native_source_cohort="sc-neurocore-neural-step-1n1b16t.v1",
        source_contract_ref={
            "path": "native_cohort_policy.json",
            "sha256": "f1e44f86fee1a20c75e8990acb65e66652138e09cd6c4dc545815431d50127dc",
            "byte_length": 10570,
        },
    )
    return value


def _command(path: Path, output: Path) -> subprocess.CompletedProcess[str]:
    """Run the existing installed analysis command with a finite deadline.

    Parameters
    ----------
    path
        Original caller-controlled manifest path.
    output
        Exclusive output destination which must remain absent after refusal.

    Returns
    -------
    subprocess.CompletedProcess[str]
        Actual installed command status and original diagnostic streams.
    """
    command = Path(sys.executable).with_name("loop-timing-witness-analyze")
    assert command.is_file()
    return subprocess.run(
        [str(command), str(path), "--output-dir", str(output)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def test_unadmitted_declaration_is_refused_by_full_api_and_installed_cli(tmp_path: Path) -> None:
    """Require reviewed consumer admission before any copied policy or checker is used.

    Parameters
    ----------
    tmp_path
        Actual prospective manifest without source, runtime or trace files.
    """
    manifest = tmp_path / "run.json"
    manifest.write_text(json.dumps(_declaration()), encoding="utf-8")
    with pytest.raises(NeuralCaptureRefusalError, match=r"^No reviewed source contract"):
        package.load_neural_run(manifest)
    result = _command(manifest, tmp_path / "report")
    assert result.returncode == 1
    assert result.stdout == ""
    assert "No reviewed source contract is admitted" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (tmp_path / "report").exists()
    assert {p.name for p in tmp_path.iterdir()} == {"run.json"}


@pytest.mark.parametrize("kind", ["private", "unknown", "duplicate", "float", "oversized"])
def test_invalid_neural_input_is_refused_without_output(tmp_path: Path, kind: str) -> None:
    """Keep actual private input, malformed declarations and excessive bytes fail-closed.

    Parameters
    ----------
    tmp_path
        Task-owned original input control and absent report destination.
    kind
        Actual private identity or a deliberate grammar contradiction.
    """
    value = _declaration()
    if kind == "private":
        raw = (_ROOT / "tests/data/neural-native-original.run.json").read_bytes()
    elif kind == "duplicate":
        raw = b'{"schema_id":"x","schema_id":"y"}'
    elif kind == "oversized":
        raw = json.dumps(value).encode() + b" " * 65536
    else:
        if kind == "unknown":
            value["schema_id"] = "unrecognised.neural.v1"
        else:
            value["event_codes"]["input_step_applied"] = 14.0
        raw = json.dumps(value).encode()
    manifest = tmp_path / "run.json"
    manifest.write_bytes(raw)
    with pytest.raises(NeuralCaptureRefusalError):
        package.load_neural_run(manifest)
    result = _command(manifest, tmp_path / "report")
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("run analysis: FAIL:")
    assert "Traceback" not in result.stderr
    assert not (tmp_path / "report").exists()


@pytest.mark.parametrize("kind", ["missing", "directory", "symlink", "fifo"])
def test_full_api_and_command_bound_actual_root_file_kind(tmp_path: Path, kind: str) -> None:
    """Refuse nonregular and no-follow root inputs without waiting on a FIFO writer.

    Parameters
    ----------
    tmp_path
        Real filesystem object allocation.
    kind
        Unsupported actual root file kind.
    """
    manifest = tmp_path / "run.json"
    if kind == "directory":
        manifest.mkdir()
    elif kind == "symlink":
        original = tmp_path / "original.json"
        original.write_text(json.dumps(_declaration()), encoding="utf-8")
        manifest.symlink_to(original)
    elif kind == "fifo":
        os.mkfifo(manifest)
    with pytest.raises(NeuralCaptureRefusalError):
        package.load_neural_run(manifest)
    result = _command(manifest, tmp_path / "report")
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert not (tmp_path / "report").exists()


def test_neural_report_rejects_real_legacy_inputs(make_rtl_run: MakeRtlRun) -> None:
    """Preserve a real legacy report while refusing to treat it as neural verification.

    Parameters
    ----------
    make_rtl_run
        Actual Icarus-generated CONTROL capture and complete legacy manifest.
    """
    directory, _ = make_rtl_run()
    inputs = package.load_run(directory / "manifest.json")
    report, _ = package.build_report(inputs)
    assert report["valid"] is True
    with pytest.raises(NeuralCaptureRefusalError, match="complete public run loader snapshot"):
        package.build_neural_run_report(inputs)
    with pytest.raises(NeuralCaptureRefusalError, match="complete public run loader snapshot"):
        NeuralRunInputs(
            directory,
            (directory / "manifest.json").read_bytes(),
            canonical_json_bytes(report),
            object(),
        )


def test_actual_neural_loader_snapshot_cannot_be_replaced() -> None:
    """Keep caller report edits outside an actual full-verification snapshot.

    Without an external acquisition, require the recorded declaration's missing
    originals to refuse. ``PUBLIC_NEURAL_MANIFEST`` enables the complete loader
    and replacement control on a genuine supported acquisition.
    """
    selected = os.environ.get("PUBLIC_NEURAL_MANIFEST")
    if selected is None:
        with pytest.raises(NeuralCaptureRefusalError):
            package.load_neural_run(_ROOT / "tests/data/neural-selected-original.run.json")
        return
    inputs = package.load_neural_run(Path(selected))
    original = package.build_neural_run_report(inputs)
    caller = package.build_neural_run_report(inputs)
    caller["verification"]["whole"] = not original["verification"]["whole"]
    with pytest.raises(NeuralCaptureRefusalError, match="complete public run loader snapshot"):
        replace(inputs, report_bytes=canonical_json_bytes(caller))
    assert package.build_neural_run_report(inputs) == original
    assert package.build_neural_run_report(copy(inputs)) == original
    assert not hasattr(inputs, "loader_origin")
