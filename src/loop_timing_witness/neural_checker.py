# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete source-owned numerical checker verification

"""Regenerate the admitted fixture and execute the actual complete source-owned checker."""

from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .manifest_io import canonical_json_bytes
from .neural_checker_contract import bind_checker_contract
from .neural_checker_execution import invoke_source_checker
from .neural_checker_image import ImageCheckerExecutor
from .neural_checker_receipts import checker_receipt_findings
from .neural_checker_trace import checker_trace_findings
from .neural_event_stream import NeuralCaptureRefusalError

if TYPE_CHECKING:
    from .neural_checker_execution import CheckerInvocation
    from .neural_run_binding import BoundNeuralRun

_OUTPUT_LIMIT = 65536


@dataclass(frozen=True, slots=True)
class NeuralCheckerFindings:
    """Independent source, numerical and execution-completion findings.

    Attributes
    ----------
    source, numerical, completion
        Actual invocation, full-file correspondence and original receipt failures.
    executed
        Whether both actual workers reached the source-owned program.
    """

    source: tuple[str, ...]
    numerical: tuple[str, ...]
    completion: tuple[str, ...]
    executed: bool


def verify_source_checker(run: BoundNeuralRun) -> NeuralCheckerFindings:
    """Execute both fixed operations using only the admitted closure and installation.

    Parameters
    ----------
    run
        Entire source-admitted original public acquisition, never a component envelope.

    Returns
    -------
    NeuralCheckerFindings
        Complete source, numerical and completion findings. The source-owned model
        is actually regenerated and compared; recorded success cannot replace it.
    """
    policy = bind_checker_contract(run)
    installation = run.contract.installation
    digests = tuple(reference["sha256"] for reference in policy["source_files"])
    source = list(checker_receipt_findings(run, policy))
    numerical: list[str] = []
    completion: list[str] = []
    executed = True
    with tempfile.TemporaryDirectory(prefix="neural-checker-") as name:
        root = Path(name)
        source_root = root / "source-closure"
        copied = set()
        for reference in policy["source_files"]:
            path = source_root / reference["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(run.sources[reference["path"]])
            copied.add(path)
        script = source_root / policy["entry_point"]["path"]
        for operation in ("generate", "check"):
            directory = root / operation
            directory.mkdir()
            if operation == "check":
                (directory / "results_verilog.txt").write_bytes(run.files["numerical_projection"])
            if isinstance(installation, ImageCheckerExecutor):
                actual = installation.invoke(operation, directory)
                source.extend(installation.closure_findings(actual, digests))
            else:
                actual = invoke_source_checker(installation, script, operation, directory)
                source.extend(
                    checker_trace_findings(actual, directory, frozenset(copied), installation)
                )
            executed = (
                executed
                and actual.observation is not None
                and actual.observation.get("phase") == "source"
            )
            actual_findings = _invocation_findings(actual)
            source.extend(actual_findings.source)
            numerical.extend(actual_findings.numerical)
            completion.extend(actual_findings.completion)
            if operation == "generate" and actual.returncode == 0:
                source.extend(_generation_findings(run, directory))
            run.files[f"fresh_checker_{operation}_execution_receipt"] = canonical_json_bytes(
                {
                    "command": list(actual.command),
                    "native_returncode": actual.returncode,
                    "started_ns": actual.started_ns,
                    "completed_ns": actual.completed_ns,
                    "elapsed_ns": actual.elapsed_ns,
                    "interrupted": actual.interrupted,
                    "worker_observation": actual.observation,
                }
            )
            run.files[f"fresh_checker_{operation}_stdout"] = actual.stdout
            run.files[f"fresh_checker_{operation}_stderr"] = actual.stderr
            run.files[f"fresh_checker_{operation}_opened_files"] = actual.trace
    installation.verify()
    return NeuralCheckerFindings(tuple(source), tuple(numerical), tuple(completion), executed)


def _invocation_findings(actual: CheckerInvocation) -> NeuralCheckerFindings:
    """Reconcile actual worker completion and source comparison observations.

    Parameters
    ----------
    actual
        Original process status, worker observation and diagnostic bytes.

    Returns
    -------
    NeuralCheckerFindings
        Independent findings without inferred checker execution.
    """
    source = []
    numerical: list[str] = []
    completion: list[str] = []
    observation = actual.observation
    if actual.interrupted or observation is None:
        completion.append("Actual source checker lacks a complete reaped observation.")
    elif observation["native_returncode"] != actual.returncode:
        source.append("Actual source checker worker and native process status differ.")
    if actual.returncode != 0:
        numerical.append("Actual source checker refused the complete selected projection.")
    if actual.stderr:
        completion.append("Actual source checker reported an execution diagnostic.")
    return NeuralCheckerFindings(
        tuple(source),
        tuple(numerical),
        tuple(completion),
        observation is not None and observation.get("phase") == "source",
    )


def _generation_findings(run: BoundNeuralRun, directory: Path) -> tuple[str, ...]:
    """Compare both actual generated files against their original bound whole roles.

    Parameters
    ----------
    run
        Source-admitted acquisition containing the original fixture.
    directory
        Owned completed generation directory.

    Returns
    -------
    tuple[str, ...]
        Whole-file generation differences, independent of numerical comparison.
    """
    return tuple(
        "Actual source generation differs from the bound original fixture."
        for filename, role in (
            ("stimuli.txt", "original_stimulus"),
            ("results_expected.txt", "reference_projection"),
        )
        if _output_bytes(directory / filename) != run.files[role]
    )


def _output_bytes(path: Path) -> bytes:
    """Read one generated output as a bounded regular file without following a link.

    Parameters
    ----------
    path
        Output inside the owned generation directory.

    Returns
    -------
    bytes
        Complete output bytes.

    Raises
    ------
    NeuralCaptureRefusalError
        If the output is absent, a link, nonregular, unreadable or excessive.
    """
    try:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        with os.fdopen(os.open(path, flags), "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                message = "Actual checker output must be a regular file."
                raise NeuralCaptureRefusalError(message)
            raw = stream.read(_OUTPUT_LIMIT + 1)
    except OSError as exc:
        message = "Actual checker output is unavailable."
        raise NeuralCaptureRefusalError(message) from exc
    if len(raw) > _OUTPUT_LIMIT:
        message = "Actual checker output exceeds its allocation."
        raise NeuralCaptureRefusalError(message)
    return raw
