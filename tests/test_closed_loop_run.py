# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — closed-loop benchmark data through the real harness and both analyses

"""Build the real harness, produce a campaign and hold both analyses to byte-equal reports."""

from __future__ import annotations

import contextlib
import csv
import hashlib
import json
import struct
import subprocess
from pathlib import Path
from typing import Any

import pytest
from closed_loop_run import main
from closed_loop_stimulus import (
    COEFFICIENTS,
    MAXIMUM_CYCLES,
    MAXIMUM_SEED,
    SKIP_INTERVAL,
    declaration,
    expected_counts,
    harness_arguments,
)
from control_rust_support import python_command, rust_campaign_command, rust_command
from run_manifest import load_run

from conftest import REPOSITORY_ROOT
from loop_timing_witness.host_profile import build_jobs, scaled
from manifest_io import canonical_json_bytes

CYCLES = 200
SEED = 7
# Harness argument replacements by refusal case: the declared item and its substitute.
REPLACEMENTS: dict[str, tuple[str, str | None]] = {
    "missing": ("seed=7", None),
    "malformed": ("seed=7", "seed"),
    "empty key": ("seed=7", "=7"),
    "text": ("cycles=200", "cycles=abc"),
    "short": ("cycles=200", "cycles=15"),
    "overflow": ("seed=7", "seed=99999999999999999999"),
    "late write": ("gap_span=780", "gap_span=5000"),
    "write at the deadline": ("gap_span=780", "gap_span=4780"),
    "late fault": ("fault_cycle=192", "fault_cycle=200"),
    "early fault": ("fault_cycle=192", "fault_cycle=3"),
    "coefficients": ("kp=33554432", "kp=-1"),
}


