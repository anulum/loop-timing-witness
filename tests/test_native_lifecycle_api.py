# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual native lifecycle API boundaries

"""Build actual production RTL and exercise native lifecycle APIs without substitute devices."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from test_native_run import configuration

from conftest import REPOSITORY_ROOT


@pytest.fixture(scope="module", params=[0, 1])
def lifecycle_program(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    """Compile the API corpus with the actual production RTL and native C controller.

    Parameters
    ----------
    request
        Mechanical or thermal production plant selection.
    tmp_path_factory
        Fresh build allocation preventing profiles from another compilation from being merged.

    Returns
    -------
    Path
        Actual API test executable, with strict warnings and compiler instrumentation.
    """
    selected = os.environ.get("WITNESS_LIFECYCLE_BUILD_ROOT")
    base = Path(selected) if selected is not None else tmp_path_factory.mktemp("lifecycle-api")
    directory = base / f"plant_{int(request.param)}"
    directory.mkdir(parents=True, exist_ok=True)
    kernel = directory / "kernel.o"
    rtl_coverage = os.environ.get("WITNESS_RTL_COVERAGE") == "1"
    commands = [
        [
            "gcc",
            "-std=gnu11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wconversion",
            "-Wshadow",
            "-Wstrict-prototypes",
            "-Wmissing-prototypes",
            "-c",
            "controllers/c/witness_controller.c",
            "-o",
            str(kernel),
        ],
        [
            "verilator",
            "--cc",
            "--exe",
            "--build",
            "--Wall",
            *(["--coverage-line"] if rtl_coverage else []),
            "--top-module",
            "axi_control_witness",
            "-j",
            "2",
            "-GPERIOD_TICKS=32768",
            "-GADDRESS_BITS=5",
            "-GGROUP_ADDRESS_BITS=4",
            f"-GTHERMAL=1'b{int(request.param)}",
            "--Mdir",
            str(directory),
            "-CFLAGS",
            "-std=c++17 -Wall -Wextra -Werror --coverage -O2"
            + (" -DWITNESS_RTL_COVERAGE" if rtl_coverage else ""),
            "-LDFLAGS",
            f"{kernel} --coverage -lcrypto",
            "rtl/event_codes_pkg.sv",
            *[
                str(p.relative_to(REPOSITORY_ROOT))
                for p in sorted((REPOSITORY_ROOT / "rtl").glob("*.sv"))
                if p.name != "event_codes_pkg.sv"
            ],
            str(REPOSITORY_ROOT / "tests/native/run_lifecycle_test.cpp"),
            str(REPOSITORY_ROOT / "runtime/run_configuration.cpp"),
            str(REPOSITORY_ROOT / "runtime/linux/file_digest.cpp"),
            "-o",
            "run_lifecycle_test",
        ],
    ]
    for command in commands:
        result = subprocess.run(
            command, cwd=REPOSITORY_ROOT, capture_output=True, text=True, check=False, timeout=90
        )
        assert result.returncode == 0, result.stdout + result.stderr
    return directory / "run_lifecycle_test"


@pytest.mark.parametrize(
    "scenario",
    [
        "read",
        "write",
        "period_mismatch",
        "unstarted",
        "active",
        "unread",
        "recover",
        "hooks",
        "closed",
        "header_limit",
        "event_limit",
        "sample_limit",
        "finish_limit",
        "final_drain",
        "duplicate",
        "out_of_range",
        "invalid_pid",
        "invalid_lqr",
    ],
)
def test_actual_lifecycle_api(lifecycle_program: Path, tmp_path: Path, scenario: str) -> None:
    """Exercise real decoder errors, protected bank reset and callback ordering.

    Parameters
    ----------
    lifecycle_program
        Native test linked directly to the actual production RTL model.
    tmp_path
        Exclusive configuration and possible run output allocation.
    scenario
        Real API state or lifecycle path under test.
    """
    config = tmp_path / "run.conf"
    text = configuration("pid", "none").replace("pid 32", "pid 2")
    if scenario == "event_limit":
        text = configuration("pid", "freeze").replace("pid 32", "pid 256")
    elif scenario == "sample_limit":
        text = (
            configuration("pid", "overload")
            .replace("pid 32", "pid 256")
            .replace("overload 0 3", "overload 0 256")
            .replace("1000 1100000", "1000 0")
        )
    elif scenario == "final_drain":
        text = (
            configuration("pid", "overload")
            .replace("pid 32", "pid 8")
            .replace("overload 0 3", "overload 0 8")
            .replace("1000 1100000", "1000 5000000")
        )
    elif scenario == "finish_limit":
        text = configuration("pid", "none").replace("pid 32", "pid 1")
    config.write_text(text, encoding="utf-8")
    events, raw = tmp_path / "events.bin", tmp_path / "raw.csv"
    result = subprocess.run(
        [str(lifecycle_program), scenario, str(config), str(events), str(raw)],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == f"verified {scenario}\n"
    assert result.stderr == ""
    if os.environ.get("WITNESS_RTL_COVERAGE") == "1":
        assert events.with_name(events.name + ".coverage.dat").stat().st_size > 0
    assert_retained_outputs(scenario, events, raw)


def assert_retained_outputs(scenario: str, events: Path, raw: Path) -> None:
    """Check retained actual FIFO and trace bytes after each lifecycle outcome.

    Parameters
    ----------
    scenario
        Public lifecycle operation exercised by the native child.
    events
        Actual binary FIFO output allocation.
    raw
        Actual controller trace allocation.
    """
    if scenario == "closed":
        assert Path(str(events) + ".copy").read_bytes() == events.read_bytes()[:16]
    if scenario in {"hooks", "closed", "period_mismatch"}:
        assert events.stat().st_size > 0
        assert len(raw.read_text().splitlines()) == 3
    elif scenario == "final_drain":
        assert events.stat().st_size == 20 * 16
        assert len(raw.read_text().splitlines()) == 2
    elif scenario == "recover":
        assert events.stat().st_size > 0
        assert len(raw.read_text().splitlines()) == 1
    elif scenario in {"unstarted", "duplicate", "out_of_range", "invalid_pid", "invalid_lqr"}:
        assert events.read_bytes() == b""
        assert len(raw.read_text().splitlines()) == (2 if scenario == "duplicate" else 1)
        if scenario == "unstarted":
            assert Path(str(events) + ".recovery").stat().st_size > 0
            assert len(Path(str(raw) + ".recovery").read_text().splitlines()) == 3
    elif scenario == "header_limit":
        assert events.read_bytes() == b""
        assert raw.stat().st_size == 32
    elif scenario in {"event_limit", "sample_limit"}:
        assert 0 < events.stat().st_size <= 512
        assert 0 < raw.stat().st_size <= 512
    elif scenario == "finish_limit":
        assert events.stat().st_size == 64
        assert raw.stat().st_size == 192
    else:
        assert not events.exists()
        assert not raw.exists()
