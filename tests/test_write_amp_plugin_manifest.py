# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original ISA logger completion and corruption regression tests

"""Retain actual public Make plugin provenance and refuse incomplete original builds."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from amp_plugin_inputs import PluginBuild
from test_capture_amp_simulation import ROOT
from write_amp_plugin_manifest import main, write_plugin_manifest

from manifest_io import sha256_of_file


@pytest.fixture(scope="module")
def original_plugin(tmp_path_factory: pytest.TempPathFactory) -> PluginBuild:
    """Compile actual production RTL and native adapter against the real original Spike SDK.

    Parameters
    ----------
    tmp_path_factory
        Exclusive actual module build allocation.

    Returns
    -------
    PluginBuild
        Actual source, SDK and output selections used by the public Make build.
    """
    source = os.environ.get("WITNESS_SPIKE_SOURCE")
    sdk = os.environ.get("WITNESS_SPIKE_BUILD")
    assert source is not None
    assert sdk is not None
    output = tmp_path_factory.mktemp("original-plugin")
    result = subprocess.run(
        [
            "make",
            "amp-spike-plugin",
            "AMP_SPIKE_SOURCE=" + source,
            "AMP_SPIKE_BUILD=" + sdk,
            "AMP_PLUGIN_DIRECTORY=" + str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    (output / "build.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    return PluginBuild(output, Path(source), Path(sdk), "gcc", "g++", 0)


@pytest.fixture
def owned_plugin(original_plugin: PluginBuild, tmp_path: Path) -> PluginBuild:
    """Compile an independent real build for each corruption or original receipt re-export.

    Parameters
    ----------
    original_plugin
        Real module build, preserved intact.
    tmp_path
        Exclusive test-owned actual build.

    Returns
    -------
    PluginBuild
        Same original SDK/tool selections with independently compiled owned output.
    """
    output = tmp_path / "plugin"
    result = subprocess.run(
        [
            "make",
            "amp-spike-plugin",
            "AMP_SPIKE_SOURCE=" + str(original_plugin.source),
            "AMP_SPIKE_BUILD=" + str(original_plugin.sdk),
            "AMP_PLUGIN_DIRECTORY=" + str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    (tmp_path / "owned-build.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    (output / "plugin.json").unlink()
    return replace(original_plugin, directory=output)


def test_actual_plugin_receipt(owned_plugin: PluginBuild) -> None:
    """Require the complete original dependency, compiler and link closure from actual builds.

    Parameters
    ----------
    owned_plugin
        Original actual native build output copy.
    """
    path = write_plugin_manifest(owned_plugin)
    data = json.loads(path.read_bytes())
    assert data["plugin_sha256"] == sha256_of_file(owned_plugin.directory / "witness_spike_axi.so")
    assert data["simulation_only"] is True
    assert len(data["spike_sdk"]["revision"]) == 40
    assert len(data["link_inputs"]) == 6
    assert len(data["dependency_records"]) > 5
    assert any(name.endswith("sim.h") for name in data["dependencies"])
    assert any(name.endswith("stdint.h") for name in data["dependencies"])
    assert any(name.endswith("sampled_plant.sv") for name in data["dependencies"])
    assert set(data["compilers"]["c"]["programs"]) == {"cc1", "collect2", "as", "ld"}
    with pytest.raises(FileExistsError):
        write_plugin_manifest(owned_plugin)


@pytest.mark.parametrize("fault", ["thermal", "native-record", "model-record", "sdk", "library"])
def test_public_original_build_refusal(owned_plugin: PluginBuild, fault: str) -> None:
    """Refuse bad parameters or missing actual build artifacts through the public CLI.

    Parameters
    ----------
    owned_plugin
        Complete actual build copy.
    fault
        Specific corrupted original build selection or missing native artifact.
    """
    build = owned_plugin
    if fault == "thermal":
        build = replace(build, thermal=2)
    elif fault == "native-record":
        (build.directory / "plugin.d").unlink()
    elif fault == "model-record":
        for path in (build.directory / "rtl").glob("*.d"):
            path.unlink()
    elif fault == "sdk":
        build = replace(build, source=build.directory / "absent-original-sdk")
    else:
        (build.directory / "witness_spike_axi.so").unlink()
    assert (
        main(
            [
                "--directory",
                str(build.directory),
                "--source",
                str(build.source),
                "--sdk",
                str(build.sdk),
                "--cc",
                build.cc,
                "--cxx",
                build.cxx,
                "--thermal",
                str(build.thermal),
            ]
        )
        == 1
    )
    assert not (build.directory / "plugin.json").exists()


def test_real_public_receipt_process(owned_plugin: PluginBuild) -> None:
    """Execute the real standalone writer with all actual admitted build inputs.

    Parameters
    ----------
    owned_plugin
        Complete actual build outputs and source/SDK selections.
    """
    result = subprocess.run(
        [
            sys.executable,
            "tools/write_amp_plugin_manifest.py",
            "--directory",
            str(owned_plugin.directory),
            "--source",
            str(owned_plugin.source),
            "--sdk",
            str(owned_plugin.sdk),
            "--cc",
            "gcc",
            "--cxx",
            "g++",
            "--thermal",
            "0",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout
    assert (owned_plugin.directory / "plugin.json").exists()


def test_original_receipt_stops_rebuild(original_plugin: PluginBuild) -> None:
    """Refuse an existing actual receipt before touching any compiled output or source proof.

    Parameters
    ----------
    original_plugin
        Actual completed public module build.
    """
    original = {
        str(path): (sha256_of_file(path), path.stat().st_mtime_ns)
        for path in original_plugin.directory.rglob("*")
        if path.is_file()
    }
    result = subprocess.run(
        [
            "make",
            "amp-spike-plugin",
            "AMP_SPIKE_SOURCE=" + str(original_plugin.source),
            "AMP_SPIKE_BUILD=" + str(original_plugin.sdk),
            "AMP_PLUGIN_DIRECTORY=" + str(original_plugin.directory),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode != 0
    retained = {
        str(path): (sha256_of_file(path), path.stat().st_mtime_ns)
        for path in original_plugin.directory.rglob("*")
        if path.is_file()
    }
    assert original == retained
