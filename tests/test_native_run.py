# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — native run lifecycle against actual production RTL

"""Execute real native configuration, controller, fault and binary drain paths."""

from __future__ import annotations

import csv
import os
import struct
import subprocess
from pathlib import Path

import pytest
from test_controller_parity import DEFAULT

from conftest import REPOSITORY_ROOT


@pytest.fixture(scope="module", params=[0, 1])
def native_run(request: pytest.FixtureRequest) -> Path:
    """Build a native controller linked directly to the actual plant/AXI model.

    Parameters
    ----------
    request
        Actual plant mode.

    Returns
    -------
    Path
        Production run simulation executable.
    """
    thermal = int(request.param)
    build_root = Path(os.environ.get("WITNESS_NATIVE_BUILD_ROOT", str(REPOSITORY_ROOT / "build")))
    directory = build_root / f"run_simulation_{thermal}"
    result = subprocess.run(
        [
            "make",
            "run-simulation",
            f"SIMULATION_THERMAL={thermal}",
            f"RUN_SIMULATION_DIRECTORY={directory}",
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return directory / "run_simulation"


def configuration(mode: str, fault: str, reference: int = 0) -> str:
    """Supply every native field with an explicit bounded run and overload model.

    Parameters
    ----------
    mode
        Actual PID or LQR kernel selection.
    fault
        Injected RTL fault, or none.
    reference
        Step, ramp or sine mode.

    Returns
    -------
    str
        Complete public configuration file.
    """
    duration = 0 if fault == "none" else 3 if fault in {"freeze", "overload"} else 1
    workload = "1000 1100000" if fault == "overload" else "0 0"
    return (
        f"{mode} 32 32768\n"
        + " ".join(map(str, DEFAULT))
        + "\n"
        + f"{reference} 16777216 0 16777 1\n"
        + f"{fault} 0 {duration}\n{workload}\n"
    )


@pytest.mark.parametrize(
    "scenario",
    [
        (mode, fault, reference)
        for mode in ["pid", "lqr"]
        for fault, reference in [
            ("none", 0),
            ("none", 1),
            ("none", 2),
            ("drop", 0),
            ("delay", 0),
            ("freeze", 0),
            ("overload", 0),
        ]
    ],
)
def test_real_native_run(
    native_run: Path,
    native_controllers: tuple[Path, Path],
    scenario: tuple[str, str, int],
    tmp_path: Path,
) -> None:
    """Verify final actual misses/safe state and every C/Rust controller transition.

    Parameters
    ----------
    native_run
        Real native controller using in-process production AXI.
    native_controllers
        Actual public C and Rust streaming programs.
    scenario
        Controller, fault and reference modes.
    tmp_path
        Exclusive configuration and raw output storage.
    """
    mode, fault, reference = scenario
    config = tmp_path / "run.conf"
    config.write_text(configuration(mode, fault, reference), encoding="utf-8")
    events, tracking = tmp_path / "events.bin", tmp_path / "tracking_raw.csv"
    result = subprocess.run(
        [str(native_run), str(config), str(events), str(tracking)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("simulation_only ")
    summary = dict(item.split("=") for item in result.stdout.split()[1:])
    assert summary["overflow"] == "0"
    records = list(struct.iter_unpack("<IIQ", events.read_bytes()))
    with tracking.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(records) == int(summary["records"])
    assert len(rows) == int(summary["samples"])
    assert all(records[index][2] <= records[index + 1][2] for index in range(len(records) - 1))
    assert [(code, cycle, ticks) for code, cycle, ticks in records if code == 2] == [
        (2, int(row["cycle"]), int(row["sample_ticks"])) for row in rows
    ]
    check_fault_outcome(summary, rows, records, fault)
    check_native_commands(mode, rows, native_controllers)
    saved = events.read_bytes(), tracking.read_bytes()
    refused = subprocess.run(
        [str(native_run), str(config), str(events), str(tracking)],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert refused.returncode == 1
    assert "exclusive" in refused.stderr
    assert (events.read_bytes(), tracking.read_bytes()) == saved


def check_fault_outcome(
    summary: dict[str, str],
    rows: list[dict[str, str]],
    records: list[tuple[int, int, int]],
    fault: str,
) -> None:
    """Compare actual monitor behavior with the complete configured run duration.

    Parameters
    ----------
    summary
        Actual live statistics read after final drain.
    rows
        Recorded observed controller samples.
    records
        Actual binary event records.
    fault
        Scheduled real RTL injection.
    """
    if fault == "none":
        assert summary["misses"] == "0"
        assert summary["safe"] == "0"
        assert len(rows) == 32
        assert len(records) == 128
    elif fault in {"drop", "delay"}:
        assert summary["misses"] == "1"
        assert summary["safe"] == "0"
        assert len(rows) == 31
    else:
        assert summary["misses"] == "32"
        assert summary["safe"] == "1"
        assert [cycle for code, cycle, _ in records if code == 5] == [2]
        assert any(code == 5 for code, _, _ in records)
    if fault == "overload":
        assert int(rows[0]["overload_work"]) == sum(index * index for index in range(1000))
        assert rows[0]["submitted"] == "0"


def check_native_commands(
    mode: str, rows: list[dict[str, str]], binaries: tuple[Path, Path]
) -> None:
    """Replay all actual observed inputs and compare complete native state fields.

    Parameters
    ----------
    mode
        Actual kernel mode.
    rows
        Recorded inputs and kernel returns from the production native run.
    binaries
        C and Rust public entry points.
    """
    fields = ("cycle", "reference_raw", "output_raw", "velocity_raw")
    outputs = ("cycle", "command_raw", "integral_raw", "derivative_raw", "clipped", "integral_held")
    payload = (
        ",".join(map(str, DEFAULT))
        + "\n"
        + "".join(",".join(row[field] for field in fields) + "\n" for row in rows)
    )
    expected = "".join(",".join(row[field] for field in outputs) + "\n" for row in rows)
    for binary in binaries:
        result = subprocess.run(
            [str(binary), mode],
            input=payload,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout == expected


@pytest.mark.parametrize(
    "invalid",
    [
        "",
        "other 4 32768",
        "pid 0 32768",
        "pid 4 0",
        "pid -1 32768",
        "pid 4294967296 32768",
        "pid 4 32768\n0",
        "pid 4 32768\nNaN",
    ],
)
def test_invalid_configuration(native_run: Path, invalid: str, tmp_path: Path) -> None:
    """Refuse invalid input before creating outputs or starting the simulated run.

    Parameters
    ----------
    native_run
        Production native run entry point.
    invalid
        Malformed configuration.
    tmp_path
        Managed input/output destinations.
    """
    config = tmp_path / "bad.conf"
    config.write_text(invalid, encoding="utf-8")
    events, tracking = tmp_path / "events.bin", tmp_path / "tracking.csv"
    result = subprocess.run(
        [str(native_run), str(config), str(events), str(tracking)],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 1
    assert result.stderr
    assert not events.exists()
    assert not tracking.exists()


def test_run_timer_overflow(native_run: Path, tmp_path: Path) -> None:
    """Refuse a full valid configuration whose declared duration wraps host nanoseconds.

    Parameters
    ----------
    native_run
        Production parser and run lifecycle entry point.
    tmp_path
        Managed configuration and output paths.
    """
    config = tmp_path / "long.conf"
    config.write_text(
        configuration("pid", "none").replace("pid 32 32768", "pid 4294967295 4294967295"),
        encoding="utf-8",
    )
    events, tracking = tmp_path / "events.bin", tmp_path / "tracking.csv"
    result = subprocess.run(
        [str(native_run), str(config), str(events), str(tracking)],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 1
    assert "nanosecond run timer" in result.stderr
    assert not events.exists()
    assert not tracking.exists()
