# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — control-run command parity between the Python and native analyses

"""Run the Python and the native analysis command on the same real captures.

Each case requires the same exit status, the same printed lines and, when a
report is published, byte-equal report directories with the same mode. Kernel
faults during publication are real: an unwritable parent, a file-size limit,
and failures a tracer injects into directory creation and renaming.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from control_rust_support import python_command, rust_command
from test_control_run_parity import CODES, _bind, _cycle, _edit_events

MakeRtlRun = Callable[..., tuple[Path, dict[str, Any]]]
DEFAULT_OUTPUTS = ("python-report", "rust-report")
IGNORE_XFSZ = ["sh", "-c", "trap '' XFSZ; exec \"$@\"", "sh"]
# Final cumulative energies of three rails over the capture's three cycles, and the
# per-cycle plot labels Python prints for them with ``.6g``.
ENERGY_VARIANTS = {
    "energy formats": {"VDD": "370368", "VDD25": "4.5e7", "VDDA25": "7.5e-7"},
    "energy rounding": {"VDD": "2999998.5", "VDD25": "299998.5", "VDDA25": "0.000370370367"},
}
PLOT_LABELS = {
    "energy formats": ("123456", "1.5e+07", "2.5e-07", "0.4"),
    "energy rounding": ("1e+06", "99999.5", "0.000123457", "0.4"),
}


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


def _files(directory: Path) -> dict[str, bytes]:
    """Return every file of a report directory by name.

    Parameters
    ----------
    directory
        Published report directory.

    Returns
    -------
    dict[str, bytes]
        File contents.
    """
    return {path.name: path.read_bytes() for path in sorted(directory.iterdir())}


def _variant(variant: str, run: Path, manifest: dict[str, Any]) -> None:
    """Change one real CONTROL capture into a report variant.

    Parameters
    ----------
    variant
        ``escaped unit`` for a plant unit that needs every JSON string escape,
        ``no power`` for a run without an energy series, ``gapped samples``
        for a cycle without its sample read and tracking row, or ``energy
        formats`` for rail energies whose plot labels need every ``.6g`` form.
    run
        Run directory.
    manifest
        Declaration changed in place.
    """
    energies = ENERGY_VARIANTS.get(variant)
    if variant == "escaped unit":
        manifest["plant"]["tracking_unit"] = 'q"b\\s\nn\rr\tt\bb\ff' + chr(1) + chr(0x7F) + "é"
    elif variant == "no power":
        manifest["files"]["power"] = None
    elif variant == "gapped samples":
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
    elif variant == "extreme ticks":
        manifest["files"]["power"] = None

        def saturate(records: list[bytearray]) -> list[bytearray]:
            """Hold every record from cycle 0's last onwards at the top of the 64-bit counter."""
            last = max(index for index, record in enumerate(records) if _cycle(record) == 0)
            for record in records[last:]:
                record[8:16] = (2**64 - 1).to_bytes(8, "little")
            return records

        _edit_events(run, manifest, saturate)
    elif energies is not None:
        power = (run / "power.csv").read_text(encoding="utf-8")
        for rail, energy in energies.items():
            power = re.sub(
                rf"^15021,{rail},(.*),[^,]*$",
                rf"15021,{rail},\g<1>,{energy}",
                power,
                flags=re.MULTILINE,
            )
        _bind(run, manifest, "power", power.encode())


@pytest.mark.parametrize(
    "variant",
    [
        "CONTROL",
        "COMPUTE",
        "escaped unit",
        "no power",
        "gapped samples",
        "energy formats",
        "energy rounding",
        "extreme ticks",
    ],
)
@pytest.mark.parametrize(
    "outputs", [("report-python", "report-rust"), ("./py//report/", "./rs//report/")]
)
def test_reports_are_byte_equal(
    variant: str, outputs: tuple[str, str], make_rtl_run: MakeRtlRun, tmp_path: Path
) -> None:
    """Publish byte-equal report directories for real captures.

    Parameters
    ----------
    variant
        Event profile of the capture, or a changed capture: every JSON string
        escape in the plant unit, no energy series, a gapped sample, rail
        energies whose plot labels need each ``.6g`` form or round across a
        form, or a COMPUTE capture whose counter saturates after cycle 0 so an
        adjacent-cycle change exceeds the signed 64-bit range.
    outputs
        Output arguments of the Python and native commands.
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directory.
    """
    run, manifest = make_rtl_run(
        "COMPUTE" if variant in {"COMPUTE", "extreme ticks"} else "CONTROL"
    )
    _variant(variant, run, manifest)
    _write(run, manifest)
    for output in outputs:
        (run / output).parent.mkdir(parents=True, exist_ok=True)
    python = python_command(["manifest.json", "--output-dir", outputs[0]], run)
    rust = rust_command(["manifest.json", "--output-dir", outputs[1]], run, tmp_path)
    assert python["status"] == 0, python["stderr"]
    assert rust == {
        "status": 0,
        "stdout": python["stdout"].replace(str(Path(outputs[0])), str(Path(outputs[1]))),
        "stderr": "",
    }
    python_files = _files(run / outputs[0])
    assert ("energy_per_cycle.svg" in python_files) is (
        variant not in {"no power", "extreme ticks"}
    )
    if variant in PLOT_LABELS:
        plot = python_files["energy_per_cycle.svg"].decode()
        assert all(f">{label}<" in plot for label in PLOT_LABELS[variant]), plot
    if variant == "extreme ticks":
        changes = python_files["cycle_jitter.csv"].decode()
        assert ",-18446744073709551" in changes, changes
    assert len(python_files) >= 7
    assert _files(run / outputs[1]) == python_files
    mode = (run / outputs[0]).stat().st_mode & 0o777
    assert (run / outputs[1]).stat().st_mode & 0o777 == mode


