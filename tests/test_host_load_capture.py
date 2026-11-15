# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — source-bound host load capture and report integration

"""Capture real host work, production RTL and hash-bound analysis through public CLI."""

from __future__ import annotations

import hashlib
import json
import os
from typing import TYPE_CHECKING, Any

import pytest
from linux_load_config import PROFILES
from test_native_run import configuration

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import RunTool

# Load tools a capture snapshots under source/tools.
LOAD_TOOLS = (
    "linux_load.py",
    "linux_load_config.py",
    "linux_load_worker.py",
    "linux_load_channels.py",
    "linux_load_readiness.py",
    "linux_load_process.py",
    "manifest_io.py",
)
DIGEST = "input SHA-256 mismatch: host_load.json"
STATUS = "host load profile or native exit status"


@pytest.mark.parametrize("profile", PROFILES)
def test_frozen_load_capture(tmp_path: Path, run_tool: RunTool, profile: str) -> None:
    """Freeze and analyze actual host work for every profile over both plant types.

    Parameters
    ----------
    tmp_path
        Exclusive source and output allocation.
    run_tool
        Actual producer and analyzer CLI runner.
    profile
        Real host workload, with alternating mechanical and thermal plant builds.
    """
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none"), encoding="utf-8")
    run = tmp_path / "capture"
    thermal = PROFILES.index(profile) % 2
    result = run_tool(
        "capture_native_simulation",
        str(config),
        "--output-dir",
        str(run),
        "--thermal",
        str(thermal),
        "--load-profile",
        profile,
        "--load-cpu",
        str(min(os.sched_getaffinity(0))),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    manifest, receipt, report = _check_bound_capture(run, profile)
    reanalysis = run_tool(
        "analyze_run", str(run / "manifest.json"), "--output-dir", str(run / "repeat")
    )
    assert reanalysis.returncode == 0, reanalysis.stdout + reanalysis.stderr
    assert json.loads((run / "repeat/report.json").read_bytes()) == report
    wrong_digest = dict(manifest)
    wrong_digest["host_load"] = {**manifest["host_load"], "sha256": "0" * 64}
    _check_refused(run_tool, run / "wrong_digest", wrong_digest, "wrong_digest_report", (DIGEST,))
    wrong_profile = dict(manifest)
    wrong_profile["load_case"] = "storage" if profile != "storage" else "cpu"
    _check_refused(
        run_tool, run / "wrong_profile", wrong_profile, "wrong_profile_report", (STATUS,)
    )
    malformed = dict(receipt)
    malformed["native_returncode"] = 1
    raw = (json.dumps(malformed) + "\n").encode()
    (run / "altered_load.json").write_bytes(raw)
    manifest["host_load"] = {"path": "altered_load.json", "sha256": hashlib.sha256(raw).hexdigest()}
    _check_refused(run_tool, run / "altered_manifest", manifest, "refused", (STATUS,))


def _check_bound_capture(
    run: Path, profile: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Require the capture to bind its load receipt, its sources and its report.

    Parameters
    ----------
    run
        Completed capture directory.
    profile
        Captured load profile.

    Returns
    -------
    tuple[dict[str, Any], dict[str, Any], dict[str, Any]]
        Manifest, host load receipt and report.
    """
    manifest = json.loads((run / "manifest.json").read_bytes())
    receipt = json.loads((run / "host_load.json").read_bytes())
    report = json.loads((run / "reports/report.json").read_bytes())
    assert manifest["load_case"] == profile
    assert (
        manifest["host_load"]["sha256"]
        == hashlib.sha256((run / "host_load.json").read_bytes()).hexdigest()
    )
    assert report["host_load"] == receipt
    assert report["input_sha256"]["host_load"] == manifest["host_load"]["sha256"]
    assert report["evidence_status"] == "simulation_only"
    assert report["events"]["control"]["observed_deadlines"] == 32
    assert report["energy"]["status"] == "unavailable"
    assert report["valid"] is False
    paths = {item["path"] for item in manifest["source"]["files"]}
    assert all("source/tools/" + name in paths for name in LOAD_TOOLS)
    assert "host_load_workspace/worker.json" in paths
    assert "host_load_workspace/worker.log" in paths
    for item in manifest["source"]["files"]:
        assert hashlib.sha256((run / item["path"]).read_bytes()).hexdigest() == item["sha256"]
    return manifest, receipt, report


def _check_refused(
    run_tool: RunTool,
    stem: Path,
    manifest: dict[str, Any],
    output: str,
    messages: tuple[str, ...],
) -> None:
    """Write a changed manifest beside the capture and require its analysis to be refused.

    Parameters
    ----------
    run_tool
        Analyzer CLI runner.
    stem
        Changed manifest path without its ``.json`` suffix.
    manifest
        Changed declaration.
    output
        Report directory name beside the capture, which must stay absent.
    messages
        Texts the refusal must contain.
    """
    path = stem.with_name(stem.name + ".json")
    path.write_text(json.dumps(manifest), encoding="utf-8")
    refused = run_tool("analyze_run", str(path), "--output-dir", str(stem.parent / output))
    assert refused.returncode == 1
    assert all(message in refused.stderr for message in messages)
    assert not (stem.parent / output).exists()


@pytest.mark.parametrize(
    "arguments",
    [
        ("--load-profile", "cpu"),
        ("--load-cpu", "0"),
        ("--load-working-set-bytes", "4096"),
        ("--load-profile", "network", "--load-cpu", "0", "--load-working-set-bytes", "60001"),
    ],
)
def test_incomplete_load_request(
    tmp_path: Path, run_tool: RunTool, arguments: tuple[str, ...]
) -> None:
    """Refuse incomplete or invalid capture loads before reading config or allocating output.

    Parameters
    ----------
    tmp_path
        Exclusive uncreated capture destination.
    run_tool
        Actual capture CLI runner.
    arguments
        Incomplete profile/CPU pair or resource-bound violation.
    """
    output = tmp_path / "capture"
    arguments = tuple(
        str(min(os.sched_getaffinity(0)))
        if index and arguments[index - 1] == "--load-cpu"
        else value
        for index, value in enumerate(arguments)
    )
    result = run_tool(
        "capture_native_simulation",
        str(tmp_path / "absent.conf"),
        "--output-dir",
        str(output),
        *arguments,
    )
    assert result.returncode == 1
    assert "load" in result.stderr
    assert not output.exists()


def test_capture_binds_parent_json_implementation(tmp_path: Path, run_tool: RunTool) -> None:
    """Bind actual parent JSON code and refuse a changed implementation digest.

    Parameters
    ----------
    tmp_path
        Exclusive actual idle-work capture and refusal outputs.
    run_tool
        Actual native producer and public analyser commands.
    """
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none"), encoding="utf-8")
    run = tmp_path / "capture"
    result = run_tool(
        "capture_native_simulation",
        str(config),
        "--output-dir",
        str(run),
        "--load-profile",
        "idle",
        "--load-cpu",
        str(min(os.sched_getaffinity(0))),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((run / "manifest.json").read_bytes())
    paths = {item["path"] for item in manifest["source"]["files"]}
    context = json.loads((run / "producer_context.json").read_bytes())
    implementation = "source/parent_package/loop_timing_witness/manifest_io.py"
    assert implementation in paths
    assert "producer_context.json" in paths
    assert "source/parent_tools/linux_load_readiness.py" in paths
    assert (
        context["sources"][implementation]["sha256"]
        == hashlib.sha256((run / implementation).read_bytes()).hexdigest()
    )
    assert context["python"]["implementation"] == "cpython"
    wrong_source = json.loads(json.dumps(manifest))
    source = next(
        item for item in wrong_source["source"]["files"] if item["path"] == implementation
    )
    source["sha256"] = "0" * 64
    messages = ("artefact SHA-256 mismatch", implementation)
    _check_refused(run_tool, run / "wrong_source", wrong_source, "wrong_source_report", messages)
