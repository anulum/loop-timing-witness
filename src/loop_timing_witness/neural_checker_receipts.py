# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — source-bound original checker invocation receipts

"""Bind original source-checker invocation receipts without executing receipt arguments."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .neural_checker_execution import checker_environment
from .neural_event_stream import NeuralCaptureRefusalError
from .neural_run_files import read_neural_run_file
from .strict_json import parse_json_object

if TYPE_CHECKING:
    from .neural_run_binding import BoundNeuralRun

_ARGV_LENGTH = 6
_ELAPSED_NS_LIMIT = 45 * 1000000000
_NATIVE_STATUS_LIMIT = 2**31

_FIELDS = {
    "schema_id",
    "source_contract_ref",
    "checker_policy_ref",
    "operation",
    "actual_argv",
    "environment_ref",
    "inputs",
    "outputs",
    "observed_source_inventory_ref",
    "observed_runtime_inventory_ref",
    "stdout_ref",
    "stderr_ref",
    "native_returncode",
    "started_ns",
    "completed_ns",
    "elapsed_ns",
    "cleanup",
}
_CHECK_INPUTS = {
    "stimuli": "original_stimulus",
    "reference": "reference_projection",
    "observed": "numerical_projection",
}
_GENERATE_OUTPUTS = {"stimuli": "original_stimulus", "reference": "reference_projection"}


def _inventory_rows(run: BoundNeuralRun, reference: object) -> list[Any]:
    """Read an observed inventory and return its rows after the closed-shape check.

    Parameters
    ----------
    run
        Complete admitted acquisition.
    reference
        Original observed inventory file reference.

    Returns
    -------
    list[Any]
        Inventory rows, not yet checked.

    Raises
    ------
    NeuralCaptureRefusalError
        If the inventory is not its closed versioned structure.
    """
    inventory = parse_json_object(
        read_neural_run_file(run.directory, reference, 1048576), "observed checker inventory"
    )
    if (
        set(inventory) != {"schema_id", "files"}
        or inventory["schema_id"] != "loop-timing-witness.checker-observed-inventory.v1"
        or not isinstance(inventory["files"], list)
    ):
        message = "Checker observed inventory requires its closed versioned structure."
        raise NeuralCaptureRefusalError(message)
    rows: list[Any] = inventory["files"]
    return rows


def _well_formed_row(item: object) -> bool:
    """Tell whether an inventory row holds exactly its four typed fields.

    Parameters
    ----------
    item
        One decoded inventory row.

    Returns
    -------
    bool
        Whether the row is an object with text ``path`` and ``actual_path``, an
        integer ``byte_length`` and a ``sha256``, and nothing else.
    """
    return (
        isinstance(item, dict)
        and set(item) == {"path", "actual_path", "sha256", "byte_length"}
        and type(item["path"]) is str
        and type(item["actual_path"]) is str
        and type(item["byte_length"]) is int
    )


def _bound_inventory(
    run: BoundNeuralRun, reference: object, expected: dict[str, dict[str, Any]]
) -> dict[str, str]:
    """Bind every portable inventory role and its original observed physical name.

    Parameters
    ----------
    run
        Complete admitted acquisition.
    reference
        Original observed inventory file reference.
    expected
        Entire source or runtime portable role map from the reviewed policy.

    Returns
    -------
    dict[str, str]
        Actual original path to portable role, for argument correspondence only.

    Raises
    ------
    NeuralCaptureRefusalError
        If closed inventory shape, whole population, role, digest or length differs.
    """
    paths = {}
    roles = set()
    for item in _inventory_rows(run, reference):
        if not _well_formed_row(item):
            message = "Checker observed inventory row is malformed."
            raise NeuralCaptureRefusalError(message)
        name = item["path"]
        if (
            name in roles
            or item["actual_path"] in paths
            or name not in expected
            or {key: item[key] for key in ("path", "sha256", "byte_length")} != expected[name]
        ):
            message = "Checker observed inventory differs from the complete reviewed roles."
            raise NeuralCaptureRefusalError(message)
        paths[item["actual_path"]] = name
        roles.add(name)
    if roles != set(expected):
        message = "Checker observed inventory omits a reviewed role."
        raise NeuralCaptureRefusalError(message)
    return paths


def _argv_matches(
    argv: object, paths: dict[str, str], policy: dict[str, Any], operation: str
) -> bool:
    """Tell whether recorded argv runs the bound entry point with the fixed arguments.

    Parameters
    ----------
    argv
        Recorded ``actual_argv`` of the receipt.
    paths
        Observed physical source path to portable role.
    policy
        Complete static reviewed checker policy.
    operation
        Fixed ``generate`` or ``check`` operation.

    Returns
    -------
    bool
        Whether argv is six texts naming the entry point and the operation's arguments.
    """
    return (
        isinstance(argv, list)
        and len(argv) == _ARGV_LENGTH
        and all(type(value) is str for value in argv)
        and paths.get(argv[0]) == policy["entry_point"]["path"]
        and argv[1:] == policy[f"{operation}_arguments"]
    )


def _environment_matches(run: BoundNeuralRun, receipt: dict[str, Any]) -> bool:
    """Tell whether the recorded environment is the closed worker profile.

    Parameters
    ----------
    run
        Complete admitted acquisition.
    receipt
        Original interpretable source execution receipt.

    Returns
    -------
    bool
        Whether every fixed variable is equal and ``TMPDIR`` is text.
    """
    environment = parse_json_object(
        read_neural_run_file(run.directory, receipt["environment_ref"], 65536),
        "actual checker environment",
    )
    expected = checker_environment(run.directory)
    return (
        set(environment) == set(expected)
        and all(environment[key] == value for key, value in expected.items() if key != "TMPDIR")
        and type(environment["TMPDIR"]) is str
    )


def _completed_cleanly(run: BoundNeuralRun, receipt: dict[str, Any], operation: str) -> bool:
    """Bind the original logs and tell whether the invocation passed and was reaped.

    Parameters
    ----------
    run
        Complete admitted acquisition, which receives both original logs.
    receipt
        Original interpretable source execution receipt.
    operation
        Fixed ``generate`` or ``check`` operation.

    Returns
    -------
    bool
        Whether the native status is zero, the group was reaped and nothing was
        written to standard error.
    """
    stdout = read_neural_run_file(run.directory, receipt["stdout_ref"], 1048576)
    stderr = read_neural_run_file(run.directory, receipt["stderr_ref"], 1048576)
    run.files[f"original_checker_{operation}_stdout"] = stdout
    run.files[f"original_checker_{operation}_stderr"] = stderr
    return receipt["native_returncode"] == 0 and receipt["cleanup"] == "reaped" and not stderr


def checker_receipt_findings(run: BoundNeuralRun, policy: dict[str, Any]) -> tuple[str, ...]:
    """Validate both complete original invocations and every referenced observation.

    Parameters
    ----------
    run
        Full admitted original acquisition, including generation and check receipts.
    policy
        Complete static reviewed checker policy.

    Returns
    -------
    tuple[str, ...]
        Reliable original receipt contradictions, separate from fresh execution.

    Raises
    ------
    NeuralCaptureRefusalError
        If receipt structure or nested byte bindings prevents interpretation.
    """
    failures = []
    source_roles = {item["path"]: item for item in policy["source_files"]}
    runtime_roles = run.contract.installation.runtime_references()
    for label, operation in (("generation", "generate"), ("check", "check")):
        receipt = _original_receipt(run.files[f"checker_{label}_receipt"])
        if (
            receipt["source_contract_ref"] != run.manifest["source_contract_ref"]
            or receipt["checker_policy_ref"] != run.contract.policy["checker_policy_ref"]
            or receipt["operation"] != operation
        ):
            failures.append(
                "Original checker invocation source or operation differs from its static binding."
            )
        paths = _bound_inventory(run, receipt["observed_source_inventory_ref"], source_roles)
        _bound_inventory(run, receipt["observed_runtime_inventory_ref"], runtime_roles)
        if not _argv_matches(receipt["actual_argv"], paths, policy, operation):
            failures.append(
                "Original source-program argv differs from the bound fixed checker operation."
            )
        if not _environment_matches(run, receipt):
            failures.append(
                "Original checker environment differs from the selected closed worker profile."
            )
        failures.extend(_input_output_findings(run, receipt, operation))
        if not _completed_cleanly(run, receipt, operation):
            failures.append(
                "Original checker invocation did not complete cleanly with a passing comparison."
            )
    return tuple(failures)


def _original_receipt(raw: bytes) -> dict[str, Any]:
    """Decode complete closed original execution status and finite timing fields.

    Parameters
    ----------
    raw
        Original source-owned invocation receipt bytes.

    Returns
    -------
    dict[str, Any]
        Structurally interpretable receipt, without claiming passing execution.

    Raises
    ------
    NeuralCaptureRefusalError
        If closed receipt shape, integer encoding or finite timing is invalid.
    """
    receipt = parse_json_object(raw, "original checker invocation")
    if (
        set(receipt) != _FIELDS
        or receipt["schema_id"] != "loop-timing-witness.sc-checker-execution.v1"
    ):
        message = "Original checker invocation requires its complete closed versioned receipt."
        raise NeuralCaptureRefusalError(message)
    integers = [
        receipt[key] for key in ("native_returncode", "started_ns", "completed_ns", "elapsed_ns")
    ]
    if (
        any(type(value) is not int for value in integers)
        or not -_NATIVE_STATUS_LIMIT <= receipt["native_returncode"] < _NATIVE_STATUS_LIMIT
        or receipt["started_ns"] <= 0
        or receipt["completed_ns"] < receipt["started_ns"]
        or not 0 <= receipt["elapsed_ns"] <= _ELAPSED_NS_LIMIT
    ):
        message = "Original checker timing and native status require exact finite integers."
        raise NeuralCaptureRefusalError(message)
    return receipt


def _input_output_findings(
    run: BoundNeuralRun,
    receipt: dict[str, Any],
    operation: str,
) -> tuple[str, ...]:
    """Bind every whole original input and output for one fixed checker operation.

    Parameters
    ----------
    run
        Full acquisition and original stimulus, oracle and producer projection.
    receipt
        Original interpretable source execution receipt.
    operation
        Consumer-selected generation or comparison role.

    Returns
    -------
    tuple[str, ...]
        Complete original byte-correspondence failures.

    Raises
    ------
    NeuralCaptureRefusalError
        If required operation roles or referenced file identities are invalid.
    """
    failures = []
    inputs = _CHECK_INPUTS if operation == "check" else {}
    outputs = _GENERATE_OUTPUTS if operation == "generate" else {}
    for name, roles in (("inputs", inputs), ("outputs", outputs)):
        if not isinstance(receipt[name], dict) or set(receipt[name]) != set(roles):
            message = "Original checker invocation lacks its complete input/output roles."
            raise NeuralCaptureRefusalError(message)
        for role, original in roles.items():
            raw = read_neural_run_file(run.directory, receipt[name][role], 65536)
            if raw != run.files[original]:
                failures.append(
                    "Original checker input/output differs from its bound whole-run role."
                )
    return tuple(failures)
