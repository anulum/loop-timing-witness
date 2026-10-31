# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — receipt, policy, reset and trace faults of a hermetic acquisition

"""Damage one receipt, policy, reset or trace fact and require one outcome in both languages.

Each fault is a refusal of the whole acquisition or a finding of one report
dimension; Python and Rust must give the same refusal or the same report.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from neural_acquisition_support import (
    CHECKER,
    build_neural_acquisition,
    edit_json,
    make_writable,
    replace_file,
)
from neural_rust_support import assert_same_outcome, python_outcome, rust_outcome

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from neural_acquisition_support import Change

_CHECK = "checker/check/"
_RECEIPT = _CHECK + "execution.json"
_INVENTORY = _CHECK + "source-inventory.json"
_NATIVE = "native-runtime.json"
_ZERO = "0" * 64
_COUNTS = "capture-counts.json"


def _set(target: str, *path: object, value: object) -> Change:
    """Return a change that assigns one nested JSON value.

    Parameters
    ----------
    target
        Within-run JSON document.
    *path
        Keys and indexes to the parent container, then the final key.
    value
        Assigned value.

    Returns
    -------
    Change
        Document rewrite.
    """

    def edit(document: Any) -> None:  # noqa: ANN401
        """Assign the value.

        Parameters
        ----------
        document
            Decoded JSON document.
        """
        for key in path[:-1]:
            document = document[key]
        document[path[-1]] = value

    return edit_json(target, edit)


def _first_entry(target: str, member: str, edit: Callable[[dict[str, Any]], None]) -> Change:
    """Return a change of the first entry of one JSON object member.

    Parameters
    ----------
    target
        Within-run JSON document.
    member
        Object member holding named entries.
    edit
        Mutates the first entry's value in place.

    Returns
    -------
    Change
        Document rewrite.
    """
    return edit_json(target, lambda value: edit(next(iter(value[member].values()))))


def _row(target: str, index: int, column: int | None, value: int = 0) -> Change:
    """Return a change of one trace row: set a column, or drop the row when ``column`` is ``None``.

    Parameters
    ----------
    target
        Within-run trace path.
    index
        Row index.
    column
        Column index, or ``None`` to remove the row.
    value
        Assigned integer.

    Returns
    -------
    Change
        Trace rewrite.
    """

    def change(name: str, raw: bytes) -> bytes:
        """Rewrite the target trace only.

        Parameters
        ----------
        name, raw
            File path and original bytes.

        Returns
        -------
        bytes
            Rewritten trace, or the original bytes.
        """
        if name != target:
            return raw
        rows = [line.split(" ") for line in raw.decode("ascii").splitlines()]
        if column is None:
            del rows[index]
        else:
            rows[index][column] = str(value)
        return "".join(" ".join(row) + "\n" for row in rows).encode("ascii")

    return change


def _duplicate_source_path(name: str, raw: bytes) -> bytes:
    """Repeat the first recorded native source path member in the raw JSON text.

    Parameters
    ----------
    name, raw
        File path and original bytes.

    Returns
    -------
    bytes
        Native runtime receipt with one repeated member name, or the original bytes.
    """
    if name != _NATIVE:
        return raw
    marker = b'"actual_source_paths": {\n'
    start = raw.index(marker) + len(marker)
    end = raw.index(b"\n", start) + 1
    return raw[:start] + raw[start:end] + raw[start:]


def _repeat_attempts(name: str, raw: bytes) -> bytes:
    """Repeat the first attempts member of the counter receipt in its raw text.

    Parameters
    ----------
    name, raw
        File path and original bytes.

    Returns
    -------
    bytes
        Counter receipt with one repeated member name, or the original bytes.
    """
    if name != _COUNTS:
        return raw
    return raw.replace(b'"attempts":', b'"attempts":0,"attempts":', 1)


def _extra_inventory_key(value: dict[str, Any]) -> None:
    """Add a member to an observed inventory.

    Parameters
    ----------
    value
        Decoded inventory.
    """
    value["extra"] = 1


def _rename_digest(value: dict[str, Any]) -> None:
    """Replace the first inventory row's digest member with another member.

    Parameters
    ----------
    value
        Decoded inventory.
    """
    row = value["files"][0]
    row["other"] = row.pop("sha256")


def _repeat_role(value: dict[str, Any]) -> None:
    """Repeat the first inventory row.

    Parameters
    ----------
    value
        Decoded inventory.
    """
    value["files"].append(dict(value["files"][0]))


def _repeat_path(value: dict[str, Any]) -> None:
    """Give the second inventory row the first row's actual path.

    Parameters
    ----------
    value
        Decoded inventory.
    """
    value["files"][1]["actual_path"] = value["files"][0]["actual_path"]


def _repeat_source(value: dict[str, Any]) -> None:
    """Repeat the first declared source reference.

    Parameters
    ----------
    value
        Decoded manifest.
    """
    value["source_files"].append(dict(value["source_files"][0]))


def _longer(value: dict[str, Any]) -> None:
    """Add one byte to a reference's declared length.

    Parameters
    ----------
    value
        Decoded file reference.
    """
    value["byte_length"] += 1


def _other_path(value: dict[str, Any]) -> None:
    """Point the first recorded native source path at another admitted path.

    Parameters
    ----------
    value
        Decoded native runtime receipt.
    """
    paths = value["actual_source_paths"]
    first, second = list(paths)[:2]
    paths[first] = paths[second]


def _artifact_digest(value: dict[str, Any]) -> None:
    """Change the first compiled artifact's digest.

    Parameters
    ----------
    value
        Decoded artifact reference.
    """
    value["sha256"] = _ZERO


def _extra_environment(value: dict[str, Any]) -> None:
    """Add a variable to a recorded checker environment.

    Parameters
    ----------
    value
        Decoded environment.
    """
    value["EXTRA"] = "1"


def _longer_checker_source(value: dict[str, Any]) -> None:
    """Add one byte to the declared length of a checker source.

    Parameters
    ----------
    value
        Decoded checker policy.
    """
    value["source_files"][1]["byte_length"] += 1


def _pop_job(value: dict[str, Any]) -> None:
    """Remove the last recorded native job.

    Parameters
    ----------
    value
        Decoded native runtime receipt.
    """
    value["jobs"].pop()


def _execution_first(value: dict[str, Any]) -> None:
    """Give the first native job the execution job's shape.

    Parameters
    ----------
    value
        Decoded native runtime receipt.
    """
    value["jobs"][0] = dict(value["jobs"][4])


def _both(first: Change, second: Change) -> Change:
    """Apply two changes in order.

    Parameters
    ----------
    first, second
        File changes.

    Returns
    -------
    Change
        Combined change.
    """
    return lambda name, raw: second(name, first(name, raw))


def _same_later_cohort(value: dict[str, Any]) -> None:
    """Admit the reset epoch's cohort with the original epoch's objects.

    Parameters
    ----------
    value
        Decoded source policy.
    """
    artifacts = value["compiled_artifacts"]
    artifacts["0,0,0,10:1"] = artifacts["0,0,0,10:0"]


def _without_language(value: dict[str, Any]) -> None:
    """Remove the explicit language selection from the elaboration command.

    Parameters
    ----------
    value
        Decoded native runtime receipt.
    """
    command = value["jobs"][0]["command"]
    index = command.index("--language")
    del command[index : index + 2]


def _artifact_path(value: dict[str, Any]) -> None:
    """Rename the first compiled artifact reference.

    Parameters
    ----------
    value
        Decoded artifact reference.
    """
    value["path"] = "other.bin"


def _without_flag(job: int, flag: str) -> Callable[[dict[str, Any]], None]:
    """Return an edit removing one argument from one native job command.

    Parameters
    ----------
    job
        Job index.
    flag
        Removed argument.

    Returns
    -------
    Callable[[dict[str, Any]], None]
        Native runtime edit.
    """

    def edit(value: dict[str, Any]) -> None:
        """Remove the argument.

        Parameters
        ----------
        value
            Decoded native runtime receipt.
        """
        value["jobs"][job]["command"].remove(flag)

    return edit


def _without_native_source(value: dict[str, Any]) -> None:
    """Compile the native program without its recorded producer source.

    Parameters
    ----------
    value
        Decoded native runtime receipt.
    """
    paths = value["actual_source_paths"]
    actual = next(key for key, role in paths.items() if role == "native/native_trial.cpp")
    value["jobs"][2]["command"].remove(actual)


def _longer_entry(value: dict[str, Any]) -> None:
    """Declare an entry point that is not one of the checker sources.

    Parameters
    ----------
    value
        Decoded checker policy.
    """
    value["entry_point"]["byte_length"] += 1


def _pop_source(value: dict[str, Any]) -> None:
    """Remove the last recorded native source reference.

    Parameters
    ----------
    value
        Decoded native runtime receipt.
    """
    value["source_files"].pop()


def _first_row_only(name: str, raw: bytes) -> bytes:
    """Keep only the first abandoned input row.

    Parameters
    ----------
    name, raw
        File path and original bytes.

    Returns
    -------
    bytes
        Shortened prefix trace, or the original bytes.
    """
    return raw.splitlines(keepends=True)[0] if name == "prefix/input.txt" else raw


_OTHER_GENERATION = CHECKER.replace(
    'Path("stimuli.txt").write_bytes(stimuli)', 'Path("stimuli.txt").write_bytes(stimuli + b"0")'
).encode()
_FAILED_GENERATION = (
    b"import sys\nif sys.argv[1] == '--generate':\n    sys.exit(3)\n" + CHECKER.encode()
)

_CASES: dict[str, tuple[dict[str, Any], str, str]] = {
    "counts-json": (
        {"change": replace_file(_COUNTS, b"{")},
        "refusal",
        "Invalid original neural capture counts.",
    ),
    "counts-repeated-member": (
        {"change": _repeat_attempts},
        "refusal",
        "Invalid original neural capture counts.",
    ),
    "counts-schema": (
        {"change": _set(_COUNTS, "schema_id", value="other")},
        "refusal",
        "Invalid neural capture counter receipt schema.",
    ),
    "counts-extra": (
        {"change": _set(_COUNTS, "extra", value=0)},
        "refusal",
        "Invalid neural capture counter receipt schema.",
    ),
    "counts-width-zero": (
        {"change": _set(_COUNTS, "drop_counter_bits", value=0)},
        "refusal",
        "Invalid neural capture counter width.",
    ),
    "counts-width-large": (
        {"change": _set(_COUNTS, "drop_counter_bits", value=33)},
        "refusal",
        "Invalid neural capture counter: drop_counter_bits.",
    ),
    "counts-width-flag": (
        {"change": _set(_COUNTS, "drop_counter_bits", value=True)},
        "refusal",
        "Invalid neural capture counter: drop_counter_bits.",
    ),
    "counts-channels-object": (
        {"change": _set(_COUNTS, "channels", value={})},
        "refusal",
        "requires three channels",
    ),
    "counts-channels-empty": (
        {"change": _set(_COUNTS, "channels", value=[])},
        "refusal",
        "requires three channels",
    ),
    "counts-channel-null": (
        {"change": _set(_COUNTS, "channels", 0, value=None)},
        "refusal",
        "Invalid neural capture counter channel: input.",
    ),
    "counts-role": (
        {"change": _set(_COUNTS, "channels", 0, "role", value="service")},
        "refusal",
        "Invalid neural capture counter channel: input.",
    ),
    "counts-channel-extra": (
        {"change": _set(_COUNTS, "channels", 0, "extra", value=0)},
        "refusal",
        "Invalid neural capture counter channel: input.",
    ),
    "counts-overflow-type": (
        {"change": _set(_COUNTS, "channels", 0, "overflowed", value=0)},
        "refusal",
        "Invalid neural capture overflow flag: input.",
    ),
    "counts-attempts-flag": (
        {"change": _set(_COUNTS, "channels", 0, "attempts", value=True)},
        "refusal",
        "Invalid neural capture counter: input.attempts.",
    ),
    "counts-attempts-negative": (
        {"change": _set(_COUNTS, "channels", 0, "attempts", value=-1)},
        "refusal",
        "Invalid neural capture counter: input.attempts.",
    ),
    "counts-accepted-range": (
        {"change": _set(_COUNTS, "channels", 0, "accepted", value=1 << 64)},
        "refusal",
        "Invalid neural capture counter: input.accepted.",
    ),
    "counts-dropped-range": (
        {"change": _set(_COUNTS, "channels", 0, "dropped", value=2**32)},
        "refusal",
        "Invalid neural capture counter: input.dropped.",
    ),
    "counts-drained-decimal": (
        {"change": _set(_COUNTS, "channels", 0, "drained", value=1.0)},
        "refusal",
        "Invalid neural capture counter: input.drained.",
    ),
    "counts-drop-without-overflow": (
        {"change": _set("capture-counts.json", "channels", 0, "dropped", value=1)},
        "capture",
        "input: overflow flag and drop counter disagree",
    ),
    "model-checker-json": (
        {"change": replace_file("original-model-checker.json", b"[]")},
        "refusal",
        "historical source checker",
    ),
    "model-checker-rows-range": (
        {"change": _set("original-model-checker.json", "rows", value=65536)},
        "refusal",
        "Invalid complete actual receipt: historical source checker",
    ),
    "model-checker-spikes-range": (
        {"change": _set("original-model-checker.json", "spikes", value=65536)},
        "refusal",
        "Invalid complete actual receipt: historical source checker",
    ),
    "model-checker-rows": (
        {"change": _set("original-model-checker.json", "rows", value=999)},
        "source_binding",
        "Historical source checker binding differs: rows",
    ),
    "model-checker-pass": (
        {
            "change": _set(
                "original-model-checker.json", "source_owned_public_checker_pass", value=False
            )
        },
        "source_binding",
        "binding differs: source_owned_public_checker_pass",
    ),
    "model-checker-type": (
        {"change": _set("original-model-checker.json", "rows", value="1000")},
        "refusal",
        "Invalid complete actual receipt: historical source checker.",
    ),
    "completion-type": (
        {"change": _set("completion.json", "pending_empty", value=1)},
        "refusal",
        "Invalid complete actual receipt: producer completion.",
    ),
    "clock-type": (
        {"change": _set("clock-schedule.json", "first_input_tick", value="20")},
        "refusal",
        "Invalid complete actual receipt: native clock.",
    ),
    "reset-type": (
        {"epoch": 1, "change": _set("reset-epoch.json", "prefix_attempts", value=[4, 3])},
        "refusal",
        "Invalid complete actual receipt: actual joint reset.",
    ),
    "completion-range": (
        {"change": _set("completion.json", "final_counter", value=70000)},
        "refusal",
        "Invalid complete actual receipt: producer completion",
    ),
    "completion-service-quiescent": (
        {"change": _set("completion.json", "service_quiescent", value=False)},
        "completion",
        "not finalized and quiescent",
    ),
    "completion-pipeline-quiescent": (
        {"change": _set("completion.json", "pipeline_quiescent", value=False)},
        "completion",
        "not finalized and quiescent",
    ),
    "completion-drain": (
        {"change": _set("completion.json", "drain_complete", value=False)},
        "completion",
        "not finalized and quiescent",
    ),
    "clock-range": (
        {"change": _set("clock-schedule.json", "capture_half_period_units", value=70000)},
        "refusal",
        "Invalid complete actual receipt: native clock",
    ),
    "clock-precision-range": (
        {"change": _set("clock-schedule.json", "driver_half_period_precision_ticks", value=70000)},
        "refusal",
        "Invalid complete actual receipt: native clock",
    ),
    "clock-producer-length-range": (
        {"change": _set("clock-schedule.json", "source_producer", "byte_length", value=70000)},
        "refusal",
        "Invalid complete actual receipt: native clock",
    ),
    "clock-producer-digest-length": (
        {"change": _set("clock-schedule.json", "source_producer", "sha256", value="0" * 63)},
        "refusal",
        "Invalid complete actual receipt: native clock",
    ),
    "clock-producer-digest-hex": (
        {"change": _set("clock-schedule.json", "source_producer", "sha256", value="g" * 64)},
        "refusal",
        "Invalid complete actual receipt: native clock",
    ),
    "clock-producer-path": (
        {"change": _set("clock-schedule.json", "source_producer", "path", value="other")},
        "refusal",
        "native clock/source/precision differs",
    ),
    "clock-producer-digest": (
        {"change": _set("clock-schedule.json", "source_producer", "sha256", value=_ZERO)},
        "refusal",
        "native clock/source/precision differs",
    ),
    "clock-producer-length": (
        {"change": _set("clock-schedule.json", "source_producer", "byte_length", value=1)},
        "refusal",
        "native clock/source/precision differs",
    ),
    "clock-time-unit": (
        {"change": _set("clock-schedule.json", "simulation_time_unit", value="1us")},
        "clock",
        "schedule differs: simulation_time_unit",
    ),
    "native-paths-shape": (
        {"change": _set(_NATIVE, "actual_source_paths", value=[])},
        "refusal",
        "Invalid complete actual receipt: native runtime.",
    ),
    "native-paths-duplicate": (
        {"change": _duplicate_source_path},
        "refusal",
        "Invalid original native runtime.",
    ),
    "native-dialect": (
        {"change": _set(_NATIVE, "dialect", value="other")},
        "refusal",
        "Unsupported actual native backend or dialect",
    ),
    "native-parameter-range": (
        {"change": _set(_NATIVE, "parameters", "ADDRESS_BITS", value=70000)},
        "refusal",
        "Invalid complete actual receipt: native runtime.",
    ),
    "native-epoch-range": (
        {"change": _set(_NATIVE, "epoch", value=70000)},
        "refusal",
        "Invalid complete actual receipt: native runtime.",
    ),
    "native-steps-range": (
        {"change": _set(_NATIVE, "steps", value=70000)},
        "refusal",
        "Invalid complete actual receipt: native runtime.",
    ),
    "native-job-population": (
        {"change": edit_json(_NATIVE, _pop_job)},
        "refusal",
        "Invalid complete actual receipt: native runtime.",
    ),
    "native-job-shape": (
        {"change": edit_json(_NATIVE, _execution_first)},
        "refusal",
        "Invalid complete actual receipt: native runtime.",
    ),
    "native-command-empty": (
        {"change": _set(_NATIVE, "jobs", 0, "command", value=[])},
        "refusal",
        "Invalid complete actual receipt: native runtime.",
    ),
    "native-file-length": (
        {"change": _set(_NATIVE, "source_files", 0, "byte_length", value=8 * 1024 * 1024 + 1)},
        "refusal",
        "Invalid complete actual receipt: native runtime.",
    ),
    "native-field-type": (
        {"change": _set(_NATIVE, "epoch", value="0")},
        "refusal",
        "Invalid complete actual receipt: native runtime.",
    ),
    "native-artifact": (
        {"change": _first_entry(_NATIVE, "compiled_artifacts", _artifact_digest)},
        "refusal",
        "compiled artifact cohort",
    ),
    "native-source-population": (
        {"change": edit_json(_NATIVE, _pop_source)},
        "refusal",
        "Invalid complete actual receipt: native runtime.",
    ),
    "native-path-target": (
        {"change": edit_json(_NATIVE, _other_path)},
        "refusal",
        "source path population differs",
    ),
    "manifest-source-repeat": (
        {"change": edit_json("run.json", _repeat_source)},
        "refusal",
        "Neural source references contain a duplicate path.",
    ),
    "manifest-source-length": (
        {"change": edit_json("run.json", lambda value: _longer(value["source_files"][0]))},
        "refusal",
        "source reference differs from its reviewed policy",
    ),
    "checker-source-length": (
        {"change": edit_json("checker-policy.json", _longer_checker_source)},
        "refusal",
        "Original whole length/SHA-256 differs:",
    ),
    "inventory-extra-key": (
        {"change": edit_json(_INVENTORY, _extra_inventory_key)},
        "refusal",
        "closed versioned structure",
    ),
    "inventory-row-extra": (
        {"change": _set(_INVENTORY, "files", 0, "extra", value=1)},
        "refusal",
        "inventory row is malformed",
    ),
    "inventory-row-path": (
        {"change": _set(_INVENTORY, "files", 0, "path", value=1)},
        "refusal",
        "inventory row is malformed",
    ),
    "inventory-row-actual": (
        {"change": _set(_INVENTORY, "files", 0, "actual_path", value=1)},
        "refusal",
        "inventory row is malformed",
    ),
    "inventory-row-digest-member": (
        {"change": edit_json(_INVENTORY, _rename_digest)},
        "refusal",
        "inventory row is malformed",
    ),
    "inventory-row-large-length": (
        {"change": _set(_INVENTORY, "files", 0, "byte_length", value=2**63)},
        "refusal",
        "differs from the complete reviewed roles",
    ),
    "inventory-row-repeat-role": (
        {"change": edit_json(_INVENTORY, _repeat_role)},
        "refusal",
        "differs from the complete reviewed roles",
    ),
    "inventory-row-repeat-path": (
        {"change": edit_json(_INVENTORY, _repeat_path)},
        "refusal",
        "differs from the complete reviewed roles",
    ),
    "receipt-json": (
        {"change": replace_file(_RECEIPT, b"[]")},
        "refusal",
        "checker invocation",
    ),
    "receipt-completed-before-start": (
        {"change": _set(_RECEIPT, "completed_ns", value=500_000_000)},
        "refusal",
        "exact finite integers",
    ),
    "receipt-elapsed": (
        {"change": _set(_RECEIPT, "elapsed_ns", value=45_000_000_001)},
        "refusal",
        "exact finite integers",
    ),
    "receipt-source-reference": (
        {"change": _set(_RECEIPT, "source_contract_ref", "sha256", value=_ZERO)},
        "source_binding",
        "source or operation differs",
    ),
    "receipt-policy-reference": (
        {"change": _set(_RECEIPT, "checker_policy_ref", "sha256", value=_ZERO)},
        "source_binding",
        "source or operation differs",
    ),
    "receipt-argv-length": (
        {"change": edit_json(_RECEIPT, lambda value: value["actual_argv"].append("x"))},
        "source_binding",
        "argv differs",
    ),
    "receipt-argv-entry": (
        {"change": _set(_RECEIPT, "actual_argv", 0, value="/image/other.py")},
        "source_binding",
        "argv differs",
    ),
    "receipt-environment-json": (
        {"change": replace_file(_CHECK + "environment.json", b"[]")},
        "refusal",
        "checker environment",
    ),
    "receipt-environment-extra": (
        {"change": edit_json(_CHECK + "environment.json", _extra_environment)},
        "source_binding",
        "environment differs",
    ),
    "receipt-environment-tmpdir": (
        {"change": _set(_CHECK + "environment.json", "TMPDIR", value=1)},
        "source_binding",
        "environment differs",
    ),
    "receipt-stderr": (
        {"change": replace_file(_CHECK + "checker.stderr", b"x")},
        "source_binding",
        "did not complete cleanly",
    ),
    "policy-schema": (
        {"change": _set("source-contract.json", "schema_id", value="other")},
        "refusal",
        "does not implement its closed contract",
    ),
    "policy-schema-digest": (
        {"change": _set("source-contract.json", "schema_sha256", value=_ZERO)},
        "refusal",
        "does not implement its closed contract",
    ),
    "policy-cohort": (
        {"change": _set("source-contract.json", "cohort", value="other")},
        "refusal",
        "does not implement its closed contract",
    ),
    "policy-sources-empty": (
        {"change": _set("source-contract.json", "sources", value={})},
        "refusal",
        "does not implement its closed contract",
    ),
    "policy-artifacts-empty": (
        {"change": _set("source-contract.json", "compiled_artifacts", value={})},
        "refusal",
        "does not implement its closed contract",
    ),
    "checker-policy-schema": (
        {"change": _set("checker-policy.json", "schema_id", value="other")},
        "refusal",
        "complete closed fixed-operation policy",
    ),
    "checker-policy-runtime-reference": (
        {"change": _set("checker-policy.json", "runtime_contract_ref", "sha256", value=_ZERO)},
        "refusal",
        "runtime",
    ),
    "tool-extra-key": (
        {"change": _set("tool-receipt.json", "extra", value=1)},
        "refusal",
        "complete closed successor",
    ),
    "tool-schema": (
        {"change": _set("tool-receipt.json", "schema_id", value="other")},
        "refusal",
        "complete closed successor",
    ),
    "tool-counter-reference": (
        {"change": _set("tool-receipt.json", "counter_receipt", "sha256", value=_ZERO)},
        "refusal",
        "capture-counts.json",
    ),
    "tool-generation-reference": (
        {
            "change": _set(
                "tool-receipt.json", "checker_receipts", "generation", "sha256", value=_ZERO
            )
        },
        "refusal",
        "checker/generate/execution.json",
    ),
    "reset-tool-counter-reference": (
        {
            "epoch": 1,
            "change": _set("tool-receipt.json", "counter_receipt", "sha256", value=_ZERO),
        },
        "refusal",
        "capture-counts.json",
    ),
    "reset-receipt-reference": (
        {
            "epoch": 1,
            "change": _set("tool-receipt.json", "reset_epoch_receipt", "sha256", value=_ZERO),
        },
        "refusal",
        "reset-epoch.json",
    ),
    "reset-range": (
        {"epoch": 1, "change": _set("reset-epoch.json", "counter_before_reset", value=70000)},
        "refusal",
        "Invalid complete actual receipt: actual joint reset",
    ),
    "prefix-numerical-malformed": (
        {"epoch": 1, "change": replace_file("prefix/numerical.txt", b"x\n")},
        "refusal",
        "Malformed original abandoned numerical trace row",
    ),
    "prefix-raw-malformed": (
        {"epoch": 1, "change": replace_file("prefix/raw_spike.txt", b"x\n")},
        "refusal",
        "Malformed original abandoned raw_spike trace row",
    ),
    "prefix-service-malformed": (
        {"epoch": 1, "change": replace_file("prefix/service.txt", b"x\n")},
        "refusal",
        "Malformed original abandoned service trace row",
    ),
    "prefix-input-phase": (
        {"epoch": 1, "change": _row("prefix/input.txt", 0, 6, 99)},
        "completion",
        "Abandoned input 0",
    ),
    "prefix-numerical-phase": (
        {"epoch": 1, "change": _row("prefix/numerical.txt", 0, 4, 99)},
        "completion",
        "Abandoned numerical 0",
    ),
    "prefix-raw-flag": (
        {"epoch": 1, "change": _row("prefix/raw_spike.txt", 0, 2, 1)},
        "completion",
        "Abandoned raw spike 0",
    ),
    "prefix-input-short": (
        {"epoch": 1, "change": _first_row_only},
        "completion",
        "did not establish the selected queued/inflight/pending reset",
    ),
    "prefix-numerical-short": (
        {"epoch": 1, "change": _row("prefix/numerical.txt", -1, None)},
        "completion",
        "did not establish the selected queued/inflight/pending reset",
    ),
    "prefix-raw-short": (
        {"epoch": 1, "change": _row("prefix/raw_spike.txt", -1, None)},
        "completion",
        "did not establish the selected queued/inflight/pending reset",
    ),
    "prefix-raw-spikes": (
        {"epoch": 1, "change": _set("reset-epoch.json", "prefix_raw_spikes", value=2)},
        "completion",
        "did not establish the selected queued/inflight/pending reset",
    ),
    "numerical-oracle": (
        {"change": _row("numerical.txt", 0, 3, 7)},
        "numerical",
        "Numerical step 0: original oracle differs",
    ),
    "raw-flag": (
        {"change": _row("raw-spikes.txt", 0, 2, 1)},
        "source_binding",
        "Raw step 0: original spike or source phase differs",
    ),
    "clock-driver-precision": (
        {"change": _set("clock-schedule.json", "driver_half_period_precision_ticks", value=4000)},
        "refusal",
        "native clock/source/precision differs",
    ),
    "clock-final-counter-low": (
        {"change": _set("completion.json", "final_counter", value=1000)},
        "clock",
        "final counter does not fit",
    ),
    "native-cpp-version": (
        {"change": _set(_NATIVE, "tool_versions", "g++", value="other")},
        "source_binding",
        "compiler versions differ",
    ),
    "native-epoch-identity": (
        {
            "change": _both(
                edit_json("source-contract.json", _same_later_cohort),
                _set(_NATIVE, "epoch", value=1),
            )
        },
        "source_binding",
        "identity/configuration differs",
    ),
    "manifest-fifo": (
        {"change": _set("run.json", "fifo_capacity_records", value=8)},
        "source_binding",
        "identity/configuration differs",
    ),
    "native-language": (
        {"change": edit_json(_NATIVE, _without_language)},
        "source_binding",
        "compiler/dialect/run arguments differ",
    ),
    "receipt-cleanup": (
        {"change": _set(_RECEIPT, "cleanup", value="killed")},
        "source_binding",
        "did not complete cleanly",
    ),
    "checker-policy-check-arguments": (
        {"change": _set("checker-policy.json", "check_arguments", value=["--check"])},
        "refusal",
        "complete closed fixed-operation policy",
    ),
    "checker-policy-sources-empty": (
        {"change": _set("checker-policy.json", "source_files", value=[])},
        "refusal",
        "complete closed fixed-operation policy",
    ),
    "checker-policy-entry-outside": (
        {"change": edit_json("checker-policy.json", _longer_entry)},
        "refusal",
        "complete closed fixed-operation policy",
    ),
    "generation-differs": (
        {"program": _OTHER_GENERATION},
        "source_binding",
        "generation differs from the bound original fixture",
    ),
    "generation-fails": (
        {"program": _FAILED_GENERATION},
        "numerical",
        "refused the complete selected projection",
    ),
    "native-artifact-path": (
        {"change": _first_entry(_NATIVE, "compiled_artifacts", _artifact_path)},
        "refusal",
        "compiled artifact cohort",
    ),
    "native-generic-default": (
        {"change": edit_json(_NATIVE, lambda value: value["jobs"][0]["command"].append("-GX=0"))},
        "source_binding",
        "compiler/dialect/run arguments differ",
    ),
    "native-verilator-flag": (
        {"change": edit_json(_NATIVE, _without_flag(0, "--cc"))},
        "source_binding",
        "compiler/dialect/run arguments differ",
    ),
    "native-cpp-source": (
        {"change": edit_json(_NATIVE, _without_native_source)},
        "source_binding",
        "compiler/dialect/run arguments differ",
    ),
    "native-run-mode": (
        {"change": _set(_NATIVE, "jobs", 4, "command", -1, value="reset")},
        "source_binding",
        "compiler/dialect/run arguments differ",
    ),
    "native-stderr": (
        {"change": replace_file("stderr.log", b"x")},
        "completion",
        "publication did not finalise cleanly",
    ),
    "native-execution-status": (
        {"change": _set(_NATIVE, "jobs", 4, "returncode", value=1)},
        "completion",
        "publication did not finalise cleanly",
    ),
}


@pytest.mark.parametrize("fault", list(_CASES))
def test_receipt_fault_has_one_outcome_in_both(tmp_path: Path, fault: str) -> None:
    """Require the same refusal or dimension finding in both languages.

    Parameters
    ----------
    tmp_path
        Owned acquisition directory.
    fault
        Named single fault.
    """
    options, kind, message = _CASES[fault]
    acquisition = build_neural_acquisition(tmp_path / "run", **options)
    try:
        python: dict[str, Any] = python_outcome(acquisition)
        assert_same_outcome(python, rust_outcome(acquisition, tmp_path / "rust"))
    finally:
        make_writable(tmp_path)
    if kind == "refusal":
        assert message in python.get("refusal", ""), python.get("refusal", python)
    else:
        findings = python["report"][kind]["findings"]
        assert any(message in finding for finding in findings), findings
        assert python["report"]["verification"]["whole"] is False
