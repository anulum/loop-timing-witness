# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — native compiler and artifact reconciliation

"""Bind complete native objects/logs and reconcile actual recorded commands."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .neural_event_stream import NeuralCaptureRefusalError
from .neural_run_files import read_neural_run_file as read_neural_bound_file
from .neural_run_native_commands import native_command_findings
from .neural_run_policy import ARTIFACT_LIMIT
from .neural_run_receipt_io import TEXT, UNSIGNED, decode_actual_receipt

EXECUTION_INDEX = 4

if TYPE_CHECKING:
    from .neural_run_binding import BoundNeuralRun

PARAMETERS = ("EXTRA_STATE_REGISTER", "TIMESTAMP_OFFSET", "DROP_ENCODER_FEED", "ADDRESS_BITS")
JOB_KINDS = (
    "RTL_elaboration",
    "generated_model_archive",
    "native_CPP_compile",
    "native_CPP_link",
    "native_execution",
)
NATIVE_FILE = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "path": TEXT,
        "sha256": TEXT,
        "byte_length": {"type": "integer", "minimum": 0, "maximum": ARTIFACT_LIMIT},
    },
    "required": ["path", "sha256", "byte_length"],
}


def _closed(fields: dict[str, Any]) -> dict[str, Any]:
    """Return the schema of an object holding exactly the given fields.

    Parameters
    ----------
    fields
        Field schemas keyed by field name.

    Returns
    -------
    dict[str, Any]
        Object schema requiring every field and admitting no other.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": fields,
        "required": list(fields),
    }


_COMMON = {
    "kind": TEXT,
    "command": {"type": "array", "minItems": 1, "items": TEXT},
    "returncode": {"type": "integer", "minimum": -2147483648, "maximum": 2147483647},
}
_LOG_JOB = _closed({**_COMMON, "log": NATIVE_FILE})
_EXECUTION_JOB = _closed({**_COMMON, "stdout": NATIVE_FILE, "stderr": NATIVE_FILE})
_JOBS = {
    "type": "array",
    "minItems": 5,
    "maxItems": 5,
    "prefixItems": [*[_LOG_JOB] * 4, _EXECUTION_JOB],
}


def _runtime(run: BoundNeuralRun) -> dict[str, Any]:
    """Decode the complete closed native receipt and every typed job variant.

    Parameters
    ----------
    run
        Fully bound private source and runtime bytes.

    Returns
    -------
    dict[str, Any]
        Validated native declarations, without executing supplied commands.

    Raises
    ------
    ValueError
        If any receipt field, job variant or integer encoding is unsupported.
    """
    policy = run.contract.policy
    source_count = len(policy["sources"])
    artifact_names = next(iter(policy["compiled_artifacts"].values()))
    return decode_actual_receipt(
        run.files["compiler_simulator_runtime"],
        "native runtime",
        {
            "scope": TEXT,
            "backend": TEXT,
            "dialect": TEXT,
            "epoch": UNSIGNED,
            "steps": UNSIGNED,
            "parameters": _closed(dict.fromkeys(PARAMETERS, UNSIGNED)),
            "tool_versions": _closed({"verilator": TEXT, "g++": TEXT}),
            "source_files": {
                "type": "array",
                "minItems": source_count,
                "maxItems": source_count,
                "items": NATIVE_FILE,
            },
            "actual_source_paths": {"type": "object", "additionalProperties": TEXT},
            "jobs": _JOBS,
            "compiled_artifacts": _closed(dict.fromkeys(artifact_names, NATIVE_FILE)),
            "runtime_object_source_scope": TEXT,
        },
    )


def _bind_artifacts(run: BoundNeuralRun, runtime: dict[str, Any]) -> None:
    """Admit the declared compiled cohort and bind every compiled object's bytes.

    Parameters
    ----------
    run
        Complete native acquisition receiving the bound object bytes.
    runtime
        Decoded native receipt.

    Raises
    ------
    ValueError
        If the parameters and epoch select no admitted cohort, the declared
        objects differ from it, or an object cannot be bound.
    """
    params = runtime["parameters"]
    key = ",".join(str(params[name]) for name in PARAMETERS) + f":{runtime['epoch']}"
    expected = run.contract.policy["compiled_artifacts"].get(key)
    if expected is None or runtime["compiled_artifacts"] != expected:
        message = "Unsupported actual native compiled artifact cohort."
        raise NeuralCaptureRefusalError(message)
    for name, reference in runtime["compiled_artifacts"].items():
        run.files[f"native_{name}"] = read_neural_bound_file(
            run.directory, reference, ARTIFACT_LIMIT
        )


def _bind_job_logs(run: BoundNeuralRun, jobs: list[dict[str, Any]]) -> None:
    """Bind the log of every compile job and both streams of the execution job.

    Parameters
    ----------
    run
        Complete native acquisition receiving the bound log bytes.
    jobs
        Decoded jobs in their admitted kind sequence.

    Raises
    ------
    ValueError
        If a log cannot be bound.
    """
    for index, job in enumerate(jobs):
        names = ("stdout", "stderr") if index == EXECUTION_INDEX else ("log",)
        for name in names:
            run.files[f"native_job_{index}_{name}"] = read_neural_bound_file(
                run.directory, job[name], 1048576
            )


def analyze_native_runtime(run: BoundNeuralRun) -> tuple[str, ...]:
    """Bind exact compiled bytes and compare native command/source/run predicates.

    Parameters
    ----------
    run
        Complete native acquisition, including real fault exports.

    Returns
    -------
    tuple[str, ...]
        Reliable recorded source/configuration/execution inconsistencies.

    Raises
    ------
    ValueError
        If source, object, log, command sequence or configuration is unsupported.
    """
    runtime = _runtime(run)
    if runtime["backend"] != "verilator-native-cpp" or runtime["dialect"] != "1800-2012":
        message = "Unsupported actual native backend or dialect."
        raise NeuralCaptureRefusalError(message)
    _bind_artifacts(run, runtime)
    if runtime["source_files"] != run.manifest["source_files"]:
        message = "Native runtime source references differ from root."
        raise NeuralCaptureRefusalError(message)
    paths = runtime["actual_source_paths"]
    if len(paths) != len(run.contract.policy["sources"]) or set(paths.values()) != set(run.sources):
        message = "Native recorded source path population differs."
        raise NeuralCaptureRefusalError(message)
    if tuple(job["kind"] for job in runtime["jobs"]) != JOB_KINDS:
        message = "Actual native command sequence differs."
        raise NeuralCaptureRefusalError(message)
    _bind_job_logs(run, runtime["jobs"])
    return native_command_findings(run, runtime)
