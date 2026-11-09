# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — control-run loading parity of the Python and native analyses

"""Load real RTL runs through both analyses and require identical outcomes.

Every case starts from an Icarus capture of the production event-record
capture logic. Valid runs must load to the same manifest, domain, input
digests, directory and events; every refused run must give the same text,
including operating-system failures and faults injected by the kernel.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from control_rust_support import canonical, python_outcome, python_outcome_under, rust_outcome
from test_control_receipt_schema_corpus import HOST_LOAD, NATIVE
from test_run_manifest import _change_manifest
from test_run_series import _bad_power, _bad_tracking

from conftest import REPOSITORY_ROOT
from loop_timing_witness.event_stream import decode_events
from loop_timing_witness.manifest_io import load_json_object
from loop_timing_witness.run_analysis import analyse_events
from loop_timing_witness.run_manifest import load_run

MakeRtlRun = Callable[..., tuple[Path, dict[str, Any]]]
VARIANTS = [
    "schema_id",
    "non_utc",
    "placement",
    "rate",
    "compute_period",
    "missing_period",
    "warmup",
    "fault_cycle",
    "fault_delay",
    "event_digest",
    "domain_digest",
    "source_digest",
    "traversal",
    "directory",
    "escape_symlink",
    "missing_source",
    "board_without_evidence",
]
CODES = load_json_object(REPOSITORY_ROOT / "measurement-domain.json")["design_contracts"][
    "event_codes"
]
SERIES_VARIANTS = [
    "tracking_utf8",
    "tracking_header",
    "tracking_empty",
    "tracking_ragged",
    "tracking_csv_quote",
    "tracking_cycle_text",
    "tracking_cycle_duplicate",
    "tracking_cycle_outside",
    "tracking_cycle_missing",
    "tracking_decimal",
    "tracking_infinite",
    "power_unknown_rail",
    "power_duplicate_rail",
    "power_negative",
    "power_incomplete",
    "power_single_sample",
    "power_regression",
    "power_uncovered",
]


def _write(run: Path, manifest: dict[str, Any]) -> Path:
    """Write the manifest beside its run files.

    Parameters
    ----------
    run
        Run directory.
    manifest
        Declaration to write.

    Returns
    -------
    Path
        Manifest path.
    """
    path = run / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _bind(run: Path, manifest: dict[str, Any], key: str, content: bytes) -> None:
    """Replace one bound file's bytes and declare their digest.

    Parameters
    ----------
    run
        Run directory.
    manifest
        Declaration changed in place.
    key
        ``measurement_domain`` or a member of ``files``.
    content
        New file bytes.
    """
    item = manifest[key] if key == "measurement_domain" else manifest["files"][key]
    (run / item["path"]).write_bytes(content)
    item["sha256"] = hashlib.sha256(content).hexdigest()


def _same(path: Path, directory: Path, root: bytes | None = None) -> dict[str, Any]:
    """Require identical outcomes and return the Python one.

    Parameters
    ----------
    path
        Manifest path.
    directory
        Owned directory for the native outcome.
    root
        Manifest bytes already read for the path, or ``None``.

    Returns
    -------
    dict[str, Any]
        The common outcome.
    """
    python = python_outcome(path, root)
    assert canonical(rust_outcome(path, directory, root)) == canonical(python)
    return python


@pytest.mark.parametrize("profile", ["CONTROL", "COMPUTE"])
def test_valid_runs_load_to_the_same_inputs_and_events(
    profile: str, make_rtl_run: MakeRtlRun, tmp_path: Path
) -> None:
    """Load each profile's real capture, also from root bytes already read.

    Parameters
    ----------
    profile
        Event profile of the capture.
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directory.
    """
    run, manifest = make_rtl_run(profile)
    path = _write(run, manifest)
    outcome = _same(path, tmp_path / "file")
    assert outcome["events"]
    assert outcome["events_refusal"] is None
    _same(path, tmp_path / "root", path.read_bytes())


def test_receipts_are_read_before_the_declared_files(
    make_rtl_run: MakeRtlRun, tmp_path: Path
) -> None:
    """Bind native metadata and host-load receipts and read them in the same order.

    Parameters
    ----------
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directory.
    """
    run, manifest = make_rtl_run()
    manifest["native_metadata"] = manifest["files"]["events"].copy()
    manifest["host_load"] = manifest["files"]["power"].copy()
    outcome = _same(_write(run, manifest), tmp_path / "receipts")
    assert set(outcome["files"]) == {"events", "tracking", "power", "native_metadata", "host_load"}
    manifest["host_load"] = {"path": "absent.json", "sha256": "0" * 64}
    _same(_write(run, manifest), tmp_path / "absent")


def test_root_bytes_keep_loading_after_the_manifest_file_vanished(
    make_rtl_run: MakeRtlRun, tmp_path: Path
) -> None:
    """Resolve a vanished manifest beside its directory, as Python's non-strict resolve does.

    Parameters
    ----------
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directory.
    """
    run, manifest = make_rtl_run()
    path = _write(run, manifest)
    root = path.read_bytes()
    path.unlink()
    assert _same(path, tmp_path / "vanished", root)["directory"] == str(run.resolve())
    _same(path, tmp_path / "missing")


@pytest.mark.parametrize("variant", VARIANTS)
def test_declaration_refusals_are_identical(
    variant: str, make_rtl_run: MakeRtlRun, tmp_path: Path
) -> None:
    """Refuse every changed declaration of the provenance suite with the same text.

    Parameters
    ----------
    variant
        Named manifest or file-reference violation.
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directory.
    """
    run, manifest = make_rtl_run()
    _change_manifest(run, manifest, variant)
    assert "refusal" in _same(_write(run, manifest), tmp_path)


def test_files_are_read_in_document_order(make_rtl_run: MakeRtlRun, tmp_path: Path) -> None:
    """Report the first failing file of the declaration, not of a sorted order.

    Parameters
    ----------
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directory.
    """
    run, manifest = make_rtl_run()
    files = manifest["files"]
    manifest["files"] = {
        "tracking": {"path": "absent.csv", "sha256": "0" * 64},
        "events": {**files["events"], "sha256": "0" * 64},
        "power": files["power"],
    }
    outcome = _same(_write(run, manifest), tmp_path)
    assert outcome["refusal"] == "input is not a regular file inside the run directory: absent.csv"


@pytest.mark.parametrize(
    "raw",
    [
        b"{",
        b'{"a": NaN}',
        b'{"a": 1, "a": 2}',
        b'{"a": 18446744073709551616}',
        b'{"a": "\\ud800"}',
        b"[" * 65 + b"]" * 65,
        b"[]",
        b'{"a": "\xff"}',
    ],
)
def test_manifest_json_refusals_are_identical(
    raw: bytes, make_rtl_run: MakeRtlRun, tmp_path: Path
) -> None:
    """Refuse a malformed manifest document with the same labelled text.

    Parameters
    ----------
    raw
        Manifest bytes.
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directory.
    """
    run, _ = make_rtl_run()
    path = run / "manifest.json"
    path.write_bytes(raw)
    assert _same(path, tmp_path)["refusal"].startswith(f"{path}: ")


def _floats(value: object) -> object:
    """Return a value with every integer turned into an integral float.

    Parameters
    ----------
    value
        Decoded JSON value.

    Returns
    -------
    Any
        Changed copy.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return float(value)
    if isinstance(value, dict):
        return {key: _floats(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_floats(item) for item in value]
    return value


@pytest.mark.parametrize(
    "change",
    ["invalid JSON", "schema", "semantic", "wire", "integral floats", "rate-bound COMPUTE"],
)
def test_domain_refusals_and_floats_are_identical(
    change: str, make_rtl_run: MakeRtlRun, tmp_path: Path
) -> None:
    """Bind a changed measurement domain and load it through both analyses.

    Parameters
    ----------
    change
        Domain change.
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directory.
    """
    run, manifest = make_rtl_run("COMPUTE" if change == "rate-bound COMPUTE" else "CONTROL")
    domain = json.loads((run / "measurement-domain.json").read_text(encoding="utf-8"))
    contracts = domain["design_contracts"]
    if change == "schema":
        contracts.pop("event_record")
    elif change == "semantic":
        domain["claims"] = ["unmeasured"]
    elif change == "wire":
        contracts["event_record"]["fields"][1]["name"] = "spare_byte"
    elif change == "integral floats":
        domain["design_contracts"] = _floats(contracts)
    elif change == "rate-bound COMPUTE":
        contracts["event_profiles"]["COMPUTE"]["sample_rate_hz"] = {
            "minimum": 100,
            "default": 1000,
            "maximum": 20000,
        }
    raw = b"{" if change == "invalid JSON" else json.dumps(domain).encode()
    _bind(run, manifest, "measurement_domain", raw)
    outcome = _same(_write(run, manifest), tmp_path)
    assert ("refusal" in outcome) is (change != "integral floats")


@pytest.mark.parametrize(
    "events",
    [
        b"\x01" * 15,
        b"",
        bytes([1, 1, 0, 0]) + bytes(12),
        bytes([8, 0, 0, 0]) + bytes(12),
        bytes([1, 0, 0, 0]) + (99).to_bytes(4, "little") + bytes(8),
        bytes([1, 0, 0, 0, 0, 0, 0, 0])
        + (9).to_bytes(8, "little")
        + bytes([2, 0, 0, 0, 0, 0, 0, 0])
        + (8).to_bytes(8, "little"),
        (bytes([1, 0, 0, 0, 0, 0, 0, 0]) + (9).to_bytes(8, "little")) * 2,
    ],
)
def test_event_refusals_are_identical(
    events: bytes, make_rtl_run: MakeRtlRun, tmp_path: Path
) -> None:
    """Load a run whose bound events break one decoding rule.

    Parameters
    ----------
    events
        Event file bytes.
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directory.
    """
    run, manifest = make_rtl_run()
    _bind(run, manifest, "events", events)
    outcome = _same(_write(run, manifest), tmp_path)
    assert outcome["events"] is None
    assert outcome["events_refusal"]


@pytest.mark.skipif(os.geteuid() == 0, reason="the superuser reads files without permission")
def test_unreadable_files_report_the_same_operating_system_error(
    make_rtl_run: MakeRtlRun, tmp_path: Path
) -> None:
    """Refuse an unreadable bound file and a missing manifest with Python's error text.

    Parameters
    ----------
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directory.
    """
    run, manifest = make_rtl_run()
    path = _write(run, manifest)
    (run / "events.bin").chmod(0)
    try:
        assert _same(path, tmp_path / "events")["refusal"].startswith("[Errno 13] ")
    finally:
        (run / "events.bin").chmod(0o600)
    source = run / manifest["source"]["files"][0]["path"]
    source.chmod(0)
    try:
        assert _same(path, tmp_path / "source")["refusal"].startswith("[Errno 13] ")
    finally:
        source.chmod(0o600)
    missing = run / "absent-manifest.json"
    assert _same(missing, tmp_path / "manifest")["refusal"].startswith("[Errno 2] ")


@pytest.mark.parametrize("target", ["source", "events", "manifest"])
def test_injected_read_errors_are_reported_alike(
    target: str, make_rtl_run: MakeRtlRun, tmp_path: Path
) -> None:
    """Fail every read of one file with EIO in the kernel and compare both refusals.

    Parameters
    ----------
    target
        Source artefact, bound event file or the manifest itself.
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directories.
    """
    strace = shutil.which("strace")
    assert strace is not None
    run, manifest = make_rtl_run()
    path = _write(run, manifest)
    files = {
        "source": run / manifest["source"]["files"][0]["path"],
        "events": run / "events.bin",
        "manifest": path,
    }
    wrapper = [
        strace,
        "-f",
        "-qq",
        "-o",
        os.devnull,
        "-P",
        str(files[target]),
        "-e",
        "inject=read:error=EIO",
    ]
    python = python_outcome_under(path, wrapper, tmp_path / "python")
    rust = rust_outcome(path, tmp_path / "rust", wrapper=wrapper)
    assert canonical(rust) == canonical(python)
    assert python["refusal"] == "[Errno 5] Input/output error"


def _board(manifest: dict[str, Any]) -> None:
    """Declare the run as a board run whose artefacts are its real source file.

    Parameters
    ----------
    manifest
        Declaration changed in place.
    """
    manifest["source"]["kind"] = "board"
    reference = manifest["source"]["files"][0]
    manifest["hardware_artifacts"] = {
        name: reference.copy()
        for name in ("bitstream", "firmware", "linux_image", "controller_binary")
    } | {"libero_version": "declared", "toolchain_version": "declared"}
    manifest["instrument"].update(
        dict.fromkeys(
            ("known_period_pass", "injected_delay_pass", "overflow_pass", "bus_offset_pass"), True
        )
        | {"floor_ticks": 0}
    )
    manifest["environment"] = {"room_temperature_c": 20, "board_supply_only": True}


@pytest.mark.parametrize("change", ["valid", "overflow", "artefact digest"])
def test_board_declarations_load_or_refuse_alike(
    change: str, make_rtl_run: MakeRtlRun, tmp_path: Path
) -> None:
    """Verify every hardware artefact of a board declaration and its overflow rule.

    Parameters
    ----------
    change
        Valid declaration, FIFO overflow or a changed artefact digest.
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directory.
    """
    run, manifest = make_rtl_run()
    _board(manifest)
    if change == "overflow":
        manifest["instrument"]["fifo_overflow_count"] = 1
    elif change == "artefact digest":
        manifest["hardware_artifacts"]["linux_image"]["sha256"] = "0" * 64
    outcome = _same(_write(run, manifest), tmp_path)
    assert ("refusal" in outcome) is (change != "valid")


@pytest.mark.parametrize(
    ("member", "value"),
    [
        ("sample_period_ticks", 2_000_000),
        ("fault_schedule", [{"cycle": 2, "kind": "drop", "delay_periods": 0}]),
    ],
)
def test_rate_and_fault_rules_load_or_refuse_alike(
    member: str, value: object, make_rtl_run: MakeRtlRun, tmp_path: Path
) -> None:
    """Refuse a period below the minimum rate and accept a non-delay fault without delay.

    Parameters
    ----------
    member
        Run member to replace.
    value
        New value.
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directory.
    """
    run, manifest = make_rtl_run()
    manifest[member] = value
    outcome = _same(_write(run, manifest), tmp_path)
    assert ("refusal" in outcome) is (member == "sample_period_ticks")


@pytest.mark.parametrize("shape", ["wider record", "split reserved word"])
def test_record_layouts_off_the_wire_are_refused_alike(
    shape: str, make_rtl_run: MakeRtlRun, tmp_path: Path
) -> None:
    """Refuse consistent event records that differ from the 16-byte host layout.

    Parameters
    ----------
    shape
        A record with a sixth field after the timestamp, or a reserved word split in two.
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directory.
    """
    run, manifest = make_rtl_run()
    domain = json.loads((run / "measurement-domain.json").read_text(encoding="utf-8"))
    record = domain["design_contracts"]["event_record"]
    if shape == "wider record":
        record["fields"].append({"name": "spare", "offset_bytes": 16, "type": "u8"})
        record["record_size_bytes"] = 17
    else:
        record["fields"][2] = {"name": "spare_low", "offset_bytes": 2, "type": "u8"}
        record["fields"].insert(3, {"name": "spare_high", "offset_bytes": 3, "type": "u8"})
    _bind(run, manifest, "measurement_domain", json.dumps(domain).encode())
    outcome = _same(_write(run, manifest), tmp_path)
    assert (
        outcome["refusal"]
        == "measurement domain event record differs from the 16-byte host wire layout"
    )


@pytest.mark.parametrize(("cycles", "warmup"), [(3.0, 0.0), (3.0, 2.0), (3, 1)])
def test_events_blocks_keep_python_number_types(
    cycles: float, warmup: float, make_rtl_run: MakeRtlRun, tmp_path: Path
) -> None:
    """Build the events block from integral-float and integer cycle declarations alike.

    Parameters
    ----------
    cycles
        Declared cycle count.
    warmup
        Declared warm-up cycles.
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directory.
    """
    run, manifest = make_rtl_run()
    manifest["cycle_count"], manifest["warmup_cycles"] = cycles, warmup
    outcome = _same(_write(run, manifest), tmp_path)
    assert outcome["summary"]["block"]["cycle_count"] == cycles - warmup


@pytest.mark.parametrize("variant", SERIES_VARIANTS)
def test_series_refusals_are_identical(
    variant: str, make_rtl_run: MakeRtlRun, tmp_path: Path
) -> None:
    """Refuse each damaged tracking or power series with the same text.

    Parameters
    ----------
    variant
        Named damage from the series command tests.
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directory.
    """
    run, manifest = make_rtl_run()
    name = "tracking" if variant.startswith("tracking") else "power"
    content = (run / f"{name}.csv").read_bytes()
    damage = _bad_tracking if name == "tracking" else _bad_power
    _bind(run, manifest, name, damage(variant, content))
    outcome = _same(_write(run, manifest), tmp_path)
    assert outcome["report"] is None
    assert outcome["report_refusal"]


@pytest.mark.parametrize(
    "change", ["complete", "observed", "no tracking", "no power", "range", "header quote"]
)
def test_reports_are_identical(change: str, make_rtl_run: MakeRtlRun, tmp_path: Path) -> None:
    """Build the same complete report, or refuse alike, for real captures.

    Parameters
    ----------
    change
        Complete run, observed tracking, an absent series, an out-of-range
        value or a damaged header.
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directory.
    """
    run, manifest = make_rtl_run()
    tracking = (run / "tracking.csv").read_bytes()
    if change == "observed":
        manifest["tracking_sampling"] = "observed"
    elif change in {"no tracking", "no power"}:
        manifest["files"]["tracking" if change == "no tracking" else "power"] = None
    elif change == "range":
        _bind(run, manifest, "tracking", tracking.replace(b"\n0,", b"\n0,1e100", 1))
    elif change == "header quote":
        _bind(run, manifest, "tracking", b'"' + tracking)
    outcome = _same(_write(run, manifest), tmp_path)
    assert (outcome["report"] is None) is (change in {"range", "header quote"})


def _receipt(run: Path, manifest: dict[str, Any], key: str, document: dict[str, Any]) -> None:
    """Write one receipt beside the run and bind it in the declaration.

    Parameters
    ----------
    run
        Run directory.
    manifest
        Declaration changed in place.
    key
        ``native_metadata`` or ``host_load``.
    document
        Receipt content.
    """
    content = json.dumps(document).encode()
    (run / f"{key}.json").write_bytes(content)
    manifest[key] = {"path": f"{key}.json", "sha256": hashlib.sha256(content).hexdigest()}


def _bind_receipts(
    run: Path, manifest: dict[str, Any], overflow: int, profile: str, exit_status: int | None = None
) -> None:
    """Bind native metadata and a host load receipt that agree with the capture.

    The completion counters are those of the Python analysis of the same
    captured events, so a correct native analysis accepts them.

    Parameters
    ----------
    run
        Real Icarus CONTROL capture.
    manifest
        Its declaration, changed in place.
    overflow
        Declared and reported FIFO overflow count.
    profile
        Host load profile of the receipt; the declared load case stays ``idle``.
    exit_status
        Native exit status in the host load receipt, or ``None`` for the one the
        overflow implies.
    """
    manifest["controller"] = {"name": "pid", "coefficients": dict(NATIVE["coefficients"])}
    manifest["instrument"]["fifo_overflow_count"] = overflow
    inputs = load_run(_write(run, manifest))
    contracts = inputs.domain["design_contracts"]
    events = decode_events(inputs.files["events"], contracts, "CONTROL", manifest["cycle_count"])
    try:
        full, _ = analyse_events(
            events, contracts["event_profiles"]["CONTROL"], manifest["cycle_count"], 0
        )
    except ValueError:
        full = {"control": {"deadline_misses": 0, "safe_state_events": 0}}
    fault = manifest["fault_schedule"][0]
    native = copy.deepcopy(NATIVE)
    native.update(
        cycles=manifest["cycle_count"],
        period_ticks=manifest["sample_period_ticks"],
        fault={
            "kind": fault["kind"],
            "cycle": fault["cycle"],
            "duration_periods": fault["delay_periods"],
        },
        result={
            "records": len(events),
            "overflow": overflow,
            "misses": full["control"]["deadline_misses"],
            "samples": sum(event.name == "SAMPLE_READ" for event in events),
            "safe": bool(full["control"]["safe_state_events"]),
        },
    )
    native["artifacts"]["events"] = {
        "sha256": manifest["files"]["events"]["sha256"],
        "bytes": len(inputs.files["events"]),
    }
    native["artifacts"]["configuration"]["sha256"] = manifest["source"]["files"][0]["sha256"]
    _receipt(run, manifest, "native_metadata", native)
    host = copy.deepcopy(HOST_LOAD)
    host.update(
        profile=profile,
        native_pid=2,
        started_ns=1,
        native_started_ns=2,
        native_finished_ns=3,
        finished_ns=4,
        native_returncode=int(bool(overflow)) if exit_status is None else exit_status,
    )
    host["counters"]["idle_waits"] = 1 if profile == "idle" else 0
    host["counters"]["arithmetic_operations"] = 4096 if profile == "cpu" else 0
    _receipt(run, manifest, "host_load", host)


@pytest.mark.parametrize(
    "change", ["receipts", "warm-up", "overflow", "load profile", "exit status", "warm-up order"]
)
def test_reports_with_receipts_are_identical(
    change: str, make_rtl_run: MakeRtlRun, tmp_path: Path
) -> None:
    """Attach agreeing native metadata and a host load receipt alike.

    Parameters
    ----------
    change
        Agreeing receipts; a warm-up cycle, which checks the counters against
        the whole capture; a declared FIFO overflow; or a host load profile
        that contradicts the declared load case.
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directory.
    """
    run, manifest = make_rtl_run()
    if change in {"warm-up", "warm-up order"}:
        manifest["warmup_cycles"] = 1
        manifest["files"]["power"] = None
    if change == "warm-up order":
        _edit_events(run, manifest, _swap_first_ready_and_read)
    _bind_receipts(
        run,
        manifest,
        1 if change == "overflow" else 0,
        "cpu" if change == "load profile" else "idle",
        1 if change == "exit status" else None,
    )
    outcome = _same(_write(run, manifest), tmp_path)
    if change in {"load profile", "exit status"}:
        assert outcome["report_refusal"] == (
            "host load profile or native exit status contradicts the capture"
        )
    elif change == "warm-up order":
        assert outcome["report_refusal"] == "cycle 0: scheduling_latency ends before it starts"
    else:
        report = outcome["report"]["report"]
        assert set(report) >= {"native_completion", "host_load"}


def _edit_events(
    run: Path, manifest: dict[str, Any], edit: Callable[[list[bytearray]], list[bytearray]]
) -> None:
    """Change the captured event records and bind the result.

    Parameters
    ----------
    run
        Run directory.
    manifest
        Declaration changed in place.
    edit
        Change of the list of 16-byte records.
    """
    content = (run / "events.bin").read_bytes()
    records = [bytearray(content[offset : offset + 16]) for offset in range(0, len(content), 16)]
    _bind(run, manifest, "events", b"".join(edit(records)))


def _cycle(record: bytearray) -> int:
    """Return a record's cycle.

    Parameters
    ----------
    record
        16-byte event record.

    Returns
    -------
    int
        Cycle number.
    """
    return int.from_bytes(record[4:8], "little")


def _swap_first_ready_and_read(records: list[bytearray]) -> list[bytearray]:
    """Swap the event codes of cycle 0's ready and read records, keeping time order.

    Parameters
    ----------
    records
        Captured records.

    Returns
    -------
    list[bytearray]
        Records whose cycle-0 sample read precedes its sample-ready event.
    """
    ready, read = CODES["SAMPLE_READY"], CODES["SAMPLE_READ"]
    for record in records:
        if _cycle(record) == 0 and record[0] in {ready, read}:
            record[0] = read if record[0] == ready else ready
    return records


@pytest.mark.parametrize("change", ["missing deadline", "partial observed"])
def test_invalid_reports_are_identical(
    change: str, make_rtl_run: MakeRtlRun, tmp_path: Path
) -> None:
    """Report a missing cycle anchor or partial observed tracking alike.

    Parameters
    ----------
    change
        A removed deadline record, or a removed sample read with its tracking row.
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directory.
    """
    run, manifest = make_rtl_run()
    if change == "missing deadline":
        _edit_events(
            run,
            manifest,
            lambda records: [
                record
                for record in records
                if not (record[0] == CODES["DEADLINE"] and _cycle(record) == 1)
            ],
        )
    else:
        manifest["tracking_sampling"] = "observed"
        _edit_events(
            run,
            manifest,
            lambda records: [
                record
                for record in records
                if not (record[0] == CODES["SAMPLE_READ"] and _cycle(record) == 1)
            ],
        )
        rows = (run / "tracking.csv").read_text(encoding="utf-8").splitlines()
        kept = [row for row in rows if not row.startswith("1,")]
        _bind(run, manifest, "tracking", ("\n".join(kept) + "\n").encode())
    report = _same(_write(run, manifest), tmp_path)["report"]["report"]
    assert report["valid"] is False
    assert report["invalid_reasons"]


def test_runs_with_an_amp_capture_are_refused_by_the_native_report(
    make_rtl_run: MakeRtlRun, tmp_path: Path
) -> None:
    """The native report refuses an AMP capture until AMP completion is native.

    Parameters
    ----------
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directory.
    """
    run, manifest = make_rtl_run()
    manifest.update(placement="bare_metal_amp", tracking_sampling="observed")
    manifest["files"]["power"] = None
    manifest["amp_capture"] = manifest["files"]["events"].copy()
    rust = rust_outcome(_write(run, manifest), tmp_path)
    assert rust["events_refusal"] is None
    assert rust["report_refusal"] == "AMP capture completion is not analysed by the native analysis"
