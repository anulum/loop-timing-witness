# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual ISA receipt custody and public run manifest regression

"""Export and corrupt actual production-RTL captures through their public manifest boundary."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from amp_simulation_manifest import admitted_capture, write_amp_manifest
from capture_amp_simulation import main as capture_main
from run_manifest import load_run
from test_capture_amp_simulation import ROOT, capture_arguments

from manifest_io import sha256_of_file

__all__ = ["capture_arguments"]


@pytest.fixture
def actual_capture(capture_arguments: list[str]) -> Path:
    """Execute a real prepared RV64 image and retain its complete public capture.

    Parameters
    ----------
    capture_arguments
        Actual source-bound image, Spike and production AXI plugin.

    Returns
    -------
    Path
        Complete real original run directory with schema-valid capture and report artifacts.
    """
    assert capture_main(capture_arguments) == 0
    return Path(capture_arguments[capture_arguments.index("--output") + 1])


def test_real_manifest_export(actual_capture: Path) -> None:
    """Re-export observed data without converting missing physical evidence into a measurement.

    Parameters
    ----------
    actual_capture
        Original complete actual capture.
    """
    (actual_capture / "manifest.json").unlink()
    (actual_capture / "tracking.csv").unlink()
    manifest = write_amp_manifest(actual_capture)
    inputs = load_run(manifest)
    assert inputs.manifest["placement"] == "bare_metal_amp"
    assert inputs.manifest["source"]["kind"] == "rtl_simulation"
    assert inputs.manifest["tracking_sampling"] == "observed"
    assert inputs.manifest["hardware_artifacts"] is None
    assert inputs.manifest["plant"]["name"] == "second_order_mechanical"
    assert "amp_capture" in inputs.files
    assert len(inputs.files["events"]) == 640


@pytest.mark.parametrize(
    "fault", ["schema", "missing-input", "escape", "changed-input", "completion", "tools", "image"]
)
def test_original_capture_refusal(actual_capture: Path, fault: str) -> None:
    """Refuse schema corruption, source escape, actual file mutation and contradictory counters.

    Parameters
    ----------
    actual_capture
        Original real complete capture.
    fault
        Specific mutated original receipt or artifact.
    """
    data = json.loads((actual_capture / "capture.json").read_bytes())
    if fault == "schema":
        data["simulation_only"] = False
        finding = "receipt invalid"
    elif fault == "missing-input":
        del data["files"]["events.bin"]
        finding = "required original"
    elif fault == "escape":
        data["files"]["image/../../events.bin"] = data["files"]["events.bin"]
        finding = "bytes or paths changed"
    elif fault == "changed-input":
        with (actual_capture / "tracking_raw.csv").open("ab") as stream:
            stream.write(b"changed original")
        finding = "bytes or paths changed"
    elif fault == "tools":
        data["tools"]["plugin"] = "0" * 64
        finding = "identities disagree"
    elif fault == "image":
        image_path = actual_capture / "image/image.json"
        image = json.loads(image_path.read_bytes())
        image["firmware_sha256"] = "0" * 64
        image_path.write_text(json.dumps(image), encoding="ascii")
        data["files"]["image/image.json"] = sha256_of_file(image_path)
        finding = "identities disagree"
    else:
        data["completion"]["misses"] = 1
        finding = "actual logger"
    with pytest.raises(ValueError, match=finding):
        admitted_capture(actual_capture, json.dumps(data).encode("ascii"))


def corrupt_actual_capture_source(actual_capture: Path, fault: str) -> Path:
    """Change one owned real capture artifact for original source custody refusal.

    Parameters
    ----------
    actual_capture
        Completed real target execution and original captured producer inputs.
    fault
        Specific compiler, runtime, native source or index artifact to corrupt.

    Returns
    -------
    Path
        Mutated owned captured artifact; installed originals remain intact.
    """
    index_path = actual_capture / "plugin_source_index.json"
    index = json.loads(index_path.read_bytes())
    if fault in {"firmware-preprocessing-record", "preparation-input"}:
        changed = actual_capture / (
            "image/precompile/input_0.d"
            if fault == "firmware-preprocessing-record"
            else "image/build_commands.json"
        )
        with changed.open("ab") as stream:
            stream.write(b"\n")
    elif fault in {"firmware-dependency-source", "firmware-dependency-index"}:
        directory = actual_capture / "image"
        dependency_path = directory / "compiler_source_index.json"
        dependencies = json.loads(dependency_path.read_bytes())
        if fault == "firmware-dependency-index":
            dependencies.pop(next(iter(dependencies)))
            dependency_path.write_text(json.dumps(dependencies), encoding="ascii")
            changed = dependency_path
        else:
            changed = directory / next(iter(dependencies.values()))["path"]
            with changed.open("ab") as stream:
                stream.write(b"changed original captured compiler header")
    elif fault == "index":
        index.pop(next(iter(index)))
        index_path.write_text(json.dumps(index), encoding="ascii")
        changed = index_path
    else:
        if fault in {"simulator-runtime-library", "image-runtime-library"}:
            directory = (
                actual_capture / "image" if fault == "image-runtime-library" else actual_capture
            )
            runtime_index = json.loads((directory / "runtime_source_index.json").read_bytes())
            item = next(iter(runtime_index.values()))
            item = {**item, "path": str((directory / item["path"]).relative_to(actual_capture))}
        elif fault == "runtime-library":
            plugin = json.loads((actual_capture / "plugin_build.json").read_bytes())
            name = next(iter(plugin["runtime_libraries"]))
            item = index[name]
        else:
            item = next(iter(index.values()))
        changed = actual_capture / item["path"]
        with changed.open("ab") as stream:
            stream.write(b"changed captured compiler input")
    return changed


@pytest.mark.parametrize(
    "fault",
    [
        "index",
        "source",
        "runtime-library",
        "simulator-runtime-library",
        "image-runtime-library",
        "firmware-dependency-source",
        "firmware-dependency-index",
        "firmware-preprocessing-record",
        "preparation-input",
    ],
)
def test_public_reanalysis_refuses_rehashed_plugin_source(actual_capture: Path, fault: str) -> None:
    """Refuse revised source custody despite recomputed outer capture and manifest hashes.

    Parameters
    ----------
    actual_capture
        Complete real ISA execution and captured original native build inputs.
    fault
        Captured source/library bytes or the original-to-captured source index to change.
    """
    changed = corrupt_actual_capture_source(actual_capture, fault)
    capture_path = actual_capture / "capture.json"
    capture = json.loads(capture_path.read_bytes())
    changed_names = {changed.relative_to(actual_capture).as_posix()}
    if next(iter(changed_names)).startswith("image/") and fault != "preparation-input":
        preparation_path = actual_capture / "image/preparation.json"
        preparation = json.loads(preparation_path.read_bytes())
        preparation["inputs"][changed.relative_to(actual_capture / "image").as_posix()] = (
            sha256_of_file(changed)
        )
        preparation_path.write_text(json.dumps(preparation), encoding="ascii")
        image_path = actual_capture / "image/image.json"
        image = json.loads(image_path.read_bytes())
        image["preparation_sha256"] = sha256_of_file(preparation_path)
        image_path.write_text(json.dumps(image), encoding="ascii")
        changed_names.update({"image/preparation.json", "image/image.json"})
    for name in changed_names:
        capture["files"][name] = sha256_of_file(actual_capture / name)
    capture_path.write_text(json.dumps(capture), encoding="ascii")
    manifest_path = actual_capture / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["amp_capture"]["sha256"] = sha256_of_file(capture_path)
    for reference in manifest["source"]["files"]:
        if reference["path"] in changed_names:
            reference["sha256"] = sha256_of_file(actual_capture / reference["path"])
    manifest_path.write_text(json.dumps(manifest), encoding="ascii")
    result = subprocess.run(
        [
            sys.executable,
            "tools/analyze_run.py",
            str(manifest_path),
            "--output-dir",
            str(actual_capture.parent / "refused-reanalysis"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 1
    finding = (
        "preprocessing record identities"
        if fault == "firmware-preprocessing-record"
        else "preparation input identities"
        if fault == "preparation-input"
        else "firmware dependency"
        if fault in {"firmware-dependency-source", "firmware-dependency-index"}
        else "runtime library"
        if fault in {"simulator-runtime-library", "image-runtime-library"}
        else "source"
    )
    assert finding in result.stderr
    assert not (actual_capture.parent / "refused-reanalysis/report.json").exists()


@pytest.mark.parametrize("fault", ["missing", "type", "partial"])
def test_public_reanalysis_refuses_incomplete_compiler_metadata(
    actual_capture: Path, fault: str
) -> None:
    """Refuse missing or incomplete compiler identities after every outer hash is recomputed.

    Parameters
    ----------
    actual_capture
        Complete actual public firmware/RTL capture preserved in exclusive test output.
    fault
        Missing identity, wrong type or a library-only metadata object.
    """
    preparation_path = actual_capture / "image/preparation.json"
    preparation = json.loads(preparation_path.read_bytes())
    image_path = actual_capture / "image/image.json"
    image = json.loads(image_path.read_bytes())
    if fault == "missing":
        preparation.pop("toolchain")
        image.pop("toolchain")
    else:
        value = (
            []
            if fault == "type"
            else {"runtime_libraries": preparation["toolchain"]["runtime_libraries"]}
        )
        preparation["toolchain"] = value
        image["toolchain"] = value
    preparation_path.write_text(json.dumps(preparation), encoding="ascii")
    image["preparation_sha256"] = sha256_of_file(preparation_path)
    image_path.write_text(json.dumps(image), encoding="ascii")
    capture_path = actual_capture / "capture.json"
    capture = json.loads(capture_path.read_bytes())
    changed = {"image/preparation.json", "image/image.json"}
    for name in changed:
        capture["files"][name] = sha256_of_file(actual_capture / name)
    capture_path.write_text(json.dumps(capture), encoding="ascii")
    manifest_path = actual_capture / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["amp_capture"]["sha256"] = sha256_of_file(capture_path)
    for reference in manifest["source"]["files"]:
        if reference["path"] in changed:
            reference["sha256"] = sha256_of_file(actual_capture / reference["path"])
    manifest_path.write_text(json.dumps(manifest), encoding="ascii")
    output = actual_capture.parent / "refused-compiler-reanalysis"
    result = subprocess.run(
        [sys.executable, "tools/analyze_run.py", str(manifest_path), "--output-dir", str(output)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 1
    assert "original compiler identity is invalid" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (output / "report.json").exists()