def _refused_input(change: str, run: Path, manifest: dict[str, Any]) -> tuple[str, tuple[str, str]]:
    """Prepare one refused command input.

    Parameters
    ----------
    change
        Name of the refused input.
    run
        Run directory with its valid written manifest.
    manifest
        Valid declaration.

    Returns
    -------
    tuple[str, tuple[str, str]]
        Manifest argument and the output arguments of the two commands.
    """
    path = run / "manifest.json"
    arguments = {
        "absent manifest": "absent.json",
        "symlink manifest": "link.json",
        "directory manifest": ".",
        "fifo manifest": "fifo.json",
    }
    outputs = {
        "existing output": ("taken", "taken"),
        "missing parent": ("absent/python-report", "absent/rust-report"),
        "dot output": (".", "."),
        "parent output": ("..", ".."),
        "root output": ("/", "/"),
        "up output": ("sub/..", "sub/.."),
    }
    if change == "existing output":
        (run / "taken").mkdir()
    elif change == "up output":
        (run / "sub").mkdir()
    elif change == "invalid json":
        path.write_text("{", encoding="utf-8")
    elif change == "symlink manifest":
        (run / "link.json").symlink_to(path)
    elif change == "fifo manifest":
        os.mkfifo(run / "fifo.json")
    elif change == "oversized manifest":
        path.write_bytes(b"{" + b" " * (16 * 1048576) + b"}")
    elif change == "wide integer":
        text = json.dumps(manifest)[:-1] + ', "extra": 18446744073709551616}'
        path.write_text(text, encoding="utf-8")
    elif change == "damaged series":
        content = b"cycle,reference,output\n"
        (run / "tracking.csv").write_bytes(content)
        manifest["files"]["tracking"]["sha256"] = hashlib.sha256(content).hexdigest()
        _write(run, manifest)
    return arguments.get(change, "manifest.json"), outputs.get(change, DEFAULT_OUTPUTS)


EXISTING_OUTPUTS = {"existing output", "dot output", "parent output", "root output", "up output"}


@pytest.mark.parametrize(
    "change",
    [
        "existing output",
        "missing parent",
        "dot output",
        "parent output",
        "root output",
        "up output",
        "invalid json",
        "absent manifest",
        "symlink manifest",
        "directory manifest",
        "fifo manifest",
        "oversized manifest",
        "wide integer",
        "damaged series",
    ],
)
def test_refusals_are_identical(change: str, make_rtl_run: MakeRtlRun, tmp_path: Path) -> None:
    """Refuse each command input alike, with nothing published.

    Parameters
    ----------
    change
        The refused input.
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directory.
    """
    run, manifest = make_rtl_run()
    _write(run, manifest)
    argument, outputs = _refused_input(change, run, manifest)
    python = python_command([argument, "--output-dir", outputs[0]], run)
    rust = rust_command([argument, "--output-dir", outputs[1]], run, tmp_path)
    assert python["status"] == 1
    assert rust == {
        "status": 1,
        "stdout": "",
        "stderr": python["stderr"].replace(outputs[0], outputs[1]),
    }
    if change not in EXISTING_OUTPUTS:
        assert not (run / outputs[1]).exists()


