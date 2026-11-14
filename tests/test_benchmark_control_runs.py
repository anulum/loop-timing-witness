# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — control-run analysis timing through the real commands

"""Time both real analysis commands on a real closed-loop campaign and exercise every refusal."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest
from benchmark_control_runs import NATIVE_PROGRAMS, BenchmarkRequest, host, main, validate
from closed_loop_run import main as generate
from timed_command import latency_statistics, run_timed

from conftest import REPOSITORY_ROOT
from loop_timing_witness.host_profile import scaled

if TYPE_CHECKING:
    from pathlib import Path

CPU = min(os.sched_getaffinity(0))


@pytest.fixture(scope="module")
def campaign(closed_loop_harness: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Produce a two-repeat, 200-cycle closed-loop campaign through the public command.

    Parameters
    ----------
    closed_loop_harness
        Session-built harness executable.
    tmp_path_factory
        Session temporary directory factory.

    Returns
    -------
    Path
        Campaign manifest.
    """
    output = tmp_path_factory.mktemp("timed") / "campaign"
    arguments = ["--output", str(output), "--cycles", "200", "--repeats", "2"]
    assert generate([*arguments, "--harness", str(closed_loop_harness)]) == 0
    return output / "campaign.json"


def _arguments(campaign: Path, native: Path, output: Path, *extra: str) -> list[str]:
    """Return a complete benchmark argument vector."""
    return [
        *("--campaign", str(campaign), "--native", str(native), "--output", str(output)),
        *("--cpu", str(CPU), "--label", "local", *extra),
    ]


def test_both_backends_are_measured_with_provenance(
    campaign: Path, native_analysis_commands: Path, tmp_path: Path
) -> None:
    """Every operation and backend has its samples, statistics and the inputs' digests."""
    output = tmp_path / "benchmark.json"
    assert main(_arguments(campaign, native_analysis_commands, output, "--warmup", "1")) == 0
    artifact = json.loads(output.read_text())
    assert [(row["name"], row["backend"], row["samples"]) for row in artifact["results"]] == [
        ("run", "python", 10),
        ("run", "native", 10),
        ("campaign", "python", 5),
        ("campaign", "native", 5),
    ]
    assert [row["cycles_per_command"] for row in artifact["results"]] == [200, 200, 400, 400]
    assert len(artifact["raw_samples"]) == 6 * 3 * 2
    assert {row["phase"] for row in artifact["raw_samples"][:6]} == {"warmup"}
    mean = {(row["name"], row["backend"]): row["stats"]["mean_ms"] for row in artifact["results"]}
    assert artifact["native_speedup_of_mean"] == {
        name: mean[(name, "python")] / mean[(name, "native")] for name in ("run", "campaign")
    }
    assert artifact["parameters"] == {
        "warmup_passes": 1,
        "measured_passes": 5,
        "repeats": 2,
        "cycles_per_repeat": 200,
    }
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert artifact["base_commit"] == head.stdout.strip()
    assert artifact["evidence_status"] == "nonisolated_workstation"
    assert artifact["host"]["child_affinity"] == [CPU]
    assert {f"native:{name}" for name in NATIVE_PROGRAMS.values()} <= set(artifact["sha256"])
    assert {"repeat-1:events.bin", "repeat-2:tracking.csv", "campaign:campaign.json"} <= set(
        artifact["sha256"]
    )
    assert not list(tmp_path.glob(".benchmark.json.*"))


def _stand_in(tmp_path: Path, native: Path, suffix: str) -> Path:
    """Return a native directory whose run command is a shell stand-in after the real one."""
    directory = tmp_path / "stand-in"
    directory.mkdir()
    shutil.copy2(native / NATIVE_PROGRAMS["campaign"], directory / NATIVE_PROGRAMS["campaign"])
    script = directory / NATIVE_PROGRAMS["run"]
    script.write_text(
        f'#!/bin/sh\n"{native / NATIVE_PROGRAMS["run"]}" "$@"\nstatus=$?\n{suffix}\n',
        encoding="utf-8",
    )
    script.chmod(0o755)
    return directory


# Shell lines appended after the real native run command, and the refusal each causes.
DIFFERENCES: dict[str, tuple[str, str]] = {
    "report": (
        'echo changed >> "$3/report.json"\nexit $status',
        "Python and native run outcomes differ",
    ),
    "text": ("echo extra\nexit $status", "Python and native run outcomes differ"),
    "status": ("exit 1", "native run analysis failed with status 1"),
    "incomplete run": ("exit 2", "native run analysis failed with status 2"),
    "bound input": (
        'echo x >> "$(dirname "$1")/stimulus.json"\nexit $status',
        "python run analysis failed with status 1",
    ),
    "native command": (
        "echo '# changed' >> \"$0\"\nexit $status",
        "a producer, native command or input changed during measurement",
    ),
}


