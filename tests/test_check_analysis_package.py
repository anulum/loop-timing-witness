# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — public native analysis package correspondence controls

"""Exercise original package assets and Cargo licence drift through the real CLI."""

from __future__ import annotations

import json
import os
import shutil
from typing import TYPE_CHECKING

import pytest

from check_analysis_package import main
from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import RunTool

_WORKERS = ("__init__.py", "neural_checker_worker.py", "neural_checker_isolation.py")
_ASSETS = (
    "neural-selected-source-contract.json",
    "neural-selected-checker-policy.json",
    "neural-selected-checker-runtime.json",
    "neural-image-source-contract.json",
    "neural-image-checker-policy.json",
    "neural-image-checker-runtime.json",
)
_COPIED = (
    *(f"checker_worker/loop_timing_witness/{name}" for name in _WORKERS),
    *(f"public-data/{name}" for name in _ASSETS),
    "neural-step-run.schema.json",
    "tests/data/neural-selected-original.run.json",
)


@pytest.fixture
def analysis_package(tmp_path: Path) -> Path:
    """Copy the complete actual crate and its canonical source owners.

    Parameters
    ----------
    tmp_path
        Owned package candidate containing real source and licence records.

    Returns
    -------
    Path
        Original repository layout for the public package-audit command.
    """
    shutil.copytree(REPOSITORY_ROOT / "analysis/rust", tmp_path / "analysis/rust")
    owners = (
        *(f"src/loop_timing_witness/{name}" for name in _WORKERS),
        *(f"src/loop_timing_witness/data/{name}" for name in _ASSETS),
        "neural-step-run.schema.json",
        "tests/data/neural-selected-original.run.json",
    )
    for name in owners:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / name, path)
    return tmp_path


def test_original_analysis_package_passes_public_function_and_cli(
    analysis_package: Path, run_tool: RunTool, capsys: pytest.CaptureFixture[str]
) -> None:
    """Admit the same complete shipped source and reviewed Cargo population.

    Parameters
    ----------
    analysis_package
        Actual package and exact original owner bodies.
    run_tool
        Runner for the maintained command.
    capsys
        Original public function diagnostic capture.
    """
    assert main(["--root", str(analysis_package)]) == 0
    assert capsys.readouterr().out == "analysis-package: PASS\n"
    result = run_tool("check_analysis_package", "--root", str(analysis_package))
    assert result.returncode == 0
    assert result.stdout == "analysis-package: PASS\n"
    assert result.stderr == ""


@pytest.mark.parametrize("relative", _COPIED)
def test_changed_packaged_body_refuses_without_changing_its_owner(
    analysis_package: Path, run_tool: RunTool, relative: str
) -> None:
    """Refuse independent drift of every exact packaged worker or data role.

    Parameters
    ----------
    analysis_package
        Complete original candidate.
    run_tool
        Actual public command runner.
    relative
        One original packaged role whose full bytes are changed.
    """
    path = analysis_package / "analysis/rust" / relative
    original = path.read_bytes()
    path.write_bytes(original + b"\n")
    result = run_tool("check_analysis_package", "--root", str(analysis_package))
    assert result.returncode == 1
    assert "bytes differ from the canonical owner" in result.stdout
    assert relative in result.stdout
    assert result.stderr == ""


@pytest.mark.parametrize(
    "damage",
    [
        "unknown-fields",
        "schema",
        "packages-type",
        "missing-package",
        "extra-package",
        "checksum",
        "entry-fields",
        "licence",
        "licence-type",
    ],
)
def test_original_cargo_licence_and_complete_notices_drift_refuses(
    analysis_package: Path, run_tool: RunTool, damage: str
) -> None:
    """Keep the exact archive review and complete licence text mandatory.

    Parameters
    ----------
    analysis_package
        Original complete Cargo lock, licence record and notice bodies.
    run_tool
        Actual public command runner.
    damage
        Concrete record, Cargo or notice contradiction.
    """
    crate = analysis_package / "analysis/rust"
    path = crate / "dependency-licences.json"
    policy = json.loads(path.read_bytes())
    entry = policy["packages"]["serde@1.0.228"]
    if damage == "unknown-fields":
        policy["extra"] = 1
    elif damage == "schema":
        policy["schema_id"] = "unsupported"
    elif damage == "packages-type":
        policy["packages"] = []
    elif damage == "missing-package":
        del policy["packages"]["serde@1.0.228"]
    elif damage == "extra-package":
        policy["packages"]["unknown@1.0.0"] = dict(entry)
    elif damage == "checksum":
        entry["checksum"] = "0" * 64
    elif damage == "entry-fields":
        entry["extra"] = 1
    elif damage == "licence":
        entry["licence"] = "unsupported"
    else:
        entry["licence"] = []
    path.write_text(json.dumps(policy), encoding="utf-8")
    result = run_tool("check_analysis_package", "--root", str(analysis_package))
    assert result.returncode == 1
    assert result.stdout.startswith("analysis-package: FAIL")
    assert result.stderr == ""


