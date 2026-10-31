# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — selected consumer package integrity through public analysis

"""Refuse damaged consumer assets before opening an actual acquisition's referents."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from neural_operator_support import adopt_operator_descriptors, measure_package_copy

_ROOT = Path(__file__).resolve().parents[1]
_ASSETS = (
    "neural-selected-source-contract.json",
    "neural-selected-checker-policy.json",
    "neural-selected-checker-runtime.json",
)
_IMAGE_ASSETS = (
    "neural-image-source-contract.json",
    "neural-image-checker-policy.json",
    "neural-image-checker-runtime.json",
)
_SELECTED = b"ec1236a69fc9e16a4eff1dfa7bdad8aa8b6088fc4ebceb8d8c43d33517199304"
_IMAGE = b"5ff959e55f59ca3b1d1993bbc2ed9028c49e08feb6ff15a0fd5af156959d5488"
_BOOTSTRAP = (
    "import sys;sys.path.insert(0,sys.argv.pop(1));"
    "from loop_timing_witness.analyze_run import main;raise SystemExit(main())"
)


def _analysis(package_root: Path, manifest: Path, output: Path) -> subprocess.CompletedProcess[str]:
    """Run the public command against an isolated, actual package copy.

    Parameters
    ----------
    package_root
        Source root containing the package whose installed assets are under test.
    manifest
        Exact recorded public acquisition declaration.
    output
        Exclusive destination that must remain absent on admission refusal.

    Returns
    -------
    subprocess.CompletedProcess[str]
        Original command status and complete diagnostic streams.
    """
    return subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            _BOOTSTRAP,
            str(package_root),
            str(manifest),
            "--output-dir",
            str(output),
        ],
        cwd=manifest.parent,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )


def _reviewed_initialiser() -> bytes:
    """Derive the package initialiser that the historical host runtime reviewed.

    It is the current initialiser without the later public campaign exports;
    the digest proves that nothing else differs.

    Returns
    -------
    bytes
        Exact reviewed initialiser bytes.
    """
    text = (_ROOT / "src/loop_timing_witness/__init__.py").read_text(encoding="utf-8")
    for line in (
        "    from .campaign_analysis import build_campaign_report\n",
        "    from .campaign_manifest import CampaignInputs, load_campaign\n",
        '    "CampaignInputs": ".campaign_manifest",\n',
        '    "build_campaign_report": ".campaign_analysis",\n',
        '    "load_campaign": ".campaign_manifest",\n',
    ):
        assert text.count(line) == 1
        text = text.replace(line, "")
    start = text.index("__all__ = [")
    end = text.index("]\n", start) + 1
    names = '"RunInputs", "build_neural_run_report", "build_report", "load_neural_run", "load_run"'
    raw = (text[:start] + f"__all__ = [{names}]" + text[end:]).encode()
    assert hashlib.sha256(raw).hexdigest() == (
        "6d6ff4fdd628f6f3f21c495b37dbfcb92d00b1404a8bf2610c0427bfd3bab5f2"
    )
    return raw


def _installation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Copy the real package and retain an exact original acquisition declaration.

    The copy adopts test operator descriptors; the real ones name host files.

    Parameters
    ----------
    tmp_path
        Owned isolated installation and recorded declaration allocation.
    monkeypatch
        Selects the operator descriptors for the command.

    Returns
    -------
    tuple[Path, Path]
        Complete package directory and exact public manifest; referenced run
        files are deliberately absent to distinguish admission from binding.
    """
    source = _ROOT / "src/loop_timing_witness"
    installed = tmp_path / "installation/loop_timing_witness"
    shutil.copytree(source, installed, ignore=shutil.ignore_patterns("__pycache__"))
    adopt_operator_descriptors(installed, tmp_path, monkeypatch)
    original = (_ROOT / "tests/data/neural-selected-original.run.json").read_bytes()
    assert (
        hashlib.sha256(original).hexdigest()
        == "3a982fb1aa66f64135ce622c68e408c6dcefb78022cc270f2ecc7fd047a3b075"
    )
    manifest = tmp_path / "run.json"
    manifest.write_bytes(original)
    return installed, manifest


