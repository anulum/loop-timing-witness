# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — installed Python artifacts and real RTL run analysis

"""Exercise built wheels and source archives from isolated, offline consumers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from loop_timing_witness import build_report, load_run
from loop_timing_witness.host_profile import scaled

if TYPE_CHECKING:
    from conftest import MakeRtlRun

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
# Programs run by an isolated interpreter: build both artifacts, rebuild the wheel, load
# altered input through the installed API, and analyse through the installed package.
BUILD_PROGRAM = (
    "import json,sys; from flit_core.buildapi import build_wheel,build_sdist; "
    "print(json.dumps([build_wheel(sys.argv[1]),build_sdist(sys.argv[1])]))"
)
REBUILD_PROGRAM = (
    "import sys; from flit_core.buildapi import build_wheel; print(build_wheel(sys.argv[1]))"
)
NONFINITE_PROGRAM = (
    "import sys\nfrom pathlib import Path\n"
    "from loop_timing_witness import load_run\n"
    "try:\n load_run(Path(sys.argv[1]))\n"
    "except ValueError as error:\n print(str(error))\n"
    "else:\n raise AssertionError('nonfinite input accepted')\n"
)
API_PROGRAM = (
    "import json,sys; from pathlib import Path; import loop_timing_witness as w; "
    "print(json.dumps({'origin':w.__file__,'prefix':sys.prefix,"
    "'report':w.build_report(w.load_run(Path(sys.argv[1])))[0]}))"
)
PROFILE_RESOURCES = frozenset(
    {
        "neural-selected-source-contract.json",
        "neural-selected-checker-policy.json",
        "neural-selected-checker-runtime.json",
        "neural-image-source-contract.json",
        "neural-image-checker-policy.json",
        "neural-image-checker-runtime.json",
    }
)


def _run(argv: list[str], cwd: Path, output: Path, name: str) -> subprocess.CompletedProcess[str]:
    """Execute a real package command with checkout injection removed and retain its evidence."""
    environment = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONHOME", "COVERAGE_PROCESS_START"):
        environment.pop(key, None)
    environment["PIP_CONFIG_FILE"] = os.devnull
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        timeout=scaled(120),
        check=False,
    )
    (output / f"{name}.argv.json").write_text(json.dumps(argv, indent=2) + "\n")
    (output / f"{name}.log").write_text(result.stdout + result.stderr)
    return result


@pytest.fixture
def built_distribution(tmp_path: Path, request: pytest.FixtureRequest) -> Path:
    """Build the direct wheel or rebuild it from its actual source archive.

    Parameters
    ----------
    tmp_path
        Exclusive archive, extraction and backend logs.
    request
        Parametrised artifact selection.

    Returns
    -------
    Path
        Built wheel whose resources match the current repository contracts.
    """
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    built = _run(
        [sys.executable, "-I", "-c", BUILD_PROGRAM, str(artifacts)], ROOT, tmp_path, "build"
    )
    assert built.returncode == 0, built.stdout + built.stderr
    wheel_name, source_name = json.loads(built.stdout.splitlines()[-1])
    assert isinstance(wheel_name, str)
    assert isinstance(source_name, str)
    wheel = artifacts / wheel_name
    if request.param == "sdist":
        wheel = _rebuilt_from_source(tmp_path, artifacts / source_name, wheel)
    _check_wheel_resources(wheel)
    return wheel


def _rebuilt_from_source(directory: Path, source: Path, wheel: Path) -> Path:
    """Rebuild the wheel from the unpacked source archive and require identical members.

    Parameters
    ----------
    directory
        Exclusive extraction, rebuild and log directory.
    source
        Built source archive.
    wheel
        Directly built wheel.

    Returns
    -------
    Path
        Wheel rebuilt from the source archive.
    """
    unpacked = directory / "unpacked"
    with tarfile.open(source) as archive:
        archive.extractall(unpacked, filter="data")
    rebuilt = directory / "rebuilt"
    rebuilt.mkdir()
    result = _run(
        [sys.executable, "-I", "-c", REBUILD_PROGRAM, str(rebuilt)],
        unpacked / f"loop_timing_witness-{VERSION}",
        directory,
        "rebuild",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    source_wheel = rebuilt / result.stdout.splitlines()[-1]
    with zipfile.ZipFile(wheel) as direct, zipfile.ZipFile(source_wheel) as from_source:
        assert {n: direct.read(n) for n in direct.namelist()} == {
            n: from_source.read(n) for n in from_source.namelist()
        }
    return source_wheel


def _check_wheel_resources(wheel: Path) -> None:
    """Require the wheel's package code and data resources to match the repository.

    Parameters
    ----------
    wheel
        Built wheel.
    """
    with zipfile.ZipFile(wheel) as package:
        assert (
            package.read("loop_timing_witness/manifest_io.py")
            == (ROOT / "src/loop_timing_witness/manifest_io.py").read_bytes()
        )
        assert (
            package.read("loop_timing_witness/py.typed")
            == (ROOT / "src/loop_timing_witness/py.typed").read_bytes()
        )
        for resource in (ROOT / "src/loop_timing_witness/data").glob("*.json"):
            counterpart = (
                ROOT / "analysis/rust/public-data" / resource.name
                if resource.name in PROFILE_RESOURCES
                else ROOT / resource.name
            )
            assert resource.read_bytes() == counterpart.read_bytes()
            assert (
                package.read(f"loop_timing_witness/data/{resource.name}") == resource.read_bytes()
            )


@pytest.fixture
def installed_distribution(tmp_path: Path, built_distribution: Path) -> Path:
    """Install the artifact and hashed runtime wheels into an independent environment.

    Parameters
    ----------
    tmp_path
        Exclusive environment and installer logs.
    built_distribution
        Actual direct or source-rebuilt wheel.

    Returns
    -------
    Path
        Isolated environment containing the installed package and public command.
    """
    consumer = tmp_path / "consumer"
    created = _run([sys.executable, "-I", "-m", "venv", str(consumer)], tmp_path, tmp_path, "venv")
    assert created.returncode == 0, created.stderr
    interpreter = consumer / "bin/python"
    wheelhouse = Path(os.environ.get("WITNESS_PYTHON_WHEELHOUSE", ROOT / "build/python-wheelhouse"))
    runtime = ["--find-links", str(wheelhouse), "--require-hashes", "--no-deps"]
    requirements = ["-r", str(ROOT / "requirements-runtime.txt")]
    _pip_install(interpreter, [*runtime, *requirements], tmp_path, "runtime_install")
    _pip_install(interpreter, ["--no-deps", str(built_distribution)], tmp_path, "package_install")
    return consumer


def _pip_install(interpreter: Path, arguments: list[str], directory: Path, name: str) -> None:
    """Install without an index into the consumer environment and require success.

    Parameters
    ----------
    interpreter
        Consumer environment interpreter.
    arguments
        Installer arguments after ``--no-index``.
    directory
        Working and log directory.
    name
        Log name.
    """
    installed = _run(
        [str(interpreter), "-I", "-m", "pip", "install", "--no-index", *arguments],
        directory,
        directory,
        name,
    )
    assert installed.returncode == 0, installed.stdout + installed.stderr


def assert_installed_nonfinite_refusal(consumer: Path, manifest_path: Path, tmp_path: Path) -> None:
    """Refuse altered real run numbers through the installed public API and command.

    Parameters
    ----------
    consumer
        Independent environment containing the actual built wheel.
    manifest_path
        Existing valid manifest whose original bytes are restored after the controls.
    tmp_path
        Exclusive process logs and output paths for each deliberately invalid number.
    """
    original = manifest_path.read_text()
    for index, token in enumerate(("NaN", "Infinity", "-Infinity", "1e999", "-1e999")):
        manifest_path.write_text(original.replace("{", '{"untrusted_numeric":' + token + ",", 1))
        api = _run(
            [str(consumer / "bin/python"), "-I", "-c", NONFINITE_PROGRAM, str(manifest_path)],
            tmp_path,
            tmp_path,
            f"nonfinite-api-{index}",
        )
        assert api.returncode == 0, api.stdout + api.stderr
        assert "non-finite JSON number" in api.stdout
        output = tmp_path / f"nonfinite-report-{index}"
        cli = _run(
            [
                str(consumer / "bin/loop-timing-witness-analyze"),
                str(manifest_path),
                "--output-dir",
                str(output),
            ],
            tmp_path,
            tmp_path,
            f"nonfinite-cli-{index}",
        )
        assert cli.returncode == 1
        assert "non-finite JSON number" in cli.stderr
        assert not output.exists()
    manifest_path.write_text(original)


@pytest.mark.parametrize("built_distribution", ["wheel", "sdist"], indirect=True)
@pytest.mark.parametrize("started_utc", [None, "2026-09-26t00:00:00z"])
def test_installed_distribution_analyzes_real_rtl(
    tmp_path: Path,
    make_rtl_run: MakeRtlRun,
    installed_distribution: Path,
    started_utc: str | None,
) -> None:
    """Verify packaged API, command and digest refusal on actual RTL-produced events.

    Parameters
    ----------
    tmp_path
        Exclusive real RTL event output and installed consumer command logs.
    make_rtl_run
        Factory executing the repository's Icarus event capture path.
    installed_distribution
        Independent environment using the wheel or source-rebuilt artifact.
    started_utc
        Optional schema-valid lowercase UTC timestamp for the installed consumers.
    """
    consumer = installed_distribution
    interpreter = consumer / "bin/python"
    run_directory, manifest = make_rtl_run()
    manifest_path = run_directory / "manifest.json"
    if started_utc is not None:
        manifest["started_utc"] = started_utc
        manifest_path.write_text(json.dumps(manifest))
    expected, _ = build_report(load_run(manifest_path))
    api = _run(
        [str(interpreter), "-I", "-c", API_PROGRAM, str(manifest_path)],
        tmp_path,
        tmp_path,
        "public_api",
    )
    assert api.returncode == 0, api.stdout + api.stderr
    observed = json.loads(api.stdout)
    assert Path(observed["origin"]).is_relative_to(consumer)
    assert Path(observed["prefix"]) == consumer
    assert observed["report"] == expected
    assert observed["report"]["started_utc"] == manifest["started_utc"]
    command = consumer / "bin/loop-timing-witness-analyze"
    _check_command_report(command, manifest_path, expected, tmp_path)
    assert_installed_nonfinite_refusal(consumer, manifest_path, tmp_path)
    _check_digest_refusal(command, manifest, manifest_path, tmp_path)


def _check_digest_refusal(
    command: Path, manifest: dict[str, Any], manifest_path: Path, directory: Path
) -> None:
    """Zero the events digest and require the installed command to refuse the run.

    Parameters
    ----------
    command
        Installed public analyser command.
    manifest
        Run declaration, changed in place and written.
    manifest_path
        Run manifest path.
    directory
        Exclusive log and report directory.
    """
    manifest["files"]["events"]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest))
    refused = directory / "refused"
    result = _run(
        [str(command), str(manifest_path), "--output-dir", str(refused)],
        directory,
        directory,
        "refusal",
    )
    assert result.returncode == 1
    assert "input SHA-256 mismatch: events.bin" in result.stderr
    assert "events.bin" in result.stderr
    assert not refused.exists()


def _check_command_report(
    command: Path, manifest_path: Path, expected: dict[str, Any], directory: Path
) -> None:
    """Require the installed command to publish the expected report and jitter files.

    Parameters
    ----------
    command
        Installed public analyser command.
    manifest_path
        Valid run manifest.
    expected
        Report the repository analysis gives.
    directory
        Exclusive log and report directory.
    """
    reports = directory / "reports"
    result = _run(
        [str(command), str(manifest_path), "--output-dir", str(reports)],
        directory,
        directory,
        "cli",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads((reports / "report.json").read_bytes()) == expected
    assert expected["evidence_status"] == "simulation_only"
    assert expected["events"]["jitter"]["compute_time"]["sample_count"] == 2
    assert expected["events"]["jitter"]["compute_time"]["median_ticks"] == 2495
    for filename in ("jitter_summary.csv", "cycle_jitter.csv", "jitter_p99.svg"):
        content = (reports / filename).read_text()
        assert "simulation_only" in content
        assert "compute_time" in content
