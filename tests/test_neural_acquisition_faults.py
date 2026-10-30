# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — single faults of a complete hermetic neural acquisition

"""Damage one fact of a complete acquisition and require its exact consequence."""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING, Any

import pytest
from neural_acquisition_support import (
    CHECKER,
    build_neural_acquisition,
    edit_json,
    make_writable,
    replace_file,
    sha,
    simulation_file,
)

from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError
from loop_timing_witness.neural_run_api import build_neural_run_report, load_neural_run

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from neural_acquisition_support import Change

_GENERATE = "checker/generate/execution.json"
_CHECK = "checker/check/execution.json"
_NATIVE = "native-runtime.json"


def _set(*path: object, value: object) -> Callable[[Any], None]:
    """Return an edit that assigns one nested JSON value.

    Parameters
    ----------
    *path
        Keys and indexes to the parent container, then the final key.
    value
        Assigned value.

    Returns
    -------
    Callable[[Any], None]
        In-place edit.
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

    return edit


def _reference(name: str, raw: bytes) -> dict[str, Any]:
    """Return a closed file reference.

    Parameters
    ----------
    name
        Within-run path.
    raw
        Complete bytes.

    Returns
    -------
    dict[str, Any]
        Path, digest and length.
    """
    return {"path": name, "sha256": sha(raw), "byte_length": len(raw)}


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


def _row(target: str, index: int, column: int | None, value: int | None = None) -> Change:
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


def _ticks(stem: str, record: int, ticks: int) -> Change:
    """Return a change of one capture record's tick in the channel and its projection.

    Parameters
    ----------
    stem
        ``markers`` for the start marker, ``payload`` for the first data record.
    record
        Record index in the channel capture.
    ticks
        Assigned tick count.

    Returns
    -------
    Change
        Capture rewrite that keeps the projection file consistent.
    """

    def change(name: str, raw: bytes) -> bytes:
        """Rewrite the input channel capture and the matching projection record.

        Parameters
        ----------
        name, raw
            File path and original bytes.

        Returns
        -------
        bytes
            Rewritten capture or projection, or the original bytes.
        """
        index = {"channel-0.bin": record, f"{stem}-0.bin": 0}.get(name)
        if index is None:
            return raw
        data = bytearray(raw)
        struct.pack_into("<Q", data, index * 16 + 8, ticks)
        return bytes(data)

    return change


_STIMULI = simulation_file("stimuli.txt")
_OTHER_STIMULI = _STIMULI.replace(b"20 256 0 -26\n", b"20 256 0 -25\n", 1)
_EXTRA_COHORT = "1,0,0,10:0"

_REFUSALS: dict[str, tuple[Change, str]] = {
    "manifest-source-population": (
        edit_json("run.json", lambda value: value["source_files"].pop()),
        "source population differs from its reviewed policy",
    ),
    "manifest-source-reference": (
        edit_json("run.json", _set("source_files", 0, "sha256", value="0" * 64)),
        "source reference differs from its reviewed policy",
    ),
    "body-pin": (
        edit_json("run.json", _set("sc_body_pins", "hdl/sc_lif_neuron.v", value="0" * 64)),
        "SC body pin differs",
    ),
    "tool-scope": (
        edit_json("tool-receipt.json", _set("scope", value=1)),
        "complete closed successor",
    ),
    "tool-checker-receipts": (
        edit_json("tool-receipt.json", lambda value: value["checker_receipts"].pop("check")),
        "both actual checker invocations",
    ),
    "fixture-pin": (
        replace_file("stimuli.txt", _OTHER_STIMULI),
        "fixture differs from the selected source contract",
    ),
    "source-stimulus": (
        _both(
            replace_file("stimuli.txt", _OTHER_STIMULI),
            edit_json(
                "tool-receipt.json",
                _set(
                    "original_stimulus",
                    value=_reference("checker/generate/stimuli.txt", _STIMULI),
                ),
            ),
        ),
        "source stimulus differs from its identified input binding",
    ),
    "checker-policy-form": (
        edit_json("checker-policy.json", _set("generate_arguments", value=["--generate"])),
        "complete closed fixed-operation policy",
    ),
    "checker-policy-unbound-source": (
        edit_json(
            "checker-policy.json",
            lambda value: value["source_files"].append(value["runtime_contract_ref"]),
        ),
        "closure differs from the admitted whole source population",
    ),
    "checker-policy-duplicate": (
        edit_json(
            "checker-policy.json", lambda value: value["source_files"].append(value["entry_point"])
        ),
        "closure contains duplicate roles",
    ),
    "checker-execution-contract": (
        edit_json("checker-policy.json", _set("execution_contract", value={"profile": "other"})),
        "runtime differs from the complete selected installation",
    ),
    "inventory-schema": (
        edit_json("checker/generate/source-inventory.json", _set("schema_id", value="other")),
        "closed versioned structure",
    ),
    "inventory-row": (
        edit_json(
            "checker/generate/source-inventory.json", _set("files", 0, "byte_length", value="1")
        ),
        "inventory row is malformed",
    ),
    "inventory-role": (
        edit_json(
            "checker/generate/source-inventory.json", _set("files", 0, "sha256", value="0" * 64)
        ),
        "differs from the complete reviewed roles",
    ),
    "inventory-omits": (
        edit_json("checker/check/runtime-inventory.json", lambda value: value["files"].pop()),
        "omits a reviewed role",
    ),
    "receipt-schema": (
        edit_json(_GENERATE, _set("schema_id", value="other")),
        "complete closed versioned receipt",
    ),
    "receipt-timing": (
        edit_json(_CHECK, _set("started_ns", value=0)),
        "exact finite integers",
    ),
    "receipt-roles": (
        edit_json(_CHECK, _set("inputs", value=[])),
        "complete input/output roles",
    ),
    "native-backend": (
        edit_json(_NATIVE, _set("backend", value="other")),
        "Unsupported actual native backend",
    ),
    "native-cohort": (
        edit_json(_NATIVE, _set("parameters", "ADDRESS_BITS", value=3)),
        "compiled artifact cohort",
    ),
    "native-sources": (
        edit_json(_NATIVE, _set("source_files", 0, "path", value="other")),
        "source references differ from root",
    ),
    "native-paths": (
        edit_json(_NATIVE, lambda value: value["actual_source_paths"].popitem()),
        "source path population differs",
    ),
    "native-jobs": (
        edit_json(_NATIVE, _set("jobs", 1, "kind", value="other")),
        "command sequence differs",
    ),
    "trace-population": (_row("numerical.txt", -1, None), "Complete requested population"),
    "trace-sequence": (_row("input.txt", 0, 1, 5), "epoch/step sequence differs: input_trace"),
    "trace-stimulus-range": (_row("input.txt", 0, 3, 70000), "signed16 stimulus outside range"),
    "trace-state-range": (_row("numerical.txt", 0, 2, 2), "binary spike/signed16 state"),
    "trace-raw-range": (_row("raw-spikes.txt", 0, 2, 2), "raw spike outside binary range"),
    "trace-horizon": (_row("service.txt", 0, 4, 5000), "outside no-wrap horizon"),
    "trace-service-identity": (_row("service.txt", 0, 2, 1), "neuron identity sequence"),
    "trace-service-timestamp": (_row("service.txt", 0, 3, 70000), "outside unsigned16 range"),
    "native-clock": (
        edit_json("clock-schedule.json", _set("simulation_time_precision", value="1ns")),
        "native clock/source/precision differs",
    ),
}


@pytest.mark.parametrize("fault", list(_REFUSALS))
def test_uninterpretable_fault_refuses_the_whole_acquisition(tmp_path: Path, fault: str) -> None:
    """Refuse an acquisition whose damaged fact prevents interpretation.

    Parameters
    ----------
    tmp_path
        Owned acquisition directory.
    fault
        Named single fault.
    """
    change, message = _REFUSALS[fault]
    acquisition = build_neural_acquisition(tmp_path / "run", change=change)
    try:
        with pytest.raises(NeuralCaptureRefusalError, match=message):
            load_neural_run(acquisition.manifest, registry=acquisition.registry)
    finally:
        make_writable(tmp_path)


def test_reset_requires_all_abandoned_prefix_traces(tmp_path: Path) -> None:
    """Refuse a reset acquisition that omits one abandoned prefix trace.

    Parameters
    ----------
    tmp_path
        Owned acquisition directory.
    """
    change = edit_json(
        "tool-receipt.json", lambda value: value["abandoned_prefix_traces"].pop("service")
    )
    acquisition = build_neural_acquisition(tmp_path / "run", epoch=1, change=change)
    try:
        with pytest.raises(NeuralCaptureRefusalError, match="all four original abandoned-prefix"):
            load_neural_run(acquisition.manifest, registry=acquisition.registry)
    finally:
        make_writable(tmp_path)


@pytest.mark.parametrize(
    ("program", "message"),
    [
        (b"import os\nos._exit(0)\n", "Actual checker output is unavailable"),
        (b"import os\nos.mkfifo('stimuli.txt')\n", "Actual checker output must be a regular file"),
        (b"open('stimuli.txt', 'wb').write(bytes(65537))\n", "output exceeds its allocation"),
    ],
)
def test_generated_output_must_be_a_bounded_regular_file(
    tmp_path: Path, program: bytes, message: str
) -> None:
    """Refuse generated output that is absent, nonregular or excessive.

    Parameters
    ----------
    tmp_path
        Owned acquisition directory.
    program
        Checker program that exits successfully with damaged output.
    message
        Expected refusal fragment.
    """
    acquisition = build_neural_acquisition(tmp_path / "run", program=program)
    try:
        with pytest.raises(NeuralCaptureRefusalError, match=message):
            load_neural_run(acquisition.manifest, registry=acquisition.registry)
    finally:
        make_writable(tmp_path)


def test_malformed_receipt_json_is_a_named_refusal(tmp_path: Path) -> None:
    """Refuse a receipt that is not a JSON object by naming the receipt.

    Parameters
    ----------
    tmp_path
        Owned acquisition directory.
    """
    acquisition = build_neural_acquisition(tmp_path / "run", change=replace_file(_NATIVE, b"[]"))
    try:
        with pytest.raises(NeuralCaptureRefusalError, match="native runtime"):
            load_neural_run(acquisition.manifest, registry=acquisition.registry)
    finally:
        make_writable(tmp_path)


def _completion() -> bytes:
    """Return the original completion receipt bytes.

    Returns
    -------
    bytes
        Exact original receipt.
    """
    return simulation_file("completion.json")


def _extra_cohort(value: dict[str, Any]) -> None:
    """Admit a second compile cohort with the original objects.

    Parameters
    ----------
    value
        Decoded source policy.
    """
    value["compiled_artifacts"][_EXTRA_COHORT] = value["compiled_artifacts"]["0,0,0,10:0"]


def _extra_parameter(value: dict[str, Any]) -> None:
    """Build with one non-default parameter and its explicit compiler flag.

    Parameters
    ----------
    value
        Decoded native runtime receipt.
    """
    value["parameters"]["EXTRA_STATE_REGISTER"] = 1
    value["jobs"][0]["command"].append("-GEXTRA_STATE_REGISTER=1")


_FINDINGS: dict[str, tuple[dict[str, Any], str, str]] = {
    "checker-without-observation": (
        {"program": CHECKER.encode() + b"import os\nos._exit(0)\n"},
        "completion",
        "lacks a complete reaped observation",
    ),
    "checker-status-differs": (
        {"program": b"import atexit, os\natexit.register(os._exit, 7)\n" + CHECKER.encode()},
        "source_binding",
        "worker and native process status differ",
    ),
    "checker-refuses-projection": (
        {
            "program": b"import sys\nif sys.argv[1] == '--check':\n    sys.exit(3)\n"
            + CHECKER.encode()
        },
        "numerical",
        "refused the complete selected projection",
    ),
    "checker-diagnostic": (
        {"program": b"import sys\nprint('warning', file=sys.stderr)\n" + CHECKER.encode()},
        "completion",
        "reported an execution diagnostic",
    ),
    "receipt-operation": (
        {"change": edit_json(_GENERATE, _set("operation", value="check"))},
        "source_binding",
        "source or operation differs",
    ),
    "receipt-argv": (
        {"change": edit_json(_CHECK, _set("actual_argv", 1, value="--other"))},
        "source_binding",
        "argv differs",
    ),
    "receipt-environment": (
        {"change": edit_json("checker/check/environment.json", _set("PATH", value="/other"))},
        "source_binding",
        "environment differs",
    ),
    "receipt-status": (
        {"change": edit_json(_CHECK, _set("native_returncode", value=1))},
        "source_binding",
        "did not complete cleanly with a passing comparison",
    ),
    "receipt-input": (
        {"change": replace_file("checker/check/stimuli.txt", _OTHER_STIMULI)},
        "source_binding",
        "input/output differs from its bound whole-run role",
    ),
    "clock-declaration": (
        {
            "change": edit_json(
                "tool-receipt.json",
                _set(
                    "declared_clock_schedule",
                    value=_reference("completion.json", _completion()),
                ),
            )
        },
        "clock",
        "Root and tool receipt clock schedule bytes differ",
    ),
    "clock-field": (
        {"change": edit_json("clock-schedule.json", _set("first_input_tick", value=21))},
        "clock",
        "schedule differs: first_input_tick",
    ),
    "clock-final-counter": (
        {"change": edit_json("completion.json", _set("final_counter", value=5000))},
        "clock",
        "final counter does not fit",
    ),
    "completion-root": (
        {"change": edit_json("run.json", _set("completion", "raw_spikes", value=53))},
        "completion",
        "Root completion differs from actual source data: raw_spikes",
    ),
    "completion-actual": (
        {"change": edit_json("completion.json", _set("raw_spike_rows", value=999))},
        "completion",
        "completion predicate differs: raw_spike_rows",
    ),
    "completion-quiescence": (
        {"change": edit_json("completion.json", _set("pending_empty", value=False))},
        "completion",
        "not finalized and quiescent",
    ),
    "counter-width": (
        {"change": edit_json("capture-counts.json", _set("drop_counter_bits", value=16))},
        "capture",
        "counter width differs",
    ),
    "channel-declaration": (
        {"change": edit_json("run.json", _set("channels", 0, "attempts", value=1001))},
        "capture",
        "declaration differs from original capture: attempts",
    ),
    "native-rtl": (
        {"change": edit_json(_NATIVE, lambda value: value["jobs"][0]["command"].pop())},
        "source_binding",
        "compiled RTL source inventory differs",
    ),
    "native-versions": (
        {"change": edit_json(_NATIVE, _set("tool_versions", "verilator", value="other"))},
        "source_binding",
        "compiler versions differ",
    ),
    "native-identity": (
        {"change": edit_json(_NATIVE, _set("steps", value=999))},
        "source_binding",
        "identity/configuration differs",
    ),
    "native-arguments": (
        {"change": edit_json(_NATIVE, lambda value: value["jobs"][2]["command"].remove("-Werror"))},
        "source_binding",
        "compiler/dialect/run arguments differ",
    ),
    "native-returncode": (
        {"change": edit_json(_NATIVE, _set("jobs", 0, "returncode", value=1))},
        "source_binding",
        "build/execution did not complete cleanly",
    ),
    "native-parameters": (
        {
            "change": _both(
                edit_json("source-contract.json", _extra_cohort),
                edit_json(_NATIVE, _extra_parameter),
            )
        },
        "source_binding",
        "compile parameters differ from selected source configuration",
    ),
    "service-population": (
        {"change": _row("service.txt", -1, None)},
        "capture",
        "Service population differs from complete original raw spikes",
    ),
    "service-embedded-phase": (
        {"change": _row("service.txt", 0, 3, 23)},
        "capture",
        "Service 0: embedded-to-observed phase differs",
    ),
    "service-raw-phase": (
        {"change": _both(_row("service.txt", 0, 3, 25), _row("service.txt", 0, 4, 26))},
        "capture",
        "Service 0: raw-spike-to-service phase differs",
    ),
    "declared-projection": (
        {"change": _row("observed-projection.txt", 0, 1, -25)},
        "source_binding",
        "Declared numerical projection differs from the full identified trace",
    ),
    "input-stimulus": (
        {"change": _row("input.txt", 0, 5, -25)},
        "source_binding",
        "Input step 0: original stimulus fields differ",
    ),
    "raw-phase": (
        {"change": _row("raw-spikes.txt", 0, 3, 99)},
        "source_binding",
        "Raw step 0: original spike or source phase differs",
    ),
    "capture-start-marker": (
        {"change": _ticks("markers", 0, 9)},
        "capture",
        "input: markers differ from actual selected source schedule",
    ),
    "capture-first-input": (
        {"change": _ticks("payload", 1, 19)},
        "capture",
        "Input observation start differs from actual source clock schedule",
    ),
    "native-publication": (
        {"change": replace_file("stdout.log", b"interrupted\n")},
        "completion",
        "publication did not finalise cleanly",
    ),
}


@pytest.mark.parametrize("fault", list(_FINDINGS))
def test_interpretable_fault_is_an_exact_dimension_finding(tmp_path: Path, fault: str) -> None:
    """Report a damaged fact as a finding of its own dimension.

    Parameters
    ----------
    tmp_path
        Owned acquisition directory.
    fault
        Named single fault.
    """
    options, dimension, message = _FINDINGS[fault]
    acquisition = build_neural_acquisition(tmp_path / "run", **options)
    try:
        report = build_neural_run_report(
            load_neural_run(acquisition.manifest, registry=acquisition.registry)
        )
    finally:
        make_writable(tmp_path)
    assert report["verification"]["whole"] is False
    assert report[dimension]["pass"] is False
    assert any(message in finding for finding in report[dimension]["findings"]), report[dimension]


_RESET_FINDINGS: dict[str, tuple[Change, str]] = {
    "prefix-input": (_row("prefix/input.txt", 0, 5, -25), "Abandoned input 0"),
    "prefix-numerical": (_row("prefix/numerical.txt", 0, 3, -25), "Abandoned numerical 0"),
    "prefix-raw": (_row("prefix/raw_spike.txt", 0, 3, 99), "Abandoned raw spike 0"),
    "prefix-service": (
        replace_file("prefix/service.txt", b"0 0 0 24 25\n"),
        "did not establish the selected queued/inflight/pending reset",
    ),
}


@pytest.mark.parametrize("fault", list(_RESET_FINDINGS))
def test_reset_prefix_fault_is_a_completion_finding(tmp_path: Path, fault: str) -> None:
    """Report a damaged abandoned prefix as a completion finding.

    Parameters
    ----------
    tmp_path
        Owned acquisition directory.
    fault
        Named single fault of the reset prefix.
    """
    change, message = _RESET_FINDINGS[fault]
    acquisition = build_neural_acquisition(tmp_path / "run", epoch=1, change=change)
    try:
        report = build_neural_run_report(
            load_neural_run(acquisition.manifest, registry=acquisition.registry)
        )
    finally:
        make_writable(tmp_path)
    assert report["completion"]["pass"] is False
    assert any(message in finding for finding in report["completion"]["findings"])


def test_reset_prefix_identity_sequence_refuses(tmp_path: Path) -> None:
    """Refuse an abandoned prefix whose epoch and identity sequence differ.

    Parameters
    ----------
    tmp_path
        Owned acquisition directory.
    """
    change = _row("prefix/input.txt", 0, 0, 1)
    acquisition = build_neural_acquisition(tmp_path / "run", epoch=1, change=change)
    try:
        with pytest.raises(NeuralCaptureRefusalError, match="abandoned epoch/identity sequence"):
            load_neural_run(acquisition.manifest, registry=acquisition.registry)
    finally:
        make_writable(tmp_path)
