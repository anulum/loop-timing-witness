# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — tests of capability inventory generation

"""Contract tests for the generated capability inventory and its drift check."""

from __future__ import annotations

import json
import shutil
from typing import TYPE_CHECKING

import pytest

from conftest import REPOSITORY_ROOT, RunTool
from generate_capability_inventory import DEFAULT_INVENTORY, generate_inventory, main
from manifest_io import sha256_of_file
from validate_measurement_domain import DEFAULT_MANIFEST, DEFAULT_SCHEMA

if TYPE_CHECKING:
    from pathlib import Path


def copied_manifest(tmp_path: Path) -> list[str]:
    """Copy the committed manifest into a scratch directory.

    Parameters
    ----------
    tmp_path
        Scratch directory.

    Returns
    -------
    list[str]
        Command-line arguments that point the tool at the copy and at a
        scratch inventory path.
    """
    shutil.copyfile(DEFAULT_MANIFEST, tmp_path / "measurement-domain.json")
    return [
        "--manifest",
        str(tmp_path / "measurement-domain.json"),
        "--inventory",
        str(tmp_path / "capability-inventory.json"),
    ]


def test_inventory_projects_the_manifest_exactly() -> None:
    """The inventory reports zero capabilities and embeds the manifest digest."""
    inventory = generate_inventory(DEFAULT_MANIFEST, DEFAULT_SCHEMA)
    assert inventory == {
        "schema": "loop-timing-witness.capability-inventory.v1",
        "schema_version": "1.0.0",
        "project": "LOOP-TIMING-WITNESS",
        "evidence_maturity": "architecture_only",
        "implemented_capability_count": 0,
        "capabilities": [],
        "claims": [],
        "source": {
            "manifest_path": "measurement-domain.json",
            "manifest_sha256": sha256_of_file(DEFAULT_MANIFEST),
        },
    }


def test_committed_inventory_is_in_sync_in_a_subprocess(run_tool: RunTool) -> None:
    """The script entry point confirms the committed inventory byte for byte."""
    completed = run_tool("generate_capability_inventory", "--check")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == "capability-inventory: PASS in sync"
    assert DEFAULT_INVENTORY == REPOSITORY_ROOT / "capability-inventory.json"


def test_write_then_check_round_trip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A written inventory passes its own check and equals the committed bytes."""
    arguments = copied_manifest(tmp_path)
    assert main([*arguments, "--write"]) == 0
    assert "capability-inventory: wrote" in capsys.readouterr().out
    assert main([*arguments, "--check"]) == 0
    assert (tmp_path / "capability-inventory.json").read_bytes() == DEFAULT_INVENTORY.read_bytes()


def test_manifest_edit_is_detected_as_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Changing the manifest after generation changes its digest and fails the check."""
    arguments = copied_manifest(tmp_path)
    assert main([*arguments, "--write"]) == 0
    manifest_path = tmp_path / "measurement-domain.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["purpose"] += " Revised."
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    capsys.readouterr()
    assert main([*arguments, "--check"]) == 1
    assert (
        capsys.readouterr().out.strip()
        == "capability-inventory: FAIL drift between manifest and inventory"
    )


def test_manual_inventory_edit_is_detected_as_drift(tmp_path: Path) -> None:
    """A single added byte in the inventory fails the check."""
    arguments = copied_manifest(tmp_path)
    assert main([*arguments, "--write"]) == 0
    inventory = tmp_path / "capability-inventory.json"
    inventory.write_bytes(inventory.read_bytes() + b"\n")
    assert main([*arguments, "--check"]) == 1


def test_missing_inventory_fails_the_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An absent committed inventory is a failure, not a skip."""
    assert main([*copied_manifest(tmp_path), "--check"]) == 1
    assert "FAIL cannot read committed inventory" in capsys.readouterr().out


def test_invalid_manifest_is_never_projected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A manifest that claims a capability produces no inventory at all."""
    arguments = copied_manifest(tmp_path)
    manifest_path = tmp_path / "measurement-domain.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["capabilities"] = ["event witness"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert main([*arguments, "--write"]) == 1
    output = capsys.readouterr().out
    assert (
        "capability-inventory: FAIL manifest is invalid: "
        "capabilities: must be [] at architecture_only" in output
    )
    assert not (tmp_path / "capability-inventory.json").exists()


def test_write_failure_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """An inventory path whose directory does not exist fails the write cleanly."""
    arguments = copied_manifest(tmp_path)
    arguments[-1] = str(tmp_path / "absent" / "capability-inventory.json")
    assert main([*arguments, "--write"]) == 1
    assert "FAIL cannot write inventory" in capsys.readouterr().out


def test_exactly_one_mode_is_required() -> None:
    """Running without --check or --write is a usage error."""
    with pytest.raises(SystemExit) as raised:
        main([])
    assert raised.value.code == 2