@pytest.fixture
def selected_installation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Return a package copy measured by subprocess coverage.

    Parameters
    ----------
    tmp_path
        Owned isolated installation and recorded declaration allocation.
    monkeypatch
        Selects the operator descriptors and measures the copy.

    Returns
    -------
    tuple[Path, Path]
        Complete package directory and exact public manifest.
    """
    installed, manifest = _installation(tmp_path, monkeypatch)
    measure_package_copy(installed, monkeypatch)
    return installed, manifest


@pytest.fixture
def unmeasured_installation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Return a package copy whose worker files may become foreign links.

    Coverage reports a linked file at its target, so this copy stays unmeasured.

    Parameters
    ----------
    tmp_path
        Owned isolated installation and recorded declaration allocation.
    monkeypatch
        Selects the operator descriptors.

    Returns
    -------
    tuple[Path, Path]
        Complete package directory and exact public manifest.
    """
    return _installation(tmp_path, monkeypatch)


@pytest.mark.parametrize("asset", _ASSETS)
@pytest.mark.parametrize(
    "damage", ["missing", "directory", "symlink", "fifo", "changed", "oversized"]
)
def test_selected_asset_damage_refuses_the_actual_public_acquisition(
    tmp_path: Path, selected_installation: tuple[Path, Path], asset: str, damage: str
) -> None:
    """Keep every pinned consumer asset mandatory through the production CLI.

    Parameters
    ----------
    tmp_path
        Owned package installation and declaration allocation.
    selected_installation
        Real copied package and recorded acquisition declaration.
    asset
        One complete reviewed consumer role; no acquisition-supplied replacement.
    damage
        Actual filesystem or byte-integrity failure at that role.
    """
    installed, manifest = selected_installation
    target = installed / "data" / asset
    raw = target.read_bytes()
    target.unlink()
    if damage == "directory":
        target.mkdir()
    elif damage == "symlink":
        replacement = tmp_path / "replacement.json"
        replacement.write_bytes(raw)
        target.symlink_to(replacement)
    elif damage == "fifo":
        os.mkfifo(target)
    elif damage == "changed":
        target.write_bytes(raw + b" ")
    elif damage == "oversized":
        target.write_bytes(b" " * 262145)
    output = tmp_path / "report"
    result = _analysis(installed.parent, manifest, output)
    assert result.returncode == 1
    assert result.stdout == ""
    assert "Selected neural profile" in result.stderr
    assert "Traceback" not in result.stderr
    assert not output.exists()
    assert not list(tmp_path.glob(".report.*"))


@pytest.mark.parametrize(
    "registration",
    [
        ("LOOP_TIMING_WITNESS_CHECKER_INSTALLATION", "No reviewed checker installation descriptor"),
        ("LOOP_TIMING_WITNESS_CHECKER_IMAGE_BINDING", "No immutable checker image binding"),
    ],
)
@pytest.mark.parametrize(
    "damage", ["unset", "relative", "missing", "symlink", "fifo", "changed", "oversized"]
)
def test_operator_descriptor_must_be_selected_and_reviewed(
    tmp_path: Path,
    selected_installation: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    registration: tuple[str, str],
    damage: str,
) -> None:
    """Require an absolute, regular, reviewed operator descriptor for each registration.

    Parameters
    ----------
    tmp_path
        Owned descriptors and absent report destination.
    selected_installation
        Package copy with adopted descriptors and the original declaration.
    monkeypatch
        Changes the operator selection.
    registration
        Operator variable and its refusal when no absolute descriptor is selected.
    damage
        Selection or file contradiction.
    """
    installed, manifest = selected_installation
    variable, missing = registration
    if variable.endswith("IMAGE_BINDING"):
        _image_declaration(manifest)
        monkeypatch.setenv("LOOP_TIMING_WITNESS_CHECKER_IMAGE", str(tmp_path / "image"))
    else:
        (installed / "__init__.py").write_bytes(_reviewed_initialiser())
    target = Path(os.environ[variable])
    raw = target.read_bytes()
    if damage == "unset":
        monkeypatch.delenv(variable)
    elif damage == "relative":
        monkeypatch.setenv(variable, target.name)
    else:
        target.unlink()
    if damage == "symlink":
        replacement = tmp_path / "replacement.json"
        replacement.write_bytes(raw)
        target.symlink_to(replacement)
    elif damage == "fifo":
        os.mkfifo(target)
    elif damage == "changed":
        target.write_bytes(raw + b" ")
    elif damage == "oversized":
        target.write_bytes(b" " * 262145)
    output = tmp_path / "report"
    result = _analysis(installed.parent, manifest, output)
    assert result.returncode == 1
    assert result.stdout == ""
    expected = missing if damage in {"unset", "relative"} else "Selected neural profile"
    assert expected in result.stderr
    assert "Traceback" not in result.stderr
    assert not output.exists()


