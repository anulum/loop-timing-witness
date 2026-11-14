# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — AMP run analysis parity between Python and the native analysis

"""Analyse real dedicated-hart captures and their changed copies with both analyses.

Real captures run prepared RV64 images under Spike with the production RTL
plugins. Each case copies a capture, changes its receipt, a captured artifact
or the run declaration, binds the run manifest to the bytes the run now holds,
and requires the Python analysis and the native analysis to load, decode and
report the run alike: the same report with the logger's completion, or the
same refusal at the same stage. A fragment of Python's refusal is checked too,
so each case reaches the check it is named for.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Final

import pytest
from capture_amp_simulation import main as capture_main
from control_rust_support import canonical, python_outcome, rust_outcome
from test_amp_capture_scenarios import arithmetic_compiler, scenario_capture
from test_capture_amp_simulation import capture_arguments

from manifest_io import canonical_json_bytes, sha256_of_file

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["arithmetic_compiler", "capture_arguments", "scenario_capture"]
Change = Callable[["Path"], None]
Document = Callable[[dict[str, Any]], None]
ZERO: Final = "0" * 64
DEADLINE: Final = 4
DECLARATION: Final = "AMP capture configuration does not match the run declaration"
COUNTERS: Final = "AMP completion counters do not match captured events"
IDENTITIES: Final = "AMP capture tool or verified image identities disagree"


def _load(path: Path) -> dict[str, Any]:
    """Return one JSON document.

    Parameters
    ----------
    path
        Document path.

    Returns
    -------
    dict[str, Any]
        The document.
    """
    document: dict[str, Any] = json.loads(path.read_bytes())
    return document


def _bind(run: Path) -> None:
    """Bind the run manifest to the bytes the run holds now.

    The capture receipt, the declared files, the measurement domain and the
    source files (the receipt's artifacts present as files, not links, under
    names without ``..``)
    get their current digests, so the run loader admits them and the capture's
    own declarations are what the analysis checks.

    Parameters
    ----------
    run
        Run directory.
    """
    manifest = _load(run / "manifest.json")
    capture = _load(run / "capture.json")
    manifest["amp_capture"]["sha256"] = sha256_of_file(run / "capture.json")
    domain = manifest["measurement_domain"]
    domain["sha256"] = sha256_of_file(run / domain["path"])
    for item in manifest["files"].values():
        if item is not None:
            item["sha256"] = sha256_of_file(run / item["path"])
    manifest["source"]["files"] = [
        {"path": name, "sha256": sha256_of_file(run / name)}
        for name in capture["files"]
        if ".." not in name.split("/") and (run / name).is_file() and not (run / name).is_symlink()
    ]
    (run / "manifest.json").write_bytes(canonical_json_bytes(manifest))


def _document(name: str, change: Document, *, captured: bool = True) -> Change:
    """Return a case that changes one JSON document of the run.

    Parameters
    ----------
    name
        Document path in the run.
    change
        In-place change of the document.
    captured
        Whether the capture receipt binds the document's new digest.

    Returns
    -------
    Change
        The case.
    """

    def apply(run: Path) -> None:
        document = _load(run / name)
        change(document)
        (run / name).write_bytes(canonical_json_bytes(document))
        if captured:
            capture = _load(run / "capture.json")
            capture["files"][name] = sha256_of_file(run / name)
            (run / "capture.json").write_bytes(canonical_json_bytes(capture))

    return apply


def _receipt(change: Document) -> Change:
    """Return a case that changes the capture receipt.

    Parameters
    ----------
    change
        In-place change of the receipt.

    Returns
    -------
    Change
        The case.
    """
    return _document("capture.json", change, captured=False)


def _declaration(change: Document) -> Change:
    """Return a case that changes the run declaration.

    Parameters
    ----------
    change
        In-place change of the manifest.

    Returns
    -------
    Change
        The case.
    """
    return _document("manifest.json", change, captured=False)


def _artifact(name: str, change: Callable[[bytes], bytes]) -> Change:
    """Return a case that changes one captured artifact and binds its new digest.

    Parameters
    ----------
    name
        Artifact path in the run.
    change
        New bytes from the old.

    Returns
    -------
    Change
        The case.
    """

    def apply(run: Path) -> None:
        path = run / name
        path.write_bytes(change(path.read_bytes()))
        capture = _load(run / "capture.json")
        capture["files"][name] = sha256_of_file(path)
        (run / "capture.json").write_bytes(canonical_json_bytes(capture))

    return apply


def _both(*changes: Change) -> Change:
    """Return a case that applies several changes in order.

    Parameters
    ----------
    *changes
        The changes.

    Returns
    -------
    Change
        The case.
    """

    def apply(run: Path) -> None:
        for change in changes:
            change(run)

    return apply


def _completion(change: Document) -> Change:
    """Return a case that changes the logged completion and the receipt's copy alike.

    Parameters
    ----------
    change
        In-place change of the completion counters.

    Returns
    -------
    Change
        The case.
    """

    def log(content: bytes) -> bytes:
        prefix = b"WITNESS_AMP_COMPLETION "
        lines = content.split(b"\n")
        for index, line in enumerate(lines):
            if line.startswith(prefix):
                counters = json.loads(line[len(prefix) :])
                change(counters)
                lines[index] = prefix + json.dumps(counters, separators=(",", ":")).encode()
        return b"\n".join(lines)

    return _both(
        _artifact("spike.log", log), _receipt(lambda capture: change(capture["completion"]))
    )


def _outside_link(run: Path) -> None:
    """Replace the simulator log with a link to an identical file outside the run.

    Parameters
    ----------
    run
        Run directory.
    """
    outside = run.parent / f"{run.name}-spike.log"
    shutil.move(run / "spike.log", outside)
    (run / "spike.log").symlink_to(outside)


def _record_removed(run: Path) -> None:
    """Remove the first preprocessing record that the capture still binds.

    Parameters
    ----------
    run
        Run directory.
    """
    (run / "image/precompile/input_0.d").unlink()


def _copied(name: str, member: str, content: Callable[[bytes], bytes]) -> Change:
    """Return a case that binds the run to a changed copy of one of its files.

    Parameters
    ----------
    name
        File the copy is made from.
    member
        ``measurement_domain`` or a declared file's name.
    content
        Copy's bytes from the original's.

    Returns
    -------
    Change
        The case.
    """

    def apply(run: Path) -> None:
        copy = f"run-{name}"
        (run / copy).write_bytes(content((run / name).read_bytes()))
        manifest = _load(run / "manifest.json")
        item = manifest[member] if member == "measurement_domain" else manifest["files"][member]
        item["path"] = copy
        (run / "manifest.json").write_bytes(canonical_json_bytes(manifest))

    return apply


def _later_tick(content: bytes) -> bytes:
    """Move the last event one tick later.

    Parameters
    ----------
    content
        Event stream.

    Returns
    -------
    bytes
        Changed stream.
    """
    last = bytearray(content[-16:])
    last[8:16] = (int.from_bytes(last[8:16], "little") + 1).to_bytes(8, "little")
    return content[:-16] + bytes(last)


def _deadline_removed(run: Path) -> None:
    """Remove the first deadline record and log one event fewer.

    Parameters
    ----------
    run
        Run directory.
    """
    events = (run / "events.bin").read_bytes()
    first = next(index for index in range(0, len(events), 16) if events[index] == DEADLINE)
    _artifact("events.bin", lambda content: content[:first] + content[first + 16 :])(run)
    _completion(lambda counters: counters.update(events=counters["events"] - 1))(run)


def _tracking_changed(run: Path) -> None:
    """Change the first observed reference of the run's tracking file.

    Parameters
    ----------
    run
        Run directory.
    """
    path = run / "tracking.csv"
    lines = path.read_bytes().split(b"\r\n")
    cells = lines[1].split(b",")
    cells[1] = b"0.25" if cells[1] != b"0.25" else b"0.5"
    lines[1] = b",".join(cells)
    path.write_bytes(b"\r\n".join(lines))


def _leading_zeros(content: bytes) -> bytes:
    """Write the first raw tracking row's cycle with 5000 leading zeros.

    Parameters
    ----------
    content
        Raw tracking.

    Returns
    -------
    bytes
        Changed raw tracking.
    """
    header, first, rest = content.split(b"\n", 2)
    return b"\n".join([header, b"0" * 5000 + first, rest])


def _swap(path: str, pair: tuple[str, str]) -> Document:
    """Return a change that swaps one string member between two values.

    Parameters
    ----------
    path
        Dotted member path.
    pair
        The two values.

    Returns
    -------
    Document
        The change.
    """

    def change(document: dict[str, Any]) -> None:
        *parents, last = path.split(".")
        node = document
        for part in parents:
            node = node[part]
        node[last] = pair[1] if node[last] == pair[0] else pair[0]

    return change


def _first_value(member: str) -> Document:
    """Return a change that declares a zero digest for a mapping's first entry.

    Parameters
    ----------
    member
        Mapping member.

    Returns
    -------
    Document
        The change.
    """

    def change(document: dict[str, Any]) -> None:
        mapping = document[member]
        mapping[next(iter(mapping))] = ZERO

    return change


def _lowercase_times(capture: dict[str, Any]) -> None:
    """Write both capture timestamps with lowercase separators.

    Parameters
    ----------
    capture
        Capture receipt.
    """
    for field in ("started_utc", "completed_utc"):
        capture[field] = capture[field].replace("T", "t").replace("Z", "z")


def _absent_first(capture: dict[str, Any]) -> None:
    """Bind a missing artifact before a wrong digest, in document order.

    Parameters
    ----------
    capture
        Capture receipt.
    """
    capture["files"] = {"absent.bin": ZERO, **capture["files"], "events.bin": ZERO}


Cases = dict[str, tuple[Change, str | None]]
RECEIPT_CASES: Final[Cases] = {
    "captured run": (lambda _: None, None),
    "receipt breaking its schema": (
        _receipt(lambda capture: capture.update(simulation_only=False)),
        "does not satisfy the AMP capture schema",
    ),
    "start with an offset": (
        _receipt(lambda capture: capture.update(started_utc="2026-11-13T10:00:00+01:00")),
        "must be an RFC 3339 date-time in UTC",
    ),
    "times in lowercase": (_receipt(_lowercase_times), DECLARATION),
    "receipt with a logged miss": (
        _receipt(lambda capture: capture["completion"].update(misses=1)),
        "differs from the actual logger",
    ),
    "another plugin": (_receipt(lambda capture: capture["tools"].update(plugin=ZERO)), IDENTITIES),
    "no logger artifact": (
        _receipt(lambda capture: capture["files"].pop("spike.log")),
        "lacks required original artifact identities",
    ),
    "escaping artifact name": (
        _receipt(lambda capture: capture["files"].update({"image/../events.bin": ZERO})),
        "artifact bytes or paths changed",
    ),
    "wrong events digest": (
        _receipt(lambda capture: capture["files"].update({"events.bin": ZERO})),
        "artifact bytes or paths changed",
    ),
    "absent artifact first": (_receipt(_absent_first), "No such file or directory"),
    "runtime digest unlike the simulator's": (
        _both(
            _receipt(lambda capture: capture["runtime"].update(sha256=ZERO)),
            _document("command.json", lambda command: command["runtime"].update(sha256=ZERO)),
        ),
        IDENTITIES,
    ),
}
ARTIFACT_CASES: Final[Cases] = {
    "logger line changed": (
        _artifact("spike.log", lambda log: log.replace(b'"misses":0', b'"misses":1')),
        "differs from the actual logger",
    ),
    "log reached through an outside link": (_outside_link, "artifact bytes or paths changed"),
    "captured domain empty": (
        _both(
            _copied("measurement-domain.json", "measurement_domain", lambda content: content),
            _artifact("measurement-domain.json", lambda _: b"{}"),
        ),
        "measurement domain invalid",
    ),
    "tracking cycle with leading zeros": (_artifact("tracking_raw.csv", _leading_zeros), None),
    "preprocessing record missing": (_record_removed, "No such file or directory"),
    "command tools differ": (
        _document("command.json", lambda command: command["tools"].update(plugin=ZERO)),
        IDENTITIES,
    ),
    "command runtime differs": (
        _document("command.json", lambda command: command["runtime"].update(version="other")),
        IDENTITIES,
    ),
    "image toolchain differs": (
        _document("image/image.json", lambda image: image["toolchain"].update(version="other")),
        IDENTITIES,
    ),
    "image compiler dependencies differ": (
        _document("image/image.json", lambda image: image.update(compiler_dependencies={})),
        IDENTITIES,
    ),
    "image firmware digest differs": (
        _document("image/image.json", lambda image: image.update(firmware_sha256=ZERO)),
        IDENTITIES,
    ),
    "compiler identity incomplete": (
        _document(
            "image/preparation.json", lambda preparation: preparation["toolchain"].pop("version")
        ),
        "compiler identity is invalid",
    ),
    "record digest declared wrong": (
        _document("image/preparation.json", _first_value("dependency_records")),
        "preprocessing record identities disagree",
    ),
    "no preparation inputs": (
        _document("image/preparation.json", lambda preparation: preparation.update(inputs={})),
        "preparation input identities disagree",
    ),
    "input digest declared wrong": (
        _document("image/preparation.json", _first_value("inputs")),
        "preparation input identities disagree",
    ),
}
DECLARATION_CASES: Final[Cases] = {
    "LQR declared": (_declaration(_swap("controller.name", ("pid", "lqr"))), DECLARATION),
    "another plant declared": (
        _declaration(_swap("plant.name", ("second_order_mechanical", "first_order_thermal"))),
        DECLARATION,
    ),
    "coefficient declared": (
        _declaration(lambda manifest: manifest["controller"]["coefficients"].update(kp=7)),
        DECLARATION,
    ),
    "cycle count declared": (
        _declaration(lambda manifest: manifest.update(cycle_count=manifest["cycle_count"] + 1)),
        DECLARATION,
    ),
    "period declared": (
        _declaration(
            lambda manifest: manifest.update(
                sample_period_ticks=manifest["sample_period_ticks"] + 1
            )
        ),
        DECLARATION,
    ),
    "fixed point declared": (
        _declaration(lambda manifest: manifest["plant"].update(fixed_point_format="Q16.16")),
        DECLARATION,
    ),
    "tracking unit declared": (
        _declaration(lambda manifest: manifest["plant"].update(tracking_unit="volts")),
        DECLARATION,
    ),
    "run bound to a reformatted domain": (
        _copied(
            "measurement-domain.json",
            "measurement_domain",
            lambda content: json.dumps(json.loads(content), indent=1).encode(),
        ),
        DECLARATION,
    ),
    "run bound to other events": (_copied("events.bin", "events", _later_tick), DECLARATION),
    "tracking file changed": (_tracking_changed, DECLARATION),
    "fault declared": (
        _declaration(
            lambda manifest: manifest.update(
                fault_schedule=[{"cycle": 1, "kind": "drop", "delay_periods": 0}]
            )
        ),
        "fault schedule does not match captured FAULT_INJECTED events",
    ),
    "overflow declared": (
        _declaration(lambda manifest: manifest["instrument"].update(fifo_overflow_count=1)),
        COUNTERS,
    ),
    "logged miss": (_completion(lambda counters: counters.update(misses=1)), COUNTERS),
    "logged safe state": (_completion(lambda counters: counters.update(safe=True)), COUNTERS),
    "deadline record removed": (_deadline_removed, COUNTERS),
}
SCENARIO_CASES: Final[Cases] = {
    "captured scenario": (lambda _: None, None),
    "longer delay declared": (
        _declaration(lambda manifest: manifest["fault_schedule"][0].update(delay_periods=9)),
        DECLARATION,
    ),
}


def _analysed_alike(capture: Path, cases: Cases, directory: Path) -> None:
    """Require both analyses to report or refuse every case of one capture alike.

    Parameters
    ----------
    capture
        Real capture with its run manifest.
    cases
        Changes and the fragment of Python's refusal each must reach, or ``None`` for a report.
    directory
        Owned directory for the case copies and the native outcomes.
    """
    differing, misplaced = [], []
    for index, (name, (change, fragment)) in enumerate(cases.items()):
        run = directory / f"case-{index}"
        shutil.copytree(capture, run, symlinks=True)
        change(run)
        _bind(run)
        python = python_outcome(run / "manifest.json")
        native = rust_outcome(run / "manifest.json", directory / f"native-{index}")
        if canonical(native) != canonical(python):
            differing.append(name)
        refusal = python.get("refusal") or python.get("report_refusal") or ""
        reached = (
            not refusal and "amp_completion" in python["report"]["report"]
            if fragment is None
            else fragment in refusal
        )
        if not reached:
            misplaced.append((name, refusal))
    assert (differing, misplaced) == ([], [])


def test_amp_runs_analyse_alike(capture_arguments: list[str], tmp_path: Path) -> None:
    """Analyse a real capture and its changed receipts, artifacts and declarations alike.

    Parameters
    ----------
    capture_arguments
        Actual source-bound image, Spike and production plugin.
    tmp_path
        Owned directory for the capture, the case copies and the native outcomes.
    """
    assert capture_main(capture_arguments) == 0
    cases = RECEIPT_CASES | ARTIFACT_CASES | DECLARATION_CASES
    _analysed_alike(tmp_path / "capture", cases, tmp_path)


@pytest.mark.parametrize("scenario_capture", [("lqr", True, "delay", 2)], indirect=True)
def test_amp_scenarios_analyse_alike(scenario_capture: Path, tmp_path: Path) -> None:
    """Analyse an LQR capture of the thermal plant with a delay fault alike, C and Rust kernels.

    Parameters
    ----------
    scenario_capture
        Real capture of the scenario.
    tmp_path
        Owned directory for the case copies and the native outcomes.
    """
    _analysed_alike(scenario_capture, SCENARIO_CASES, tmp_path)
