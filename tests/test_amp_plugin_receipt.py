# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original ISA logger completion and corruption regression tests

"""Admit genuine native build receipts and reject changes to their original compiled closure."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from amp_plugin_receipt import admit_plugin
from test_write_amp_plugin_manifest import original_plugin, owned_plugin
from write_amp_plugin_manifest import write_plugin_manifest

from manifest_io import canonical_json_bytes, sha256_of_file

__all__ = ["original_plugin", "owned_plugin"]

if TYPE_CHECKING:
    from amp_plugin_inputs import PluginBuild


@pytest.fixture
def admitted_build(owned_plugin: PluginBuild) -> Path:
    """Export an actual compiled plugin receipt for an exclusive owned output copy.

    Parameters
    ----------
    owned_plugin
        Actual production RTL and native plugin build.

    Returns
    -------
    Path
        Original real library with its complete matching build receipt.
    """
    write_plugin_manifest(owned_plugin)
    return owned_plugin.directory / "witness_spike_axi.so"


def test_original_real_plugin_admission(admitted_build: Path) -> None:
    """Require original library, records, source/header and actual tool byte agreement.

    Parameters
    ----------
    admitted_build
        Original complete real build.
    """
    content, data = admit_plugin(admitted_build)
    assert content == admitted_build.with_name("plugin.json").read_bytes()
    assert data["thermal"] == 0
    assert data["simulation_only"] is True


@pytest.mark.parametrize(
    "fault", ["schema", "library", "source", "tool", "conflict", "omitted", "roles", "missing"]
)
def test_actual_build_drift_refused(admitted_build: Path, fault: str) -> None:
    """Refuse schema or dependency/library/tool corruption without editing shared original inputs.

    Parameters
    ----------
    admitted_build
        Actual private copied build.
    fault
        Specific original byte or declaration contradiction.
    """
    path = admitted_build.with_name("plugin.json")
    data = json.loads(path.read_bytes())
    if fault == "schema":
        data["thermal"] = 2
        finding = "receipt invalid"
    elif fault == "library":
        with admitted_build.open("ab") as stream:
            stream.write(b"changed original")
        finding = "library differs"
    elif fault == "source":
        source = next(
            Path(name)
            for name in data["dependencies"]
            if Path(name).is_relative_to(admitted_build.parent)
        )
        with source.open("ab") as stream:
            stream.write(b"changed original")
        finding = "input or tool changed"
    elif fault == "tool":
        data["verilator"]["sha256"] = "0" * 64
        finding = "preparation identities"
    elif fault == "conflict":
        source = next(iter(data["link_inputs"]))
        data["dependencies"][source] = "0" * 64
        finding = "conflicting original"
    elif fault == "omitted":
        header = admitted_build.parent / "additional_controller.h"
        root = Path(data["working_directory"])
        shutil.copyfile(root / "controllers/c/witness_controller.h", header)
        record = admitted_build.parent / "controller.d"
        result = subprocess.run(
            [
                data["compilers"]["c"]["driver"]["path"],
                "-O2",
                "-fPIC",
                "-M",
                "-include",
                str(header),
                "-MF",
                str(record),
                "controllers/c/witness_controller.c",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        data["dependency_records"][str(record)] = sha256_of_file(record)
        finding = "compiler-recorded dependencies"
    elif fault == "roles":
        removed = next(
            name for name in data["dependency_records"] if Path(name).name == "controller.d"
        )
        digest = data["dependency_records"].pop(removed)
        renamed = admitted_build.parent / "renamed-record.d"
        shutil.copyfile(removed, renamed)
        data["dependency_records"][str(renamed)] = digest
        finding = "build roles"
    else:
        path.unlink()
        with pytest.raises(FileNotFoundError):
            admit_plugin(admitted_build)
        return
    path.write_text(json.dumps(data), encoding="ascii")
    with pytest.raises(ValueError, match=finding):
        admit_plugin(admitted_build)


def test_original_runtime_library_omission(original_plugin: PluginBuild, tmp_path: Path) -> None:
    """Refuse omitted actual loaded libraries even when original source hashes are rewritten.

    Parameters
    ----------
    original_plugin
        Genuine original public build, retained unchanged.
    tmp_path
        Owned library and tampered original receipt copy used by actual admission.
    """
    library = tmp_path / "witness_spike_axi.so"
    shutil.copyfile(original_plugin.directory / library.name, library)
    data = json.loads((original_plugin.directory / "plugin.json").read_bytes())
    name = next(iter(data["runtime_libraries"]))
    data["preparation"]["identity"]["sources"].pop(name)
    data["dependencies"].pop(name)
    data["dependencies"][data["preparation_path"]] = hashlib.sha256(
        canonical_json_bytes(data["preparation"])
    ).hexdigest()
    library.with_name("plugin.json").write_bytes(canonical_json_bytes(data))
    with pytest.raises(ValueError, match="preparation identities"):
        admit_plugin(library)