def _image_declaration(manifest: Path) -> None:
    """Point the recorded declaration at the image successor registration.

    Parameters
    ----------
    manifest
        Copied recorded declaration, rewritten in place.
    """
    raw = manifest.read_bytes()
    assert raw.count(_SELECTED) == 1
    manifest.write_bytes(raw.replace(_SELECTED, _IMAGE))


@pytest.mark.parametrize("asset", _IMAGE_ASSETS)
@pytest.mark.parametrize("damage", ["missing", "changed"])
def test_image_asset_damage_refuses_the_successor_registration(
    tmp_path: Path,
    selected_installation: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    asset: str,
    damage: str,
) -> None:
    """Keep every pinned image registration asset mandatory through the CLI.

    Parameters
    ----------
    tmp_path
        Owned absent report destination.
    selected_installation
        Real copied package and recorded acquisition declaration.
    monkeypatch
        Selects an absolute image directory for the command.
    asset
        One reviewed image registration role.
    damage
        Removal or byte change at that role.
    """
    installed, manifest = selected_installation
    _image_declaration(manifest)
    monkeypatch.setenv("LOOP_TIMING_WITNESS_CHECKER_IMAGE", str(tmp_path / "image"))
    target = installed / "data" / asset
    raw = target.read_bytes()
    target.unlink()
    if damage == "changed":
        target.write_bytes(raw + b" ")
    output = tmp_path / "report"
    result = _analysis(installed.parent, manifest, output)
    assert result.returncode == 1
    assert result.stdout == ""
    assert "Selected neural profile" in result.stderr
    assert "Traceback" not in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("selection", ["unset", "relative", "absolute"])
def test_image_registration_requires_operator_image_then_original_files(
    tmp_path: Path,
    selected_installation: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    selection: str,
) -> None:
    """Admit the successor key only with an operator image and the original files.

    Parameters
    ----------
    tmp_path
        Owned absent report destination.
    selected_installation
        Intact copied package and recorded declaration without referents.
    monkeypatch
        Controls the operator image selection.
    selection
        Absent, relative or absolute image directory.
    """
    installed, manifest = selected_installation
    _image_declaration(manifest)
    monkeypatch.delenv("LOOP_TIMING_WITNESS_CHECKER_IMAGE", raising=False)
    if selection == "relative":
        monkeypatch.setenv("LOOP_TIMING_WITNESS_CHECKER_IMAGE", "image")
    elif selection == "absolute":
        monkeypatch.setenv("LOOP_TIMING_WITNESS_CHECKER_IMAGE", str(tmp_path / "image"))
    output = tmp_path / "report"
    result = _analysis(installed.parent, manifest, output)
    assert result.returncode == 1
    assert result.stdout == ""
    expected = (
        "Cannot open original file without symlinks"
        if selection == "absolute"
        else "No immutable checker image is selected"
    )
    assert expected in result.stderr
    assert "Traceback" not in result.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    "worker", ["__init__.py", "neural_checker_worker.py", "neural_checker_isolation.py"]
)
def test_changed_consumer_worker_refuses_source_admission(
    tmp_path: Path, selected_installation: tuple[Path, Path], worker: str
) -> None:
    """Require the installed worker bodies selected by the runtime contract.

    Parameters
    ----------
    tmp_path
        Owned absent report destination.
    selected_installation
        Real copied package and recorded acquisition declaration.
    worker
        Actual consumer worker source whose complete bytes are changed.
    """
    installed, manifest = selected_installation
    path = installed / worker
    path.write_bytes(path.read_bytes() + b"\n")
    output = tmp_path / "report"
    result = _analysis(installed.parent, manifest, output)
    assert result.returncode == 1
    assert result.stdout == ""
    assert "Selected checker worker or installation differs" in result.stderr
    assert "Traceback" not in result.stderr
    assert not output.exists()