def _paths(run: Path) -> None:
    """Create the directories and links the output path cases name.

    Parameters
    ----------
    run
        Run directory.
    """
    (run / "real").mkdir()
    (run / "sub").mkdir()
    (run / "relative-link").symlink_to("real")
    (run / "absolute-link").symlink_to(run / "real")
    (run / "loop-a").symlink_to("loop-b")
    (run / "loop-b").symlink_to("loop-a")
    (run / "dangling").symlink_to("missing-target")


@pytest.mark.parametrize(
    "output",
    [
        "{run}/absolute-output/{side}",
        "/{run}/absolute-output/{side}",
        "//{run}/absolute-output/{side}",
        "sub/../{side}",
        "relative-link/{side}",
        "absolute-link/{side}",
        "relative-link/../relative-link/{side}",
        "loop-a/{side}",
        "dangling/{side}",
    ],
)
def test_output_paths_resolve_alike(output: str, make_rtl_run: MakeRtlRun, tmp_path: Path) -> None:
    """Resolve each output parent as Python's non-strict ``Path.resolve`` does.

    Parameters
    ----------
    output
        Output argument template; ``{side}`` names each command's own report.
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directory.
    """
    run, manifest = make_rtl_run()
    _write(run, manifest)
    _paths(run)
    (run / "absolute-output").mkdir()
    python_output = output.format(run=run, side="python-report")
    rust_output = output.format(run=run, side="rust-report")
    python = python_command(["manifest.json", "--output-dir", python_output], run)
    rust = rust_command(["manifest.json", "--output-dir", rust_output], run, tmp_path)
    assert rust == {
        "status": python["status"],
        "stdout": python["stdout"].replace("python-report", "rust-report"),
        "stderr": python["stderr"].replace("python-report", "rust-report"),
    }
    assert (python["status"] == 0) is (
        output.split("/", maxsplit=1)[0] not in {"loop-a", "dangling"}
    )


def test_unreadable_output_link_is_kept_as_written(
    make_rtl_run: MakeRtlRun, tmp_path: Path
) -> None:
    """A link whose target cannot be read stays in the resolved parent as written.

    Parameters
    ----------
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directory.
    """
    run, manifest = make_rtl_run()
    _write(run, manifest)
    _paths(run)
    trace = tmp_path / "trace"

    def wrapper(name: str) -> list[str]:
        """Return a tracer that fails every readlink of the output link.

        Parameters
        ----------
        name
            Trace file suffix.

        Returns
        -------
        list[str]
            Argument vector prefix.
        """
        link = str(run / "relative-link")
        return [
            "strace",
            "-f",
            "-qq",
            "-P",
            link,
            "-e",
            "trace=readlink",
            "-e",
            "inject=readlink:error=EIO",
            "-o",
            f"{trace}-{name}",
        ]

    python = python_command(
        ["manifest.json", "--output-dir", "relative-link/python-report"], run, wrapper("python")
    )
    rust = rust_command(
        ["manifest.json", "--output-dir", "relative-link/rust-report"],
        run,
        tmp_path,
        wrapper("rust"),
    )
    assert "INJECTED" in Path(f"{trace}-python").read_text(encoding="utf-8")
    assert "INJECTED" in Path(f"{trace}-rust").read_text(encoding="utf-8")
    assert python["status"] == 0, python["stderr"]
    assert rust == {
        "status": 0,
        "stdout": python["stdout"].replace("python-report", "rust-report"),
        "stderr": "",
    }


def test_a_removed_working_directory_is_refused_alike(
    make_rtl_run: MakeRtlRun, tmp_path: Path
) -> None:
    """A relative output under a removed working directory cannot be resolved.

    Parameters
    ----------
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directory.
    """
    run, manifest = make_rtl_run()
    manifest_path = str(_write(run, manifest))
    outcomes = []
    for side in ("python", "rust"):
        gone = tmp_path / f"gone-{side}"
        gone.mkdir()
        wrapper = ["sh", "-c", 'rmdir "$PWD" && exec "$@"', "sh"]
        arguments = [manifest_path, "--output-dir", "report"]
        if side == "python":
            outcomes.append(python_command(arguments, gone, wrapper))
        else:
            outcomes.append(rust_command(arguments, gone, tmp_path / "rust", wrapper))
    assert (
        outcomes[0]
        == outcomes[1]
        == {
            "status": 1,
            "stdout": "",
            "stderr": "run analysis: FAIL: [Errno 2] No such file or directory\n",
        }
    )


