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
from pathlib import Path

import pytest
from amp_image_dependencies import snapshot_image_dependencies
from amp_image_options import verification_arguments
from prepare_amp_image import main as prepare_main
from test_amp_spike_command import REQUEST
from verify_amp_image import verify_image
from verify_amp_preparation import main as preparation_main

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
    if compiled:
        result = subprocess.run(
            ["make", "-C", str(original_preparation), "-j2"],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        manifest = json.loads((original_preparation / "image.json").read_bytes())
        assert manifest["compiler_dependencies"] == data["compiler_dependencies"]


@pytest.mark.parametrize(
    "fault", ["record", "dependencies", "index", "source", "escape", "identity", "relative"]
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
    index_path = original_preparation / "compiler_source_index.json"
    index = json.loads(index_path.read_bytes())
    name, item = next(iter(index.items()))
    changed = original_preparation / item["path"]
    finding = "dependency"
    if fault == "record":
        changed = original_preparation / "precompile/input_0.d"
        with changed.open("ab") as stream:
            stream.write(b"\n")
        data["inputs"][str(changed.relative_to(original_preparation))] = sha256_of_file(changed)
        finding = "preprocessing records changed"
    elif fault == "dependencies":
        removed = next(reversed(index))
        data["compiler_dependencies"].pop(removed)
        index.pop(removed)
        index_path.write_bytes(canonical_json_bytes(index))
        data["inputs"]["compiler_source_index.json"] = sha256_of_file(index_path)
        finding = "preprocessing dependencies changed"
    elif fault == "index":
        index.pop(name)
        index_path.write_bytes(canonical_json_bytes(index))
        data["inputs"]["compiler_source_index.json"] = sha256_of_file(index_path)
        finding = "snapshot index disagrees"
    elif fault == "source":
        with changed.open("ab") as stream:
            stream.write(b"changed captured real header")
        data["inputs"][str(changed.relative_to(original_preparation))] = sha256_of_file(changed)
        finding = "dependency bytes or paths changed"
    elif fault == "escape":
        changed.unlink()
        original = Path(name) if Path(name).is_absolute() else original_preparation / name
        changed.symlink_to(original)
        finding = "source/input bytes or paths changed"
    elif fault == "identity":
        data["compiler_dependencies"] = []
        finding = "dependency identities are invalid"
    else:
        data["compiler_dependencies"]["source/../contract.c"] = data["compiler_dependencies"][
            "contract.c"
        ]
        finding = "dependency paths escape"
    receipt.write_bytes(canonical_json_bytes(data))
    result = subprocess.run(
        ["make", "-C", str(original_preparation), "-j2"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode != 0
    assert finding in result.stderr
    assert not tuple(original_preparation.rglob("*.o"))
    assert not (original_preparation / "firmware.elf").exists()
    assert not (original_preparation / "image.json").exists()


def test_actual_late_compiler_dependency_refused(original_preparation: Path) -> None:
    """Refuse an actual post-compilation dependency absent from the original preprocessor closure.

    Parameters
    ----------
    original_preparation
        Actual prepared firmware compiled by its public Make target.
    """
    result = subprocess.run(
        ["make", "-C", str(original_preparation), "-j2"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads((original_preparation / "preparation.json").read_bytes())
    header = original_preparation / "additional_original_header.h"
    shutil.copyfile(ROOT / "controllers/c/witness_controller.h", header)
    commands = json.loads((original_preparation / "build_commands.json").read_bytes())
    command = commands["compile"][3]
    actual = [command[0], "-include", str(header), *command[1:]]
    result = subprocess.run(
        actual, cwd=original_preparation, capture_output=True, text=True, check=False, timeout=30
    )
    assert result.returncode == 0, result.stderr
    linked = subprocess.run(
        commands["link"],
        cwd=original_preparation,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert linked.returncode == 0, linked.stderr
    with pytest.raises(ValueError, match="differ from original preprocessing"):
        verify_image(
            original_preparation,
            original_preparation / "platform.dtb",
            original_preparation / "configuration.txt",
            REQUEST,
        )
    assert (
        data["compiler_dependencies"]
        == json.loads((original_preparation / "preparation.json").read_bytes())[
            "compiler_dependencies"
        ]
    )


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
