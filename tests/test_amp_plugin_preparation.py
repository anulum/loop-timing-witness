# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — real original generation and preprocessor custody

"""Exercise real public preparation and refuse changed original or generated build inputs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from amp_build_dependencies import dependency_hashes
from amp_build_toolchain import compiler_identity
from amp_plugin_inputs import ROOT, PluginBuild
from amp_plugin_preparation import freeze_plugin, main, verified_preparation
from amp_tool_runtime import elf_interpreter
from test_write_amp_plugin_manifest import original_plugin

from manifest_io import sha256_of_file

__all__ = ["original_plugin"]


@pytest.fixture
def prepared_plugin(original_plugin: PluginBuild, tmp_path: Path) -> PluginBuild:
    """Generate actual RTL and all compiler dependency records without compiling objects.

    Parameters
    ----------
    original_plugin
        Actual original SDK and native tool selections.
    tmp_path
        Owned exclusive preparation output.

    Returns
    -------
    PluginBuild
        Original public Make preparation with complete actual preprocessor closure.
    """
    directory = tmp_path / "prepared"
    result = subprocess.run(
        [
            "make",
            "amp-spike-plugin-prepare",
            "AMP_SPIKE_SOURCE=" + str(original_plugin.source),
            "AMP_SPIKE_BUILD=" + str(original_plugin.sdk),
            "AMP_PLUGIN_DIRECTORY=" + str(directory),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    (tmp_path / "preparation.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    return replace(original_plugin, directory=directory)


def test_actual_original_preparation(prepared_plugin: PluginBuild) -> None:
    """Require original generation and actual native/model preprocessor dependencies.

    Parameters
    ----------
    prepared_plugin
        Genuine public prepared generation and compiler-derived dependency records.
    """
    dependencies = dependency_hashes(
        tuple((prepared_plugin.directory / "precompile").glob("*.d")), ROOT
    )
    data = verified_preparation(prepared_plugin, dependencies)
    assert data["stage"] == "compilation"
    assert any(name.endswith("stdint.h") for name in data["dependencies"])
    assert any(name.endswith("sim.h") for name in data["dependencies"])
    assert not tuple(prepared_plugin.directory.rglob("*.o"))
    with pytest.raises(FileExistsError):
        freeze_plugin(prepared_plugin, "generation")


@pytest.mark.parametrize(
    "fault",
    [
        "generation",
        "generation-bytes",
        "preparation",
        "record",
        "generated",
        "dependencies",
        "post-dependencies",
    ],
)
def test_real_preparation_drift(prepared_plugin: PluginBuild, fault: str) -> None:
    """Refuse actual retained receipt, compiler-record or generated-source drift.

    Parameters
    ----------
    prepared_plugin
        Complete owned actual preparation.
    fault
        Original or generated input whose bytes or original identity change.
    """
    directory = prepared_plugin.directory
    dependencies = dependency_hashes(tuple((directory / "precompile").glob("*.d")), ROOT)
    receipt = directory / "compilation.json"
    data = json.loads(receipt.read_bytes())
    finding = "preparation or original"
    if fault == "generation":
        generation = directory / "generation.json"
        original = json.loads(generation.read_bytes())
        original["identity"]["thermal"] = 1
        generation.write_text(json.dumps(original), encoding="ascii")
        with pytest.raises(ValueError, match="generation inputs changed"):
            freeze_plugin(prepared_plugin, "compilation")
    elif fault == "generation-bytes":
        with (directory / "generation.json").open("ab") as stream:
            stream.write(b"\n")
    elif fault == "preparation":
        data["schema"] = "wrong-original-schema"
        receipt.write_text(json.dumps(data), encoding="ascii")
        finding = "preparation invalid"
    elif fault == "record":
        with (directory / "precompile/plugin.d").open("ab") as stream:
            stream.write(b"\n")
        finding = "dependency record changed"
    elif fault == "generated":
        with (directory / "rtl/Vaxi_control_witness__ALL.cpp").open("ab") as stream:
            stream.write(b"\n// changed actual generated source\n")
        finding = "generated build input changed"
    elif fault == "dependencies":
        data["dependencies"].pop(next(iter(data["dependencies"])))
        receipt.write_text(json.dumps(data), encoding="ascii")
        finding = "dependency changed"
    else:
        dependencies.pop(next(iter(dependencies)))
        finding = "dependency changed"
    with pytest.raises(ValueError, match=finding):
        verified_preparation(prepared_plugin, dependencies)


def test_late_preparation_refused(original_plugin: PluginBuild) -> None:
    """Refuse manufacturing an original preparation after actual compilation has occurred.

    Parameters
    ----------
    original_plugin
        Actual already compiled native/plugin output.
    """
    with pytest.raises(ValueError, match="must precede compilation"):
        freeze_plugin(original_plugin, "generation")
    with pytest.raises(ValueError, match="stage must"):
        freeze_plugin(original_plugin, "invalid-stage")


@pytest.mark.parametrize("override", ["VERILATOR_ROOT", "VERILATOR_BIN"])
def test_public_backend_override_refused(
    original_plugin: PluginBuild, tmp_path: Path, override: str
) -> None:
    """Refuse ambient backend substitutions through actual standalone preparation.

    Parameters
    ----------
    original_plugin
        Actual SDK selections.
    tmp_path
        Owned otherwise valid generation output.
    override
        Environment field which would change the actual wrapper's backend choice.
    """
    output = tmp_path / "override"
    output.mkdir()
    environment = os.environ.copy()
    environment[override] = "/usr/share/verilator" if override.endswith("ROOT") else "verilator_bin"
    result = subprocess.run(
        [
            sys.executable,
            "tools/amp_plugin_preparation.py",
            "--stage",
            "generation",
            "--directory",
            str(output),
            "--source",
            str(original_plugin.source),
            "--sdk",
            str(original_plugin.sdk),
            "--cc",
            "gcc",
            "--cxx",
            "g++",
            "--thermal",
            "0",
            "--fifo-address-bits",
            "8",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 1
    assert "environment overrides" in result.stderr
    assert not (output / "generation.json").exists()


def test_public_late_preparation_refused(original_plugin: PluginBuild) -> None:
    """Return a retained public CLI refusal for a real already compiled output.

    Parameters
    ----------
    original_plugin
        Actual native build to preserve unchanged.
    """
    assert (
        main(
            [
                "--stage",
                "generation",
                "--directory",
                str(original_plugin.directory),
                "--source",
                str(original_plugin.source),
                "--sdk",
                str(original_plugin.sdk),
                "--cc",
                "gcc",
                "--cxx",
                "g++",
                "--thermal",
                "0",
                "--fifo-address-bits",
                "8",
            ]
        )
        == 1
    )


@pytest.mark.parametrize("fault", ["record", "hidden", "nested", "symlink", "runtime"])
def test_public_make_preserves_existing_inputs(
    original_plugin: PluginBuild, tmp_path: Path, fault: str
) -> None:
    """Reject unknown build contents or a foreign runtime before overwriting actual evidence.

    Parameters
    ----------
    original_plugin
        Actual compiler record and original SDK to preserve.
    tmp_path
        Exclusive owned directory for the refusal exercise.
    fault
        Existing record, hidden file, nested data, directory alias or foreign runtime.
    """
    output = tmp_path / "output"
    actual = tmp_path / "actual" if fault == "symlink" else output
    actual.mkdir()
    if fault == "symlink":
        output.symlink_to(actual, target_is_directory=True)
    if fault != "runtime":
        marker = actual / (".original.d" if fault == "hidden" else "controller.d")
        if fault == "nested":
            (actual / "prior").mkdir()
            marker = actual / "prior/controller.d"
        shutil.copyfile(original_plugin.directory / "controller.d", marker)
    before = {
        path.relative_to(actual).as_posix(): sha256_of_file(path)
        for path in actual.rglob("*")
        if path.is_file()
    }
    command = [
        "make",
        "amp-spike-plugin",
        "AMP_SPIKE_SOURCE=" + str(original_plugin.source),
        "AMP_SPIKE_BUILD=" + str(original_plugin.sdk),
        "AMP_PLUGIN_DIRECTORY=" + str(output),
    ]
    if fault == "runtime":
        command.append("AMP_VERILATOR_ROOT=" + str(original_plugin.sdk))
    result = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False
    )
    assert result.returncode != 0
    finding = (
        "runtime root differs"
        if fault == "runtime"
        else ("symbolic link" if fault == "symlink" else "empty output directory")
    )
    assert finding in result.stderr
    assert before == {
        path.relative_to(actual).as_posix(): sha256_of_file(path)
        for path in actual.rglob("*")
        if path.is_file()
    }
    assert not (actual / "generation.json").exists()
    assert not (actual / "rtl").exists()


def test_real_loaded_library_drift(
    original_plugin: PluginBuild, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject a changed actual compiler library through the standalone receipt entry point.

    Parameters
    ----------
    original_plugin
        Original SDK and compiler selections used by the real public build.
    tmp_path
        Owned output and actual shared library copy, preserving the system installation.
    monkeypatch
        Select only the owned real library through the actual loader environment.
    """
    frontend = Path(compiler_identity("gcc", "cc1")["programs"]["cc1"]["path"])
    listing = subprocess.check_output(
        [str(elf_interpreter(frontend)), "--list", str(frontend)], text=True, timeout=10
    )
    record = next(line for line in listing.splitlines() if "=>" in line)
    name, target = record.split("=>", 1)
    source = Path(target.strip().rsplit(" (", 1)[0])
    libraries = tmp_path / "libraries"
    libraries.mkdir()
    selected = libraries / name.strip()
    shutil.copyfile(source, selected)
    monkeypatch.setenv(
        "LD_LIBRARY_PATH", str(libraries) + ":" + os.environ.get("LD_LIBRARY_PATH", "")
    )
    directory = tmp_path / "prepared"
    result = subprocess.run(
        [
            "make",
            "amp-spike-plugin-prepare",
            "AMP_SPIKE_SOURCE=" + str(original_plugin.source),
            "AMP_SPIKE_BUILD=" + str(original_plugin.sdk),
            "AMP_PLUGIN_DIRECTORY=" + str(directory),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    (tmp_path / "library-preparation.log").write_text(
        result.stdout + result.stderr, encoding="utf-8"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    original = json.loads((directory / "compilation.json").read_bytes())
    assert original["identity"]["runtime_libraries"][str(selected)] == sha256_of_file(selected)
    before = sha256_of_file(directory / "compilation.json")
    with selected.open("ab") as stream:
        stream.write(b"changed owned original library\n")
    assert (
        main(
            [
                "--stage",
                "compilation",
                "--directory",
                str(directory),
                "--source",
                str(original_plugin.source),
                "--sdk",
                str(original_plugin.sdk),
                "--cc",
                "gcc",
                "--cxx",
                "g++",
                "--thermal",
                "0",
                "--fifo-address-bits",
                "8",
            ]
        )
        == 1
    )
    assert sha256_of_file(directory / "compilation.json") == before
    assert not tuple(directory.rglob("*.o"))