def test_host_registration_refuses_worker_sources_changed_after_review(
    tmp_path: Path, selected_installation: tuple[Path, Path]
) -> None:
    """Refuse the historical host entry because the package worker changed since review.

    The host runtime binds the reviewed 0.1.0 package initialiser; the public
    campaign API changed that file, and the entry is never repinned.

    Parameters
    ----------
    tmp_path
        Owned absent report destination.
    selected_installation
        Intact copied package and actual original declaration without referents.
    """
    installed, manifest = selected_installation
    output = tmp_path / "report"
    result = _analysis(installed.parent, manifest, output)
    assert result.returncode == 1
    assert result.stdout == ""
    assert "Selected checker worker or installation differs" in result.stderr
    assert "Cannot open original file without symlinks" not in result.stderr


def test_reviewed_package_admission_requires_original_acquisition_files(
    tmp_path: Path, selected_installation: tuple[Path, Path]
) -> None:
    """Admit the exact tuple with the reviewed worker while requiring the original files.

    Parameters
    ----------
    tmp_path
        Owned absent report destination.
    selected_installation
        Package copy given the reviewed initialiser, and the original declaration.
    """
    installed, manifest = selected_installation
    (installed / "__init__.py").write_bytes(_reviewed_initialiser())
    output = tmp_path / "report"
    result = _analysis(installed.parent, manifest, output)
    assert result.returncode == 1
    assert result.stdout == ""
    assert "Cannot open original file without symlinks" in result.stderr
    assert "Selected neural profile" not in result.stderr
    assert "Traceback" not in result.stderr
    assert not output.exists()
    assert "Traceback" not in result.stderr
    assert not output.exists()


def test_unsupported_source_identity_refuses_before_package_asset_access(
    tmp_path: Path, selected_installation: tuple[Path, Path]
) -> None:
    """Refuse a changed tuple even when the consumer installation is unavailable.

    Parameters
    ----------
    tmp_path
        Owned absent report destination.
    selected_installation
        Actual package and declaration used for this unsupported-key control.
    """
    installed, manifest = selected_installation
    raw = manifest.read_bytes()
    selected = b"ec1236a69fc9e16a4eff1dfa7bdad8aa8b6088fc4ebceb8d8c43d33517199304"
    assert raw.count(selected) == 1
    manifest.write_bytes(raw.replace(selected, b"0" * 64))
    for name in _ASSETS:
        (installed / "data" / name).unlink()
    output = tmp_path / "report"
    result = _analysis(installed.parent, manifest, output)
    assert result.returncode == 1
    assert result.stdout == ""
    assert "No reviewed source contract is admitted" in result.stderr
    assert "Selected neural profile" not in result.stderr
    assert "Traceback" not in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("worker", ["neural_checker_worker.py", "neural_checker_isolation.py"])
@pytest.mark.parametrize("kind", ["fifo", "symlink", "directory", "missing", "oversized"])
def test_actual_selected_worker_file_refusals_are_bounded(
    tmp_path: Path, unmeasured_installation: tuple[Path, Path], worker: str, kind: str
) -> None:
    """Refuse nonregular or excessive worker sources before any checker can start.

    Parameters
    ----------
    tmp_path
        Owned report destination and replacement file.
    unmeasured_installation
        Actual copied package and recorded selected public manifest.
    worker
        Installed source inspected while constructing the selected runtime.
    kind
        Actual worker filesystem or finite-size contradiction.
    """
    installed, manifest = unmeasured_installation
    path = installed / worker
    original = path.read_bytes()
    path.unlink()
    if kind == "fifo":
        os.mkfifo(path)
    elif kind == "symlink":
        target = tmp_path / "original-worker.py"
        target.write_bytes(original)
        path.symlink_to(target)
    elif kind == "directory":
        path.mkdir()
    elif kind == "oversized":
        path.write_bytes(b" " * 1048577)
    output = tmp_path / "report"
    result = _analysis(installed.parent, manifest, output)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("run analysis: FAIL:")
    expected = {
        "fifo": "Selected checker runtime requires a regular resolved file",
        "symlink": "Selected checker runtime file is unavailable",
        "directory": "Selected checker runtime file is unavailable",
        "missing": "Selected checker runtime file is unavailable",
        "oversized": "Selected checker worker source exceeds its allocation",
    }
    assert expected[kind] in result.stderr
    assert "Traceback" not in result.stderr
    assert not output.exists()