DISPATCH_DOCUMENTS = {
    "neural deep": '{"schema_id": 1, "x": ' + "[" * 70 + "]" * 70 + "}",
    "very deep": '{"x": ' + "[" * 20000 + "]" * 20000 + "}",
    "deep invalid": '{"x": ' + "[" * 70 + "]" * 70 + ", }",
    "wide integer then invalid": '{"x": 18446744073709551616, }',
    "huge integer": '{"x": ' + "9" * 5000 + "}",
    "repeated unpaired name": '{"\\ud800": 1, "\\ud800": 2}',
    "distinct unpaired names": '{"\\ud800": 1, "\\ud801": 2}',
}


@pytest.mark.parametrize("name", list(DISPATCH_DOCUMENTS))
def test_dispatch_refusals_are_identical(name: str, tmp_path: Path) -> None:
    """Choose the analysis of each document alike, and refuse it with the same text.

    The choice itself, neural included, is held for every document of the
    shared JSON corpus; these documents reach a printed refusal of the
    dispatcher or of the CONTROL loader.

    Parameters
    ----------
    name
        Document that nests deeply, holds a wide integer or an unpaired
        surrogate, or repeats a name that holds one.
    tmp_path
        Owned run directory.
    """
    (tmp_path / "manifest.json").write_text(DISPATCH_DOCUMENTS[name], encoding="utf-8")
    python = python_command(["manifest.json", "--output-dir", "report"], tmp_path)
    rust = rust_command(["manifest.json", "--output-dir", "report"], tmp_path, tmp_path / "rust")
    assert python["status"] == 1
    assert rust == python
    assert not (tmp_path / "report").exists()


def _traced(syscall: str, error: str, when: int, trace: Path) -> list[str]:
    """Return a tracer that fails one invocation of one system call.

    Parameters
    ----------
    syscall
        Traced system call.
    error
        Injected error name.
    when
        Failed invocation, counted from one.
    trace
        Trace file.

    Returns
    -------
    list[str]
        Argument vector prefix.
    """
    return [
        "strace",
        "-f",
        "-qq",
        "-e",
        f"trace={syscall}",
        "-e",
        f"inject={syscall}:error={error}:when={when}",
        "-o",
        str(trace),
    ]


def _anonymous(text: str, side: str) -> str:
    """Name the report and the probe directory alike on both sides.

    Parameters
    ----------
    text
        Printed text.
    side
        ``python`` or ``rust``.

    Returns
    -------
    str
        Text with the side's report name and the probe's unique suffix replaced.
    """
    text = text.replace(f"{side}-report", "side-report")
    return re.sub(r"\.report-publication-probe\.[^/']+", ".report-publication-probe.*", text)


FAULTS = {
    "unwritable parent": None,
    "probe directory": ("mkdir", "EACCES", 2),
    "probe rename": ("renameat2", "EIO", 1),
    "final rename": ("renameat2", "EIO", 2),
    "file size": None,
}


@pytest.mark.parametrize("fault", list(FAULTS))
def test_publication_faults_are_refused_alike(
    fault: str, make_rtl_run: MakeRtlRun, tmp_path: Path
) -> None:
    """Refuse each kernel fault during publication alike and leave nothing behind.

    Parameters
    ----------
    fault
        An unwritable report parent, a failed probe directory, a failed probe
        or final rename, or a file-size limit below the report size.
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directory.
    """
    run, manifest = make_rtl_run()
    _write(run, manifest)
    parent = run / "reports"
    parent.mkdir()
    outcomes = {}
    for side in ("python", "rust"):
        trace = tmp_path / f"{side}.trace"
        injected = FAULTS[fault]
        wrapper: list[str] = [] if injected is None else _traced(*injected, trace)
        limit = None
        if fault == "file size":
            wrapper = (
                IGNORE_XFSZ
                if side == "rust"
                else [*IGNORE_XFSZ[:2], "trap '' XFSZ; ulimit -f 1; exec \"$@\"", "sh"]
            )
            limit = 512
        elif side == "python":
            wrapper = [*wrapper, "env", "PYTHONDONTWRITEBYTECODE=1"]
        arguments = ["manifest.json", "--output-dir", f"reports/{side}-report"]
        if fault == "unwritable parent":
            parent.chmod(0o500)
        try:
            if side == "python":
                outcome = python_command(arguments, run, wrapper)
            else:
                outcome = rust_command(arguments, run, tmp_path / "rust", wrapper, limit)
        finally:
            parent.chmod(0o700)
        if injected is not None:
            assert "INJECTED" in trace.read_text(encoding="utf-8")
        outcomes[side] = {**outcome, "stderr": _anonymous(outcome["stderr"], side)}
        assert list(parent.iterdir()) == []
    assert outcomes["python"]["status"] == 1, outcomes["python"]
    assert outcomes["rust"] == outcomes["python"]
