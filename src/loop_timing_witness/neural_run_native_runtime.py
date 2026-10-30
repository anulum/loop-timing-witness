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
    common = {
        "kind": TEXT,
        "command": {"type": "array", "minItems": 1, "items": TEXT},
        "returncode": {"type": "integer", "minimum": -2147483648, "maximum": 2147483647},
    }
    jobs = [
        {
            "type": "object",
            "additionalProperties": False,
            "properties": fields,
            "required": list(fields),
        }
        for fields in (
            {**common, "log": NATIVE_FILE},
            {**common, "stdout": NATIVE_FILE, "stderr": NATIVE_FILE},
        )
    ]
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
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": dict.fromkeys(PARAMETERS, UNSIGNED),
                "required": list(PARAMETERS),
            },
            "tool_versions": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"verilator": TEXT, "g++": TEXT},
                "required": ["verilator", "g++"],
            },
            "source_files": {
                "type": "array",
                "minItems": source_count,
                "maxItems": source_count,
                "items": NATIVE_FILE,
            },
            "actual_source_paths": {"type": "object", "additionalProperties": TEXT},
            "jobs": {
                "type": "array",
                "minItems": 5,
                "maxItems": 5,
                "prefixItems": [jobs[0], jobs[0], jobs[0], jobs[0], jobs[1]],
            },
            "compiled_artifacts": {
                "type": "object",
                "additionalProperties": False,
                "properties": dict.fromkeys(artifact_names, NATIVE_FILE),
                "required": list(artifact_names),
            },
            "runtime_object_source_scope": TEXT,
        },
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
    params = runtime["parameters"]
    key = ",".join(str(params[name]) for name in PARAMETERS) + f":{runtime['epoch']}"
    policy = run.contract.policy
    expected = policy["compiled_artifacts"].get(key)
    if expected is None or runtime["compiled_artifacts"] != expected:
        message = "Unsupported actual native compiled artifact cohort."
        raise NeuralCaptureRefusalError(message)
    for name, reference in runtime["compiled_artifacts"].items():
        run.files[f"native_{name}"] = read_neural_bound_file(
            run.directory, reference, ARTIFACT_LIMIT
        )
    if runtime["source_files"] != run.manifest["source_files"]:
        message = "Native runtime source references differ from root."
        raise NeuralCaptureRefusalError(message)
    paths = runtime["actual_source_paths"]
    if len(paths) != len(policy["sources"]) or set(paths.values()) != set(run.sources):
        message = "Native recorded source path population differs."
        raise NeuralCaptureRefusalError(message)
    jobs = runtime["jobs"]
    if tuple(job["kind"] for job in jobs) != JOB_KINDS:
        message = "Actual native command sequence differs."
        raise NeuralCaptureRefusalError(message)
    for index, job in enumerate(jobs):
        names = ("stdout", "stderr") if index == EXECUTION_INDEX else ("log",)
        for name in names:
            run.files[f"native_job_{index}_{name}"] = read_neural_bound_file(
                run.directory, job[name], 1048576
            )
    return native_command_findings(run, runtime)