@pytest.mark.parametrize("case", list(DIFFERENCES))
def test_backend_differences_and_changes_are_refused(
    case: str,
    campaign: Path,
    native_analysis_commands: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A changed report, printed text, status or input refuses the whole measurement."""
    suffix, message = DIFFERENCES[case]
    copy = tmp_path / "campaign"
    shutil.copytree(campaign.parent, copy)
    native = _stand_in(tmp_path, native_analysis_commands, suffix)
    output = tmp_path / f"{case}.json"
    assert main(_arguments(copy / "campaign.json", native, output, "--warmup", "0")) == 1
    assert capsys.readouterr().err == f"control-run benchmark refused: {message}\n"
    assert not output.exists()
    assert not list(tmp_path.glob(f".{case}.json.*"))


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("warmup", "warmup must be in [0, 10]"),
        ("passes", "passes must be in [5, 100]"),
        ("many passes", "passes must be in [5, 100]"),
        ("cpu", "benchmark CPU is outside the inherited affinity"),
        ("existing", "output already exists"),
        ("native", "native analysis commands are missing"),
        ("malformed", "campaign manifest does not bind its repeat runs"),
    ],
)
def test_requests_are_refused(
    case: str, message: str, campaign: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Out-of-range parameters, a foreign CPU, an existing output or bad inputs are refused."""
    output, native = tmp_path / "benchmark.json", tmp_path / "native"
    native.mkdir()
    for name in NATIVE_PROGRAMS.values():
        (native / name).write_text("", encoding="utf-8")
    target = campaign
    extra = {"warmup": ["--warmup", "11"], "passes": ["--passes", "4"]}.get(case, [])
    extra = ["--passes", "101"] if case == "many passes" else extra
    arguments = _arguments(target, native, output, *extra)
    if case == "cpu":
        arguments[arguments.index("--cpu") + 1] = str(max(os.sched_getaffinity(0)) + 4096)
    if case == "existing":
        output.write_text("{}", encoding="utf-8")
    if case == "native":
        (native / NATIVE_PROGRAMS["campaign"]).unlink()
    if case == "malformed":
        target = tmp_path / "campaign.json"
        target.write_text('{"repeats": [{}]}', encoding="utf-8")
        arguments[arguments.index("--campaign") + 1] = str(target)
    assert main(arguments) == 1
    assert capsys.readouterr().err == f"control-run benchmark refused: {message}\n"


def test_unreadable_campaign_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A missing campaign manifest is refused with the operating system's reason."""
    native = tmp_path / "native"
    native.mkdir()
    for name in NATIVE_PROGRAMS.values():
        (native / name).write_text("", encoding="utf-8")
    absent = tmp_path / "absent.json"
    assert main(_arguments(absent, native, tmp_path / "benchmark.json")) == 1
    assert capsys.readouterr().err == (
        f"control-run benchmark refused: [Errno 2] No such file or directory: '{absent}'\n"
    )


def test_timed_child_reports_status_output_and_resources(tmp_path: Path) -> None:
    """A child's status, output and resource use are returned and its files removed."""
    sample = run_timed(
        [
            sys.executable,
            "-c",
            "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)",
        ],
        CPU,
        tmp_path,
        scaled(60),
    )
    assert (sample.status, sample.stdout, sample.stderr) == (3, "out\n", "err\n")
    assert sample.elapsed_ns > 0
    assert sample.max_rss_kib > 0
    assert sample.user_seconds >= 0
    assert list(tmp_path.iterdir()) == []


def test_hung_child_is_killed(tmp_path: Path) -> None:
    """The hang guard kills a child that outlives it."""
    sample = run_timed(["sleep", "30"], CPU, tmp_path, 0.2)
    assert sample.status == -9
    assert sample.elapsed_ns < 20_000_000_000


def test_statistics_follow_the_inclusive_percentiles() -> None:
    """Five samples of 1–5 ms give exact percentiles, mean and throughput."""
    stats = latency_statistics([1_000_000, 2_000_000, 3_000_000, 4_000_000, 5_000_000], 300)
    assert stats == {
        "p50_ms": 3.0,
        "p95_ms": pytest.approx(4.8),
        "p99_ms": pytest.approx(4.96),
        "mean_ms": 3.0,
        "min_ms": 1.0,
        "max_ms": 5.0,
        "throughput_cycles_per_second": pytest.approx(100_000.0),
    }


@pytest.mark.parametrize("samples", [[1, 2, 3, 4], [1, 2, 3, 4, 0]])
def test_statistics_refuse_too_few_or_non_positive_samples(samples: list[int]) -> None:
    """Fewer than five samples or a non-positive one cannot be summarised."""
    with pytest.raises(ValueError, match=r"^statistics require 5 positive samples$"):
        latency_statistics(samples, 1)


def test_host_context_without_frequency_scaling() -> None:
    """A CPU without a frequency-scaling governor records none."""
    context = host(max(os.sched_getaffinity(0)) + 4096)
    assert context["scaling_governor"] is None
    assert context["child_affinity"] == [max(os.sched_getaffinity(0)) + 4096]


def test_public_command_refuses_without_a_traceback(tmp_path: Path) -> None:
    """The standalone command prints one refusal line and exits with status one."""
    result = subprocess.run(
        [
            str(REPOSITORY_ROOT / ".venv/bin/python"),
            "tools/benchmark_control_runs.py",
            *_arguments(
                tmp_path / "absent.json", tmp_path, tmp_path / "out.json", "--warmup", "11"
            ),
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        timeout=scaled(120),
        check=False,
    )
    assert (result.returncode, result.stdout) == (1, "")
    assert result.stderr == "control-run benchmark refused: warmup must be in [0, 10]\n"


def test_missing_output_directory_is_refused(
    campaign: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No working directory can be made beside an output in a missing directory."""
    output = tmp_path / "absent" / "benchmark.json"
    assert main(_arguments(campaign, tmp_path, output)) == 1
    error = capsys.readouterr().err
    assert error.startswith(
        f"control-run benchmark refused: [Errno 2] No such file or directory: '{output.parent}/"
    )
    assert error.endswith("'\n")


@pytest.mark.parametrize(("warmup", "passes"), [(10, 5), (0, 100)])
def test_largest_pass_counts_are_admitted(warmup: int, passes: int, tmp_path: Path) -> None:
    """The largest warm-up and measured pass counts pass validation up to the output check."""
    output = tmp_path / "benchmark.json"
    output.write_text("{}", encoding="utf-8")
    request = BenchmarkRequest(tmp_path, tmp_path, output, CPU, warmup, passes, "local")
    with pytest.raises(ValueError, match=r"^output already exists$"):
        validate(request)
