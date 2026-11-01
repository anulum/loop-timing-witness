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

import hashlib
import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from control_rust_support import canonical, python_outcome, python_outcome_under, rust_outcome
from test_run_manifest import _change_manifest

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