def test_incomplete_third_party_notice_text_refuses(
    analysis_package: Path, run_tool: RunTool
) -> None:
    """Bind the entire original dependency notice body, including its final byte.

    Parameters
    ----------
    analysis_package
        Original reviewed crate.
    run_tool
        Actual public package command.
    """
    path = analysis_package / "analysis/rust/THIRD_PARTY_NOTICES.md"
    path.write_bytes(path.read_bytes()[:-1])
    result = run_tool("check_analysis_package", "--root", str(analysis_package))
    assert result.returncode == 1
    assert "notices differ from the reviewed complete text" in result.stdout
    assert result.stderr == ""


@pytest.mark.parametrize("damage", ["json", "toml", "unicode", "missing", "entry-type"])
def test_unreadable_or_malformed_actual_package_metadata_is_authored(
    analysis_package: Path, run_tool: RunTool, damage: str
) -> None:
    """Refuse real missing, malformed or incorrectly typed source metadata.

    Parameters
    ----------
    analysis_package
        Actual package tree containing original metadata.
    run_tool
        Production package command runner.
    damage
        Concrete file-kind, encoding, grammar or record-type error.
    """
    crate = analysis_package / "analysis/rust"
    path = crate / "dependency-licences.json"
    if damage == "json":
        path.write_bytes(b'{"schema_id":')
    elif damage == "toml":
        (crate / "Cargo.lock").write_bytes(b"malformed = [")
    elif damage == "unicode":
        (crate / "Cargo.lock").write_bytes(b"\xff")
    elif damage == "missing":
        path.unlink()
    else:
        policy = json.loads(path.read_bytes())
        policy["packages"]["serde@1.0.228"] = []
        path.write_text(json.dumps(policy), encoding="utf-8")
    result = run_tool("check_analysis_package", "--root", str(analysis_package))
    assert result.returncode == 1
    assert result.stdout.startswith("analysis-package: FAIL")
    assert result.stderr == ""


@pytest.mark.parametrize("kind", ["missing", "directory", "symlink", "fifo", "oversized"])
def test_actual_package_file_kind_and_size_refusals_are_finite(
    analysis_package: Path, run_tool: RunTool, kind: str
) -> None:
    """Reject actual nonregular or excessive worker bytes without a FIFO writer.

    Parameters
    ----------
    analysis_package
        Real copied package whose canonical owner remains intact.
    run_tool
        Actual public command runner.
    kind
        Real package file-kind or finite-size contradiction.
    """
    worker = analysis_package / "analysis/rust/checker_worker/loop_timing_witness/__init__.py"
    raw = worker.read_bytes()
    worker.unlink()
    if kind == "directory":
        worker.mkdir()
    elif kind == "symlink":
        replacement = analysis_package / "original-worker.py"
        replacement.write_bytes(raw)
        worker.symlink_to(replacement)
    elif kind == "fifo":
        os.mkfifo(worker)
    elif kind == "oversized":
        worker.write_bytes(b" " * 262145)
    result = run_tool("check_analysis_package", "--root", str(analysis_package))
    assert result.returncode == 1
    assert "missing or invalid" in result.stdout
    assert result.stderr == ""


def test_repeated_original_cargo_archive_identity_refuses(
    analysis_package: Path, run_tool: RunTool
) -> None:
    """Reject repeated registry records even when their name and checksum agree.

    Parameters
    ----------
    analysis_package
        Original lock and reviewed package records.
    run_tool
        Actual package command runner.
    """
    crate = analysis_package / "analysis/rust"
    policy = json.loads((crate / "dependency-licences.json").read_bytes())
    checksum = policy["packages"]["serde@1.0.228"]["checksum"]
    with (crate / "Cargo.lock").open("a", encoding="utf-8") as stream:
        stream.write(
            '\n[[package]]\nname = "serde"\nversion = "1.0.228"\n'
            'source = "registry+https://github.com/rust-lang/crates.io-index"\n'
            f'checksum = "{checksum}"\n'
        )
    result = run_tool("check_analysis_package", "--root", str(analysis_package))
    assert result.returncode == 1
    assert "repeated review identities" in result.stdout
    assert result.stderr == ""
