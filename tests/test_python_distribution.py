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
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from loop_timing_witness import build_report, load_run

if TYPE_CHECKING:
    from conftest import MakeRtlRun

ROOT = Path(__file__).resolve().parents[1]


def _run(argv: list[str], cwd: Path, output: Path, name: str) -> subprocess.CompletedProcess[str]:
    """Execute a real package command with checkout injection removed and retain its evidence."""
    environment = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONHOME", "COVERAGE_PROCESS_START"):
        environment.pop(key, None)
    environment["PIP_CONFIG_FILE"] = os.devnull
    result = subprocess.run(
        argv, cwd=cwd, env=environment, capture_output=True, text=True, timeout=120, check=False
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
        [
            sys.executable,
            "-I",
            "-c",
            (
                "import json,sys; from flit_core.buildapi import build_wheel,build_sdist; "
                "print(json.dumps([build_wheel(sys.argv[1]),build_sdist(sys.argv[1])]))"
            ),
            str(artifacts),
        ],
        ROOT,
        tmp_path,
        "build",
    )
    assert built.returncode == 0, built.stdout + built.stderr
    wheel_name, source_name = json.loads(built.stdout.splitlines()[-1])
    assert isinstance(wheel_name, str)
    assert isinstance(source_name, str)
    wheel = artifacts / wheel_name
    if request.param == "sdist":
        unpacked = tmp_path / "unpacked"
        with tarfile.open(artifacts / source_name) as archive:
            archive.extractall(unpacked, filter="data")
        rebuilt = tmp_path / "rebuilt"
        rebuilt.mkdir()
        result = _run(
            [
                sys.executable,
                "-I",
                "-c",
                (
                    "import sys; from flit_core.buildapi import build_wheel; "
                    "print(build_wheel(sys.argv[1]))"
                ),
                str(rebuilt),
            ],
            unpacked / "loop_timing_witness-0.1.0",
            tmp_path,
            "rebuild",
        )
        assert result.returncode == 0, result.stdout + result.stderr
        source_wheel = rebuilt / result.stdout.splitlines()[-1]
        with zipfile.ZipFile(wheel) as direct, zipfile.ZipFile(source_wheel) as from_source:
            assert {n: direct.read(n) for n in direct.namelist()} == {
                n: from_source.read(n) for n in from_source.namelist()
            }
        wheel = source_wheel
    with zipfile.ZipFile(wheel) as package:
        assert (
            package.read("loop_timing_witness/py.typed")
            == (ROOT / "src/loop_timing_witness/py.typed").read_bytes()
        )
        for resource in (ROOT / "src/loop_timing_witness/data").glob("*.json"):
            assert resource.read_bytes() == (ROOT / resource.name).read_bytes()
            assert (
                package.read(f"loop_timing_witness/data/{resource.name}") == resource.read_bytes()
            )

    return wheel


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
    installed = _run(
        [
            str(interpreter),
            "-I",
            "-m",
            "pip",
            "install",
            "--no-index",
            "--find-links",
            str(wheelhouse),
            "--require-hashes",
            "--no-deps",
            "-r",
            str(ROOT / "requirements-runtime.txt"),
        ],
        tmp_path,
        tmp_path,
        "runtime_install",
    )
    assert installed.returncode == 0, installed.stdout + installed.stderr
    installed = _run(
        [
            str(interpreter),
            "-I",
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            str(built_distribution),
        ],
        tmp_path,
        tmp_path,
        "package_install",
    )
    assert installed.returncode == 0, installed.stdout + installed.stderr
    return consumer


@pytest.mark.parametrize("built_distribution", ["wheel", "sdist"], indirect=True)
def test_installed_distribution_analyzes_real_rtl(
    tmp_path: Path, make_rtl_run: MakeRtlRun, installed_distribution: Path
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
    """
    consumer = installed_distribution
    interpreter = consumer / "bin/python"
    run_directory, manifest = make_rtl_run()
    manifest_path = run_directory / "manifest.json"
    expected, _ = build_report(load_run(manifest_path))
    api = _run(
        [
            str(interpreter),
            "-I",
            "-c",
            (
                "import json,sys; from pathlib import Path; import loop_timing_witness as w; "
                "print(json.dumps({'origin':w.__file__,'prefix':sys.prefix,"
                "'report':w.build_report(w.load_run(Path(sys.argv[1])))[0]}))"
            ),
            str(manifest_path),
        ],
        tmp_path,
        tmp_path,
        "public_api",
    )
    assert api.returncode == 0, api.stdout + api.stderr
    observed = json.loads(api.stdout)
    assert Path(observed["origin"]).is_relative_to(consumer)
    assert Path(observed["prefix"]) == consumer
    assert observed["report"] == expected
    command = consumer / "bin/loop-timing-witness-analyze"
    reports = tmp_path / "reports"
    result = _run(
        [str(command), str(manifest_path), "--output-dir", str(reports)], tmp_path, tmp_path, "cli"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads((reports / "report.json").read_bytes()) == expected
    assert expected["evidence_status"] == "simulation_only"
    manifest["files"]["events"]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest))
    refused = tmp_path / "refused"
    result = _run(
        [str(command), str(manifest_path), "--output-dir", str(refused)],
        tmp_path,
        tmp_path,
        "refusal",
    )
    assert result.returncode == 1
    assert "input SHA-256 mismatch: events.bin" in result.stderr
    assert "events.bin" in result.stderr
    assert not refused.exists()
