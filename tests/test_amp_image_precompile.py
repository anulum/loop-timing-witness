# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual original preprocessing custody and public pre-compilation refusal

"""Exercise real firmware preparation, original GCC headers and public Make admission."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from amp_image_dependencies import snapshot_image_dependencies
from amp_image_options import verification_arguments
from prepare_amp_image import main as prepare_main
from test_amp_spike_command import REQUEST
from verify_amp_image import verify_image
from verify_amp_preparation import main as preparation_main

from loop_timing_witness.host_profile import build_jobs, scaled
from manifest_io import canonical_json_bytes, sha256_of_file

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def original_preparation(tmp_path: Path) -> Path:
    """Prepare real original inputs and all GCC dependencies without compiling objects.

    Parameters
    ----------
    tmp_path
        Exclusive original preparation output.

    Returns
    -------
    Path
        Public actual preparation with complete original preprocessor custody.
    """
    original = os.environ.get("WITNESS_AMP_IMAGE")
    compiler = os.environ.get("WITNESS_RV64_CC")
    assert original is not None
    assert compiler is not None
    source = Path(original)
    output = tmp_path / "image"
    args = verification_arguments(REQUEST)
    args[args.index("platform.dtb")] = str(source / "platform.dtb")
    args[args.index("configuration.txt")] = str(source / "configuration.txt")
    assert prepare_main([*args, "--output", str(output), "--compiler", compiler, "--isa"]) == 0
    return output


@pytest.mark.parametrize("compiled", [False, True])
def test_actual_original_preprocessing(original_preparation: Path, *, compiled: bool) -> None:
    """Require original dependency bytes and exact compile vectors before and after real Make.

    Parameters
    ----------
    original_preparation
        Actual new original image preparation.
    compiled
        Whether to compile all actual objects and reconcile their real GCC dependency records.
    """
    assert not tuple(original_preparation.rglob("*.o"))
    data = json.loads((original_preparation / "preparation.json").read_bytes())
    assert len(data["dependency_records"]) == 5
    assert any(name.endswith("stdint.h") for name in data["compiler_dependencies"])
    assert "contract.c" in data["compiler_dependencies"]
    commands = json.loads((original_preparation / "build_commands.json").read_bytes())
    assert len(commands["compile"]) == 5
    assert all("-ffreestanding" in command for command in commands["compile"])
    assert preparation_main(["--directory", str(original_preparation)]) == 0
    cli = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/verify_amp_preparation.py"),
            "--directory",
            str(original_preparation),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=scaled(30),
    )
    assert cli.returncode == 0, cli.stderr
    assert "AMP original preparation: PASS" in cli.stdout
    if compiled:
        result = subprocess.run(
            ["make", "-C", str(original_preparation), f"-j{build_jobs()}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=scaled(60),
        )
        assert result.returncode == 0, result.stdout + result.stderr
        manifest = json.loads((original_preparation / "image.json").read_bytes())
        assert manifest["compiler_dependencies"] == data["compiler_dependencies"]


@pytest.mark.parametrize(
    "fault",
    [
        "record",
        "dependencies",
        "index",
        "source",
        "escape",
        "identity",
        "relative",
    ],
)
def test_public_precompile_refusal(original_preparation: Path, fault: str) -> None:
    """Refuse changed original preprocessing inputs through actual Make before objects exist.

    Parameters
    ----------
    original_preparation
        Real original compiler preparation to preserve.
    fault
        Specific original receipt, source snapshot or path identity to corrupt.
    """
    receipt = original_preparation / "preparation.json"
    data = json.loads(receipt.read_bytes())
    finding = _damage_preparation(original_preparation, data, fault)
    receipt.write_bytes(canonical_json_bytes(data))
    assert preparation_main(["--directory", str(original_preparation)]) == 1
    result = subprocess.run(
        ["make", "-C", str(original_preparation), f"-j{build_jobs()}"],
        capture_output=True,
        text=True,
        check=False,
        timeout=scaled(60),
    )
    assert result.returncode != 0
    assert finding in result.stderr
    assert not tuple(original_preparation.rglob("*.o"))
    assert not (original_preparation / "firmware.elf").exists()
    assert not (original_preparation / "image.json").exists()


def _damage_preparation(directory: Path, data: dict[str, Any], fault: str) -> str:
    """Corrupt one preprocessing input, index entry or receipt identity.

    Parameters
    ----------
    directory
        Real original compiler preparation.
    data
        Its preparation receipt, changed in place.
    fault
        Specific corruption.

    Returns
    -------
    str
        Required refusal text.
    """
    if fault in {"record", "source", "escape"}:
        return _damage_input(directory, data, fault)
    if fault in {"dependencies", "index"}:
        return _damage_index(directory, data, fault)
    if fault == "identity":
        data["compiler_dependencies"] = []
        return "dependency identities are invalid"
    data["compiler_dependencies"]["source/../contract.c"] = data["compiler_dependencies"][
        "contract.c"
    ]
    return "dependency paths escape"


def _damage_input(directory: Path, data: dict[str, Any], fault: str) -> str:
    """Change a preprocessing record or captured source, or alias the source outside.

    Parameters
    ----------
    directory
        Real original compiler preparation.
    data
        Its preparation receipt, rebound to changed bytes.
    fault
        ``record``, ``source`` or ``escape``.

    Returns
    -------
    str
        Required refusal text.
    """
    name, item = next(
        iter(json.loads((directory / "compiler_source_index.json").read_bytes()).items())
    )
    changed = directory / item["path"]
    if fault == "escape":
        changed.unlink()
        changed.symlink_to(Path(name) if Path(name).is_absolute() else directory / name)
        return "source/input bytes or paths changed"
    if fault == "record":
        changed = directory / "precompile/input_0.d"
    with changed.open("ab") as stream:
        stream.write(b"\n" if fault == "record" else b"changed captured real header")
    data["inputs"][str(changed.relative_to(directory))] = sha256_of_file(changed)
    if fault == "record":
        return "preprocessing records changed"
    return "dependency bytes or paths changed"


def _damage_index(directory: Path, data: dict[str, Any], fault: str) -> str:
    """Remove one source from the snapshot index, alone or with its dependency identity.

    Parameters
    ----------
    directory
        Real original compiler preparation.
    data
        Its preparation receipt, rebound to the changed index.
    fault
        ``dependencies`` or ``index``.

    Returns
    -------
    str
        Required refusal text.
    """
    index_path = directory / "compiler_source_index.json"
    index = json.loads(index_path.read_bytes())
    if fault == "dependencies":
        removed = next(reversed(index))
        data["compiler_dependencies"].pop(removed)
        index.pop(removed)
    else:
        index.pop(next(iter(index)))
    index_path.write_bytes(canonical_json_bytes(index))
    data["inputs"]["compiler_source_index.json"] = sha256_of_file(index_path)
    if fault == "dependencies":
        return "preprocessing dependencies changed"
    return "snapshot index disagrees"


@pytest.mark.parametrize("backend", ["other", "rust"])
def test_unbound_arithmetic_backend_refused(original_preparation: Path, backend: str) -> None:
    """Refuse changing the backend without an original Rust preparation receipt.

    Parameters
    ----------
    original_preparation
        Actual C firmware preparation with complete compiler dependency identities.
    backend
        Unsupported backend or Rust without its required original preparation.
    """
    receipt = original_preparation / "preparation.json"
    data = json.loads(receipt.read_bytes())
    data["kernel_backend"] = backend
    receipt.write_bytes(canonical_json_bytes(data))
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/verify_amp_preparation.py"),
            "--directory",
            str(original_preparation),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=scaled(30),
    )
    assert result.returncode == 1
    assert "arithmetic backend or Rust preparation identity is invalid" in result.stderr
    assert not tuple(original_preparation.rglob("*.o"))


def test_actual_late_compiler_dependency_refused(original_preparation: Path) -> None:
    """Refuse an actual post-compilation dependency absent from the original preprocessor closure.

    Parameters
    ----------
    original_preparation
        Actual prepared firmware compiled by its public Make target.
    """
    result = subprocess.run(
        ["make", "-C", str(original_preparation), f"-j{build_jobs()}"],
        capture_output=True,
        text=True,
        check=False,
        timeout=scaled(60),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads((original_preparation / "preparation.json").read_bytes())
    header = original_preparation / "additional_original_header.h"
    shutil.copyfile(ROOT / "controllers/c/witness_controller.h", header)
    commands = json.loads((original_preparation / "build_commands.json").read_bytes())
    command = commands["compile"][3]
    actual = [command[0], "-include", str(header), *command[1:]]
    result = subprocess.run(
        actual,
        cwd=original_preparation,
        capture_output=True,
        text=True,
        check=False,
        timeout=scaled(30),
    )
    assert result.returncode == 0, result.stderr
    linked = subprocess.run(
        commands["link"],
        cwd=original_preparation,
        capture_output=True,
        text=True,
        check=False,
        timeout=scaled(30),
    )
    assert linked.returncode == 0, linked.stderr
    with pytest.raises(ValueError, match="differ from original preprocessing"):
        verify_image(
            original_preparation,
            original_preparation / "platform.dtb",
            original_preparation / "configuration.txt",
            REQUEST,
        )
    after = json.loads((original_preparation / "preparation.json").read_bytes())
    assert data["compiler_dependencies"] == after["compiler_dependencies"]


def test_real_original_header_drift_before_snapshot(original_preparation: Path) -> None:
    """Refuse an owned actual header whose bytes change after original hash admission.

    Parameters
    ----------
    original_preparation
        Real original preprocessing snapshot from the public producer.
    """
    data = json.loads((original_preparation / "preparation.json").read_bytes())
    source = next(name for name in data["compiler_dependencies"] if Path(name).is_absolute())
    header = original_preparation.parent / "owned_actual_header.h"
    shutil.copyfile(source, header)
    identities = {str(header): sha256_of_file(header)}
    with header.open("ab") as stream:
        stream.write(b"changed owned actual original header before copying")
    output = original_preparation.parent / "header-snapshot"
    output.mkdir()
    with pytest.raises(ValueError, match="changed during snapshot"):
        snapshot_image_dependencies(output, identities)