@pytest.fixture(scope="module")
def harness(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the harness with the repository's Make target into an owned directory.

    Parameters
    ----------
    tmp_path_factory
        Session temporary directory factory.

    Returns
    -------
    Path
        Built harness executable.
    """
    directory = tmp_path_factory.mktemp("closed-loop-build")
    subprocess.run(
        [
            "make",
            "closed-loop-harness",
            f"CLOSED_LOOP_DIRECTORY={directory}",
            f"VERILATOR_JOBS={build_jobs()}",
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        timeout=scaled(900),
    )
    return directory / "closed_loop_harness"


@pytest.fixture(scope="module")
def campaign(harness: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Produce one two-repeat campaign through the public command.

    Parameters
    ----------
    harness
        Built harness executable.
    tmp_path_factory
        Session temporary directory factory.

    Returns
    -------
    Path
        Campaign directory.
    """
    output = tmp_path_factory.mktemp("closed-loop") / "campaign"
    arguments = ["--output", str(output), "--cycles", str(CYCLES), "--repeats", "2"]
    status = main([*arguments, "--seed", str(SEED), "--harness", str(harness), "--jobs", "2"])
    assert status == 0
    return output


def _files(directory: Path) -> dict[str, bytes]:
    """Return every published report file by name."""
    return {path.name: path.read_bytes() for path in sorted(directory.iterdir())}


def test_campaign_binds_every_repeat(campaign: Path) -> None:
    """Each repeat is hash-bound, loadable and declares exactly what the harness ran."""
    document = json.loads((campaign / "campaign.json").read_text())
    assert [entry["repeat_index"] for entry in document["repeats"]] == [1, 2]
    for index, entry in enumerate(document["repeats"], start=1):
        run = campaign / f"repeat-{index}"
        manifest_bytes = (run / "manifest.json").read_bytes()
        assert entry["run_manifest"]["sha256"] == hashlib.sha256(manifest_bytes).hexdigest()
        manifest = load_run(run / "manifest.json").manifest
        assert manifest["source"]["kind"] == "rtl_simulation"
        assert manifest["source"]["tool"] == "Verilator"
        bound = {item["path"] for item in manifest["source"]["files"]}
        assert {
            "closed_loop_harness",
            "stimulus.json",
            "summary.json",
            "trajectory.csv",
            "source/rtl/control_plant_witness.sv",
            "source/benchmarks/closed_loop_harness.cpp",
            "source/controllers/c/witness_controller.c",
        } <= bound
        assert manifest["files"]["power"] is None
        assert manifest["fault_schedule"] == [
            {"cycle": CYCLES - 8, "kind": "delay", "delay_periods": 3}
        ]
        seed = SEED + index - 1
        assert (run / "stimulus.json").read_bytes() == canonical_json_bytes(
            declaration(CYCLES, seed)
        )
        summary = json.loads((run / "summary.json").read_text())
        assert {key: summary[key] for key in ("skipped_writes", "misses")} == expected_counts(
            CYCLES
        )
        assert (summary["cycles"], summary["overflow"], summary["safe"]) == (CYCLES, 0, True)


def test_repeats_are_deterministic_and_seeded(
    harness: Path, campaign: Path, tmp_path: Path
) -> None:
    """The same seed reproduces every byte of the data; another seed changes the timing."""
    output = tmp_path / "again"
    arguments = ["--output", str(output), "--cycles", str(CYCLES), "--seed", str(SEED)]
    assert main([*arguments, "--harness", str(harness)]) == 0
    for name in ("events.bin", "trajectory.csv", "tracking.csv", "summary.json"):
        first = (campaign / "repeat-1" / name).read_bytes()
        assert (output / "repeat-1" / name).read_bytes() == first
    second = (campaign / "repeat-2" / "events.bin").read_bytes()
    assert second != (campaign / "repeat-1" / "events.bin").read_bytes()


def test_run_reports_are_byte_equal_across_languages(campaign: Path, tmp_path: Path) -> None:
    """Both analyses publish the same report for a closed-loop repeat, with its declared faults."""
    run = campaign / "repeat-1"
    outputs = (str(tmp_path / "python-report"), str(tmp_path / "rust-report"))
    python = python_command(["manifest.json", "--output-dir", outputs[0]], run)
    rust = rust_command(["manifest.json", "--output-dir", outputs[1]], run, tmp_path / "rs")
    assert python["status"] == 0, python["stderr"]
    assert rust == {**python, "stdout": python["stdout"].replace(*outputs)}
    assert _files(Path(outputs[1])) == _files(Path(outputs[0]))
    report: dict[str, Any] = json.loads((Path(outputs[0]) / "report.json").read_text())
    control = report["events"]["control"]
    assert control["deadline_misses"] == expected_counts(CYCLES)["misses"]
    assert (control["fault_injections"], control["fault_detections"]) == (1, 1)
    assert (control["safe_state_events"], control["observed_deadlines"]) == (1, CYCLES)
    assert report["tracking_error"]["status"] == "available"
    assert (report["valid"], report["invalid_reasons"]) == (False, ["power series unavailable"])


def test_campaign_reports_are_byte_equal_across_languages(campaign: Path, tmp_path: Path) -> None:
    """Both campaign commands report the repeats alike; without power no repeat is valid.

    A campaign with no valid repeat is published and reported as incomplete, status 2.
    """
    outputs = (str(tmp_path / "python-campaign"), str(tmp_path / "rust-campaign"))
    path = str(campaign / "campaign.json")
    python = python_command([path, "--output-dir", outputs[0]], tmp_path, campaign=True)
    rust = rust_campaign_command([path, "--output-dir", outputs[1]], tmp_path, tmp_path / "rs")
    assert (python["status"], python["stderr"]) == (2, "")
    assert python["stdout"].startswith(f"repeat campaign: INCOMPLETE: {outputs[0]}\n")
    assert rust == {**python, "stdout": python["stdout"].replace(*outputs)}
    assert _files(Path(outputs[1])) == _files(Path(outputs[0]))
    report = json.loads((Path(outputs[0]) / "campaign_report.json").read_text())
    assert [item["status"] for item in report["repeats"]] == ["invalid", "invalid"]


def _script(tmp_path: Path, body: str) -> Path:
    """Write an executable stand-in harness with the given shell body."""
    path = tmp_path / "stand-in"
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


GOOD_SUMMARY = {"cycles": 32, "overflow": 0, "safe": True, **expected_counts(32)}
# Command values and stand-in harness bodies by refusal case.
REFUSAL_VALUES: dict[str, dict[str, str]] = {
    "short": {"--cycles": "15"},
    "no repeats": {"--repeats": "0"},
    "too many repeats": {"--repeats": "65"},
    "most repeats": {"--repeats": "64"},
    "negative seed": {"--seed": "-1"},
}
STAND_INS: dict[str, str] = {
    "harness refusal": "echo declared refusal >&2\nexit 1\n",
    "summary list": "echo '[]'\n",
    "unsafe summary": f"echo '{json.dumps({**GOOD_SUMMARY, 'safe': False})}'\n",
    "overflow summary": f"echo '{json.dumps({**GOOD_SUMMARY, 'overflow': 1})}'\n",
}


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("existing", "output directory already exists"),
        ("most repeats", "output directory already exists"),
        ("short", "cycles must be in [16, 4294967295]"),
        ("no repeats", "repeats must be in [1, 64]"),
        ("too many repeats", "repeats must be in [1, 64]"),
        ("negative seed", f"seed must be in [0, {MAXIMUM_SEED}]"),
        ("absent harness", "harness binary is missing; run make closed-loop-harness"),
        ("harness refusal", "harness refused repeat: declared refusal"),
        ("wrong summary", "harness summary differs from the declared stimulus"),
        ("summary list", "harness summary differs from the declared stimulus"),
        ("unsafe summary", "harness summary differs from the declared stimulus"),
        ("overflow summary", "harness summary differs from the declared stimulus"),
    ],
)
def test_command_refusals(
    case: str, message: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every refusal is one line and leaves no campaign manifest."""
    output = tmp_path / "campaign"
    values = {"--cycles": "32", "--repeats": "1", "--seed": "1"} | REFUSAL_VALUES.get(case, {})
    harness = _script(tmp_path, STAND_INS.get(case, "echo '{\"cycles\": 32}'\n"))
    if case in {"existing", "most repeats"}:
        output.mkdir()
    if case == "absent harness":
        harness = tmp_path / "absent"
    arguments = [item for pair in values.items() for item in pair]
    assert main(["--output", str(output), *arguments, "--harness", str(harness)]) == 1
    assert capsys.readouterr().err == f"closed-loop run refused: {message}\n"
    assert not (output / "campaign.json").exists()


def _null() -> contextlib.nullcontext[None]:
    """Return a context that supplies no output stream."""
    return contextlib.nullcontext()


def _harness_arguments() -> list[str]:
    """Return the declared argument vector of a 200-cycle run."""
    return [f"{key}={value}" for key, value in harness_arguments(CYCLES, SEED).items()]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("usage", "usage: closed_loop_harness events.bin trajectory.csv key=value..."),
        ("missing", "missing stimulus value: seed"),
        ("malformed", "malformed or repeated argument: seed"),
        ("repeated", "malformed or repeated argument: seed=7"),
        ("empty key", "malformed or repeated argument: =7"),
        ("text", "invalid stimulus value: cycles"),
        ("short", "invalid stimulus value: cycles"),
        ("overflow", "invalid stimulus value: seed"),
        ("unknown", "unknown stimulus argument"),
        ("late write", "service offsets do not end before the deadline"),
        ("write at the deadline", "service offsets do not end before the deadline"),
        ("late fault", "fault cycle is outside the run"),
        ("early fault", "fault cycle is outside the run"),
        ("coefficients", "controller coefficients are invalid"),
        ("no directory", "cannot open the output files"),
        ("full events", "cannot write the event file"),
        ("full trajectory", "cannot close the output files"),
        ("full summary", "cannot write the summary"),
    ],
)
def test_harness_refusals(change: str, message: str, harness: Path, tmp_path: Path) -> None:
    """The harness refuses each invalid stimulus or output with one exact diagnostic."""
    arguments = _harness_arguments()
    events, trajectory = str(tmp_path / "events.bin"), str(tmp_path / "trajectory.csv")
    if change in REPLACEMENTS:
        old, new = REPLACEMENTS[change]
        arguments = [item for item in arguments if item != old] + ([new] if new else [])
    arguments += {"repeated": ["seed=7"], "unknown": ["colour=1"]}.get(change, [])
    if change == "no directory":
        events = str(tmp_path / "absent" / "events.bin")
    events = "/dev/full" if change == "full events" else events
    trajectory = "/dev/full" if change == "full trajectory" else trajectory
    command = [str(harness)] if change == "usage" else [str(harness), events, trajectory]
    with Path("/dev/full").open("w") if change == "full summary" else _null() as sink:
        result = subprocess.run(
            [*command, *([] if change == "usage" else arguments)],
            stdout=sink if change == "full summary" else subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=scaled(120),
            check=False,
        )
    assert (result.returncode, result.stdout or "", result.stderr) == (1, "", message + "\n")


@pytest.mark.parametrize("cycles", [16, 99, 100, 103, 106, 107, 108, 200, 1000, 10007])
def test_expected_counts_follow_the_declared_rule(cycles: int) -> None:
    """The closed form equals the withheld-write rule applied to every cycle."""
    fault = cycles - 8
    skipped = sum(
        1
        for cycle in range(cycles)
        if cycle % SKIP_INTERVAL == SKIP_INTERVAL - 1 and cycle + 3 < fault
    )
    assert expected_counts(cycles) == {"skipped_writes": skipped, "misses": skipped + 8}


@pytest.mark.parametrize(
    ("cycles", "seed", "message"),
    [
        (15, 0, "cycles must be in [16, 4294967295]"),
        (MAXIMUM_CYCLES + 1, 0, "cycles must be in [16, 4294967295]"),
        (16, -1, f"seed must be in [0, {MAXIMUM_SEED}]"),
        (16, MAXIMUM_SEED + 1, f"seed must be in [0, {MAXIMUM_SEED}]"),
    ],
)
def test_declared_ranges_refuse(cycles: int, seed: int, message: str) -> None:
    """Out-of-range cycle counts and seeds are refused before any harness runs."""
    with pytest.raises(ValueError, match=r"^" + message.replace("[", r"\[") + r"$"):
        harness_arguments(cycles, seed)


def test_declaration_is_complete() -> None:
    """The declaration names the harness, its RTL build and all 25 harness arguments."""
    document = declaration(MAXIMUM_CYCLES, MAXIMUM_SEED)
    arguments = document["arguments"]
    assert isinstance(arguments, dict)
    assert len(arguments) == 25
    assert arguments["fault_cycle"] == MAXIMUM_CYCLES - 8
    assert document["build"] == {
        "top_module": "control_plant_witness",
        "period_ticks": 5000,
        "miss_limit": 3,
        "fifo_address_bits": 14,
        "thermal": False,
    }


def test_public_command_refuses_without_a_traceback(tmp_path: Path) -> None:
    """The standalone command prints one refusal line and exits with status one."""
    result = subprocess.run(
        [
            str(REPOSITORY_ROOT / ".venv/bin/python"),
            "tools/closed_loop_run.py",
            *("--output", str(tmp_path / "campaign"), "--cycles", "15"),
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        timeout=scaled(120),
        check=False,
    )
    assert (result.returncode, result.stdout) == (1, "")
    assert result.stderr == "closed-loop run refused: cycles must be in [16, 4294967295]\n"


def test_last_offset_before_the_deadline_is_accepted(harness: Path, tmp_path: Path) -> None:
    """Offsets that end one tick before the period run; the deadline itself is refused above."""
    arguments = [item for item in _harness_arguments() if item != "gap_span=780"] + [
        "gap_span=4779"
    ]
    result = subprocess.run(
        [str(harness), str(tmp_path / "events.bin"), str(tmp_path / "trajectory.csv"), *arguments],
        capture_output=True,
        text=True,
        timeout=scaled(120),
        check=False,
    )
    assert (result.returncode, result.stderr) == (0, "")
    assert json.loads(result.stdout)["cycles"] == CYCLES


def test_safe_state_holds_the_applied_actuator_at_zero(campaign: Path) -> None:
    """The trajectory records the commanded actuator until the trip and zero after it."""
    with (campaign / "repeat-1" / "trajectory.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [int(row["cycle"]) for row in rows] == list(range(CYCLES))
    fault = CYCLES - 8
    assert all(int(row["actuator"]) == 0 for row in rows[fault + 3 :])
    assert sum(int(row["actuator"]) != 0 for row in rows[1:fault]) == fault - 1


def _ticks(run: Path) -> dict[int, dict[int, int]]:
    """Return each event code's tick by cycle from a repeat's drained records."""
    ticks: dict[int, dict[int, int]] = {}
    for code, _, _, cycle, tick in struct.iter_unpack("<BBHIQ", (run / "events.bin").read_bytes()):
        ticks.setdefault(code, {})[cycle] = tick
    return ticks


def test_manifest_declares_what_the_harness_ran(campaign: Path) -> None:
    """The configuration fields equal the harness build and its events keep the declared period."""
    run = campaign / "repeat-1"
    manifest = json.loads((run / "manifest.json").read_text())
    assert {key: manifest[key] for key in ("profile", "placement", "sample_period_ticks")} == {
        "profile": "CONTROL",
        "placement": "bare_metal_amp",
        "sample_period_ticks": 5000,
    }
    assert (manifest["cycle_count"], manifest["warmup_cycles"]) == (CYCLES, 0)
    assert manifest["controller"] == {"name": "pid_anti_windup", "coefficients": COEFFICIENTS}
    assert manifest["plant"]["name"] == "second_order_mechanical"
    deadlines = _ticks(run)[4]
    assert {deadlines[cycle + 1] - deadlines[cycle] for cycle in range(CYCLES - 1)} == {5000}


def test_service_offsets_follow_the_declaration(campaign: Path) -> None:
    """Reads and writes land at varying offsets inside the declared ranges before the fault."""
    ticks = _ticks(campaign / "repeat-1")
    healthy = range(CYCLES - 8)
    reads = [ticks[2][cycle] - ticks[1][cycle] for cycle in healthy]
    writes = [ticks[3][cycle] - ticks[2][cycle] for cycle in healthy if cycle in ticks[3]]
    assert len(writes) == len(reads) - expected_counts(CYCLES)["skipped_writes"]
    assert min(reads) >= 10
    assert max(reads) <= 199
    assert min(writes) >= 20
    assert max(writes) <= 799
    assert len(set(reads)) > 60
    assert len(set(writes)) > 60


def test_tracking_series_is_the_scaled_trajectory(campaign: Path) -> None:
    """Each tracking row carries the trajectory's reference and output divided by 2^24."""
    run = campaign / "repeat-1"
    with (run / "trajectory.csv").open(encoding="utf-8", newline="") as stream:
        raw = list(csv.DictReader(stream))
    with (run / "tracking.csv").open(encoding="utf-8", newline="") as stream:
        tracking = list(csv.DictReader(stream))
    assert [row["cycle"] for row in tracking] == [row["cycle"] for row in raw]
    for row, source in zip(tracking, raw, strict=True):
        assert float(row["reference"]) == int(source["reference"]) / (1 << 24)
        assert float(row["output"]) == int(source["output"]) / (1 << 24)
    assert any(row["output"] != row["reference"] for row in tracking)


def test_withheld_write_boundary_is_held(harness: Path, tmp_path: Path) -> None:
    """At 107 cycles the write of cycle 96 ends three cycles before the fault and is kept."""
    output = tmp_path / "campaign"
    arguments = ["--output", str(output), "--cycles", "107", "--harness", str(harness)]
    assert main(arguments) == 0
    summary = json.loads((output / "repeat-1" / "summary.json").read_text())
    assert (summary["skipped_writes"], summary["misses"]) == (0, 8)
