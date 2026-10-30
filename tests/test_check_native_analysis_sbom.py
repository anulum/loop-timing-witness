# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual Cargo CycloneDX inventory correspondence

"""Exercise the actual native SBOM builder and public verifier with original Cargo data."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest
from check_native_analysis_sbom import audit, main
from test_check_analysis_package import analysis_package

from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import RunTool

__all__ = ["analysis_package"]


@pytest.fixture
def native_sbom(tmp_path: Path) -> Path:
    """Run the real exclusive Make builder with its pinned upstream generator.

    Parameters
    ----------
    tmp_path
        New owned output directory, also retaining original generator metadata.

    Returns
    -------
    Path
        Complete original CycloneDX document after public verification.
    """
    output = tmp_path / "native-sbom"
    result = subprocess.run(
        [
            "make",
            "native-sbom",
            f"VENV={sys.executable.rsplit('/', 1)[0]}",
            f"NATIVE_SBOM_DIRECTORY={output}",
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""
    assert "native-analysis-sbom: PASS" in result.stdout
    assert (output / "cargo-metadata.json").is_file()
    return output / "native-analysis-sbom.cdx.json"


def test_original_inventory_and_exclusive_builder(
    native_sbom: Path, run_tool: RunTool, capsys: pytest.CaptureFixture[str]
) -> None:
    """Admit original API/CLI inventories and preserve existing output on rerun.

    Parameters
    ----------
    native_sbom
        Actual complete generated inventory.
    run_tool
        Maintained CLI subprocess runner.
    capsys
        Capture of the public in-process command diagnostic.
    """
    assert audit(REPOSITORY_ROOT, native_sbom) == []
    assert main([str(native_sbom)]) == 0
    assert capsys.readouterr().out == "native-analysis-sbom: PASS\n"
    result = run_tool("check_native_analysis_sbom", str(native_sbom))
    assert (result.returncode, result.stdout, result.stderr) == (
        0,
        "native-analysis-sbom: PASS\n",
        "",
    )
    original = native_sbom.read_bytes()
    repeated = subprocess.run(
        [
            "make",
            "native-sbom",
            f"VENV={sys.executable.rsplit('/', 1)[0]}",
            f"NATIVE_SBOM_DIRECTORY={native_sbom.parent}",
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert repeated.returncode != 0
    assert "FileExistsError" in repeated.stderr
    assert native_sbom.read_bytes() == original


@pytest.mark.parametrize(
    ("keys", "replacement", "finding"),
    [
        (("metadata", "component", "name"), "changed", "root package"),
        (("metadata", "component", "version"), "9.9.9", "root package"),
        (("metadata", "component", "licenses"), [{"expression": "MIT"}], "root package"),
        (("metadata", "tools", 0, "version"), "0.0.0", "generator identity"),
        (("metadata", "component", "components"), [], "target inventory"),
        (("metadata", "component", "components", 0, "version"), "9.9.9", "target inventory"),
        (("components",), [], "package population"),
        (("components", 0, "purl"), "pkg:cargo/changed@1.0.0", "package URL"),
        (("components", 0, "bom-ref"), "registry+changed", "registry archive"),
        (("components", 0, "hashes", 0, "content"), "0" * 64, "registry archive"),
        (("components", 0, "licenses"), [{"expression": "AGPL-3.0-only"}], "declared licence"),
        (("dependencies",), [], "dependency graph"),
        (("dependencies", 0, "dependsOn"), ["unknown-package"], "dependency graph"),
        (("specVersion",), "1.4", "CycloneDX 1.5"),
        (("bomFormat",), "unsupported", "CycloneDX 1.5"),
    ],
)
def test_changed_original_inventory_refuses(
    native_sbom: Path,
    run_tool: RunTool,
    keys: tuple[str | int, ...],
    replacement: object,
    finding: str,
) -> None:
    """Refuse concrete metadata, archive, licence, population and graph contradictions.

    Parameters
    ----------
    native_sbom
        Actual generated document whose single field is changed.
    run_tool
        Maintained command runner.
    keys
        Original JSON field path.
    replacement
        Contradictory field value.
    finding
        Authored diagnosis required from the public verifier.
    """
    document = json.loads(native_sbom.read_bytes())
    selected = document
    for key in keys[:-1]:
        selected = selected[key]
    selected[keys[-1]] = replacement
    native_sbom.write_text(json.dumps(document), encoding="utf-8")
    result = run_tool("check_native_analysis_sbom", str(native_sbom))
    assert result.returncode == 1
    assert finding in result.stdout
    assert result.stderr == ""


@pytest.mark.parametrize(
    ("keys", "finding"),
    [
        (("metadata", "component", "components"), "target inventory"),
        (("components",), "package population"),
        (("dependencies",), "dependency graph"),
    ],
)
def test_duplicate_original_identity_refuses(
    native_sbom: Path, keys: tuple[str, ...], finding: str
) -> None:
    """Require unique actual targets, registry components and graph nodes.

    Parameters
    ----------
    native_sbom
        Actual original inventory.
    keys
        Original array receiving a conflicting record with the same identity.
    finding
        Expected public correspondence refusal.
    """
    document = json.loads(native_sbom.read_bytes())
    selected = document
    for key in keys:
        selected = selected[key]
    duplicate = dict(selected[0])
    if keys == ("dependencies",):
        duplicate["dependsOn"] = ["unregistered-package"]
    else:
        duplicate["description"] = "Conflicting duplicate of the original identity"
    selected.append(duplicate)
    native_sbom.write_text(json.dumps(document), encoding="utf-8")
    assert any(finding in item for item in audit(REPOSITORY_ROOT, native_sbom))


@pytest.mark.parametrize("damage", ["missing", "symlink", "fifo", "oversize", "json", "unicode"])
def test_unavailable_inventory_is_bounded_and_authored(
    native_sbom: Path, run_tool: RunTool, damage: str
) -> None:
    """Refuse real unavailable or malformed inputs without blocking on a FIFO.

    Parameters
    ----------
    native_sbom
        Original file before one actual filesystem or encoding change.
    run_tool
        Real CLI subprocess runner.
    damage
        Input failure exercised at the public boundary.
    """
    native_sbom.unlink()
    if damage == "symlink":
        native_sbom.symlink_to(native_sbom.parent / "cargo-metadata.json")
    elif damage == "fifo":
        os.mkfifo(native_sbom)
    elif damage == "oversize":
        native_sbom.write_bytes(b" " * 262145)
    elif damage == "json":
        native_sbom.write_bytes(b"{")
    elif damage == "unicode":
        native_sbom.write_bytes(b"\xff")
    result = run_tool("check_native_analysis_sbom", str(native_sbom))
    assert result.returncode == 1
    assert result.stdout == (
        "native-analysis-sbom: FAIL SBOM inputs or Cargo metadata are unavailable or invalid\n"
    )
    assert result.stderr == ""


@pytest.mark.parametrize("damage", ["source", "manifest", "cargo"])
def test_actual_source_or_metadata_failure_refuses(
    native_sbom: Path,
    analysis_package: Path,
    monkeypatch: pytest.MonkeyPatch,
    damage: str,
) -> None:
    """Require source correspondence and a successful actual offline Cargo invocation.

    Parameters
    ----------
    native_sbom
        Unmodified actual inventory.
    analysis_package
        Isolated complete original analysis package and canonical owner copies.
    monkeypatch
        Environment override for the actual missing-executable case only.
    damage
        Source drift, malformed manifest or genuinely unavailable Cargo.
    """
    if damage == "source":
        path = analysis_package / "analysis/rust/neural-step-run.schema.json"
        path.write_bytes(path.read_bytes() + b"\n")
    elif damage == "manifest":
        (analysis_package / "analysis/rust/Cargo.toml").write_bytes(b"[")
    else:
        monkeypatch.setenv("PATH", str(analysis_package / "absent-bin"))
    findings = audit(analysis_package, native_sbom)
    assert findings
    assert findings == [
        "analysis package source or reviewed licence bindings differ"
        if damage == "source"
        else "SBOM inputs or Cargo metadata are unavailable or invalid"
    ]
