# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — Rust outcome of a hermetic neural acquisition

"""Run the public Rust API on the acquisition a Python test analysed.

The Rust registry consumer reads a description of the test's own registry
entry and records either the whole report or the refusal. A test asserts that
both languages reach the same outcome. ``WITNESS_RUST_REGISTRY_CONSUMER``
names a prebuilt consumer; otherwise it is built once per process. With
``WITNESS_RUST_PROFILE_DIRECTORY`` set, an instrumented consumer writes its
profiles there for the hosted coverage gate.
"""

from __future__ import annotations

import copy
import json
import os
import re
import subprocess
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import loop_timing_witness
from loop_timing_witness.neural_checker_image import ImageCheckerExecutor
from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError
from loop_timing_witness.neural_run_api import build_neural_run_report, load_neural_run

if TYPE_CHECKING:
    from collections.abc import Sequence

    from neural_acquisition_support import NeuralAcquisition

CRATE = Path(__file__).resolve().parents[1] / "analysis/rust"


@cache
def consumer() -> Path:
    """Return the Rust registry consumer test binary.

    Returns
    -------
    Path
        Prebuilt binary from the environment, or one built from the crate.
    """
    selected = os.environ.get("WITNESS_RUST_REGISTRY_CONSUMER")
    if selected:
        return Path(selected)
    result = subprocess.run(
        [
            "cargo",
            "test",
            "--offline",
            "--locked",
            "--no-run",
            "--message-format=json",
            "--manifest-path",
            str(CRATE / "Cargo.toml"),
            "--test",
            "registry_consumer",
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=1200,
        check=True,
    )
    for line in result.stdout.splitlines():
        message = json.loads(line)
        if message.get("reason") == "compiler-artifact" and message["target"]["name"] == (
            "registry_consumer"
        ):
            return Path(message["executable"])
    message = "The Rust registry consumer was not built."
    raise AssertionError(message)


def _executor(entry: Any, directory: Path) -> dict[str, Any]:  # noqa: ANN401
    """Describe the entry's executor with its exact bytes written to files.

    Parameters
    ----------
    entry
        Image executor or host installation of the registry entry.
    directory
        Owned directory for the written bytes.

    Returns
    -------
    dict[str, Any]
        Executor description for the Rust consumer.
    """
    if isinstance(entry, ImageCheckerExecutor):
        (directory / "binding.json").write_bytes(entry.binding_bytes)
        (directory / "runtime.json").write_bytes(entry.runtime_bytes)
        return {
            "image": {
                "root": str(entry.image_root),
                "binding": str(directory / "binding.json"),
                "runtime": str(directory / "runtime.json"),
            }
        }
    (directory / "contract.json").write_bytes(entry.contract_bytes())
    return {
        "host": {
            "contract": str(directory / "contract.json"),
            "files": [
                {
                    "name": item.name,
                    "path": str(item.path),
                    "sha256": item.sha256,
                    "byte_length": item.byte_length,
                }
                for item in entry.files
            ],
            "import_roots": [str(root) for root in entry.import_roots],
            "worker_import_root": str(Path(loop_timing_witness.__file__).resolve().parents[1]),
        }
    }


def rust_outcome(
    acquisition: NeuralAcquisition,
    directory: Path,
    command: Path | None = None,
    wrapper: Sequence[str] = (),
) -> dict[str, Any]:
    """Run the Rust API or command against the acquisition and its own registry entry.

    Parameters
    ----------
    acquisition
        Written acquisition and reviewed entry.
    directory
        Owned directory for the description and outcome, created when absent.
    command
        New report directory for the analysis command, or ``None`` for the API.
    wrapper
        Argument vector that runs the consumer under a host condition.

    Returns
    -------
    dict[str, Any]
        ``{"report": ...}`` or ``{"refusal": message}`` from the API, or the
        command's ``status``, ``stdout`` and ``stderr``.
    """
    directory.mkdir(exist_ok=True)
    policy, checker, executor = acquisition.entry
    (directory / "policy.json").write_bytes(policy)
    (directory / "checker.json").write_bytes(checker)
    spec = {
        "manifest": str(acquisition.manifest),
        "outcome": str(directory / "outcome.json"),
        "source_sha256": json.loads(acquisition.manifest.read_bytes())["source_contract_ref"][
            "sha256"
        ],
        "policy": str(directory / "policy.json"),
        "checker": str(directory / "checker.json"),
        "executor": _executor(executor, directory),
        "command": None if command is None else str(command),
    }
    (directory / "spec.json").write_text(json.dumps(spec))
    environment = {**os.environ, "NEURAL_REGISTRY_SPEC": str(directory / "spec.json")}
    profiles = os.environ.get("WITNESS_RUST_PROFILE_DIRECTORY")
    if profiles:
        environment["LLVM_PROFILE_FILE"] = str(Path(profiles) / "registry-%p-%m.profraw")
    result = subprocess.run(
        [*wrapper, str(consumer()), "--exact", "consumer_registry_acquisition", "--nocapture"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=environment,
        timeout=600,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    outcome: dict[str, Any] = json.loads((directory / "outcome.json").read_bytes())
    return outcome


def _observations(report: dict[str, Any]) -> dict[str, Any]:
    """Remove fresh checker invocation evidence, which differs between runs.

    Parameters
    ----------
    report
        Whole analysis report.

    Returns
    -------
    dict[str, Any]
        Report restricted to original observations and verdicts.
    """
    report = copy.deepcopy(report)
    binding = report["source_binding"]
    binding.pop("checker_invocations")
    binding["original_inputs"] = {
        role: value
        for role, value in binding["original_inputs"].items()
        if not role.startswith("fresh_checker_")
    }
    return report


def python_outcome(acquisition: NeuralAcquisition) -> dict[str, Any]:
    """Run the Python API against the acquisition and its own registry entry.

    Parameters
    ----------
    acquisition
        Written acquisition and reviewed entry.

    Returns
    -------
    dict[str, Any]
        ``{"report": ...}`` or ``{"refusal": message}``.
    """
    try:
        inputs = load_neural_run(acquisition.manifest, registry=acquisition.registry)
    except NeuralCaptureRefusalError as exc:
        return {"refusal": str(exc)}
    return {"report": build_neural_run_report(inputs)}


def assert_same_outcome(python: dict[str, Any], rust: dict[str, Any]) -> None:
    """Require one refusal message or one report of original observations.

    Parameters
    ----------
    python, rust
        Outcomes of the two languages for the same acquisition.
    """
    if "refusal" in python or "refusal" in rust:
        assert rust == python
        return
    assert _observations(rust["report"]) == _observations(python["report"])


def assert_refusal_in_both(acquisition: NeuralAcquisition, directory: Path, pattern: str) -> None:
    """Require the Python refusal matching ``pattern`` and the same Rust refusal.

    Parameters
    ----------
    acquisition
        Written acquisition and reviewed entry.
    directory
        New owned directory for the Rust run.
    pattern
        Regular expression the Python refusal must contain.
    """
    python = python_outcome(acquisition)
    assert "refusal" in python, python
    assert re.search(pattern, python["refusal"]), python["refusal"]
    assert_same_outcome(python, rust_outcome(acquisition, directory))


def assert_report_in_both(
    report: dict[str, Any], acquisition: NeuralAcquisition, directory: Path
) -> None:
    """Require the Rust report of the acquisition to equal the Python report.

    Parameters
    ----------
    report
        Python report of the acquisition.
    acquisition
        Written acquisition and reviewed entry.
    directory
        New owned directory for the Rust run.
    """
    assert_same_outcome({"report": report}, rust_outcome(acquisition, directory))


def assert_command_in_both(
    python: tuple[int | None, str, str],
    output: Path,
    acquisition: NeuralAcquisition,
    directory: Path,
) -> None:
    """Require the Rust command to match the Python dispatch of the same acquisition.

    Status, printed lines and the published report's original observations must
    agree; each language publishes into its own new directory.

    Parameters
    ----------
    python
        Python status with its standard output and error.
    output
        Python report directory.
    acquisition
        Written acquisition and reviewed entry.
    directory
        Owned directory for the Rust run; the Rust report is ``report`` in it.
    """
    rust_output = directory / "report"
    rust = rust_outcome(acquisition, directory, command=rust_output)
    status, stdout, stderr = python
    assert rust == {
        "status": status,
        "stdout": stdout.replace(str(output), str(rust_output)),
        "stderr": stderr,
    }
    if status != 1:
        assert _observations(json.loads((rust_output / "report.json").read_bytes())) == (
            _observations(json.loads((output / "report.json").read_bytes()))
        )
