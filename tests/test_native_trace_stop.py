# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — kernel trace stop on a missed deadline

"""Stop a tracefs-style trace at a run's first miss or safe state, through the real programs.

The tracefs directory of each test is an ordinary directory with ``tracing_on``, ``trace_clock``
and ``trace_marker`` files, so the native run's writes can be read back exactly. The native API
corpus reaches every refusal of the trace stop.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Final

import pytest
from jsonschema import Draft202012Validator
from test_native_run import configuration, native_run

from conftest import REPOSITORY_ROOT
from loop_timing_witness.host_profile import scaled

__all__ = ["native_run"]

COVERAGE_DIRECTORY: Final = "WITNESS_POLICY_COVERAGE_DIRECTORY"
SCHEMA: Final = json.loads((REPOSITORY_ROOT / "native-run.schema.json").read_text(encoding="utf-8"))


def _tracefs(directory: Path, *, on: bytes = b"1\n", clock: bytes | None = None) -> Path:
    """Create a tracefs-style directory.

    Parameters
    ----------
    directory
        New directory.
    on
        Content of ``tracing_on``.
    clock
        Content of ``trace_clock``; the default selects ``mono``.

    Returns
    -------
    Path
        The directory, with an empty ``trace_marker``.
    """
    directory.mkdir()
    (directory / "tracing_on").write_bytes(on)
    (directory / "trace_clock").write_bytes(
        b"local global counter uptime perf [mono] mono_raw boot\n" if clock is None else clock
    )
    (directory / "trace_marker").write_bytes(b"")
    return directory


def _run(
    native_run: Path, tmp_path: Path, fault: str, *options: str
) -> subprocess.CompletedProcess[str]:
    """Run one native simulation with options after the positional arguments.

    Parameters
    ----------
    native_run
        Actual native simulation executable.
    tmp_path
        Run directory for the configuration and outputs.
    fault
        Injected RTL fault, or ``none``.
    *options
        Run options.

    Returns
    -------
    subprocess.CompletedProcess[str]
        The finished program.
    """
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", fault), encoding="utf-8")
    return subprocess.run(
        [
            str(native_run),
            str(config),
            str(tmp_path / "events.bin"),
            str(tmp_path / "raw.csv"),
            *options,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=scaled(60),
    )


@pytest.mark.parametrize(
    ("fault", "condition", "stop"),
    [
        ("none", "miss", None),
        ("drop", "miss", (1, False)),
        ("drop", "safe", None),
        ("freeze", "safe", (None, True)),
    ],
)
def test_trace_stops_at_the_first_matching_observation(
    native_run: Path,
    tmp_path: Path,
    fault: str,
    condition: str,
    stop: tuple[int | None, bool] | None,
) -> None:
    """A miss or safe-state condition writes one marker and stops tracing; otherwise nothing.

    Parameters
    ----------
    native_run
        Actual native simulation executable.
    tmp_path
        Run and tracefs directory.
    fault
        Injected RTL fault.
    condition
        Trace stop condition.
    stop
        ``None`` when the run must not stop tracing, otherwise the required miss count at the
        stop (``None`` for any positive count) and safe-state flag.
    """
    tracefs = _tracefs(tmp_path / "tracing")
    metadata = tmp_path / "metadata.json"
    result = _run(
        native_run,
        tmp_path,
        fault,
        "--metadata",
        str(metadata),
        "--trace-stop",
        condition,
        "--tracefs",
        str(tracefs),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    document = json.loads(metadata.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(SCHEMA).iter_errors(document)) == []
    record: dict[str, Any] = document["trace_stop"]
    assert record["condition"] == condition
    assert record["tracefs"] == str(tracefs)
    assert record["trace_clock"] == "mono"
    assert record["triggered"] is (stop is not None)
    marker = (tracefs / "trace_marker").read_text(encoding="ascii")
    if stop is not None:
        misses, safe = stop
        assert record["misses"] == misses or (misses is None and record["misses"] > 0)
        assert record["safe"] is safe
        assert record["monotonic_ns"] > 0
        assert marker == (
            f"loop-timing-witness trace stop: {condition} misses={record['misses']} "
            f"safe={int(safe)}\n"
        )
        assert (tracefs / "tracing_on").read_bytes() == b"0\n"
    else:
        assert (record["misses"], record["safe"], record["monotonic_ns"]) == (0, False, 0)
        assert marker == ""
        assert (tracefs / "tracing_on").read_bytes() == b"1\n"


@pytest.mark.parametrize(
    ("options", "error"),
    [
        (["--trace-stop", "miss"], "trace stop condition and tracefs must be supplied together"),
        (
            ["--tracefs", "/sys/kernel/tracing"],
            "trace stop condition and tracefs must be supplied together",
        ),
        (
            ["--trace-stop", "late", "--tracefs", "/sys/kernel/tracing"],
            "trace stop condition must be miss or safe",
        ),
        (
            ["--trace-stop", "miss", "--tracefs", "/sys/kernel/tracing"],
            "a trace stop requires native metadata",
        ),
        (
            ["--trace-stop", "miss", "--trace-stop", "safe"],
            "unknown or duplicate run option",
        ),
        (["--tracefs", "/a", "--tracefs", "/b"], "unknown or duplicate run option"),
    ],
)
def test_trace_stop_options_are_refused_before_any_output(
    native_run: Path, tmp_path: Path, options: list[str], error: str
) -> None:
    """Incomplete, unknown or metadata-free trace stops are refused before the run.

    Parameters
    ----------
    native_run
        Actual native simulation executable.
    tmp_path
        Run directory.
    options
        Trace stop options.
    error
        Required refusal.
    """
    result = _run(native_run, tmp_path, "none", *options)
    assert result.returncode == 1
    assert result.stderr.strip() == error
    assert not (tmp_path / "events.bin").exists()


@pytest.fixture(scope="module")
def trace_program() -> Path:
    """Build the native trace stop API corpus with strict warnings.

    When ``WITNESS_POLICY_COVERAGE_DIRECTORY`` names a directory, the corpus is built there
    unoptimised with GCC line and branch counters for the runtime coverage gate.

    Returns
    -------
    Path
        Native executable using the public header.
    """
    coverage = os.environ.get(COVERAGE_DIRECTORY)
    if coverage:
        directory = Path(coverage)
        flags = ["-O0", "--coverage", "-fprofile-abs-path"]
    else:
        directory = REPOSITORY_ROOT / "build/trace_stop_api"
        flags = ["-O2"]
    directory.mkdir(parents=True, exist_ok=True)
    program = directory / "trace_stop_api_test"
    result = subprocess.run(
        [
            "g++",
            "-std=c++17",
            *flags,
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wconversion",
            "-Wshadow",
            str(REPOSITORY_ROOT / "tests/native/trace_stop_api_test.cpp"),
            "-o",
            str(program),
        ],
        cwd=directory,
        capture_output=True,
        text=True,
        check=False,
        timeout=scaled(30),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return program


def _api(program: Path, *arguments: str) -> str:
    """Run the native API corpus once and return its standard output.

    Parameters
    ----------
    program
        Native trace stop API executable.
    *arguments
        Scenario and its arguments.

    Returns
    -------
    str
        The printed result or refusal.
    """
    result = subprocess.run(
        [str(program), *arguments], capture_output=True, text=True, check=False, timeout=scaled(5)
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""
    return result.stdout


def test_api_observes_once_and_records_the_stop(trace_program: Path, tmp_path: Path) -> None:
    """Only the first matching observation stops tracing; later ones change nothing.

    Parameters
    ----------
    trace_program
        Native trace stop API executable.
    tmp_path
        Tracefs directory.
    """
    tracefs = _tracefs(tmp_path / "tracing")
    output = _api(trace_program, "stop", str(tracefs), "safe", "2", "0", "3", "1", "4", "1")
    member = json.loads("{" + output.rstrip().removesuffix(",") + "}")["trace_stop"]
    assert list(Draft202012Validator(SCHEMA["properties"]["trace_stop"]).iter_errors(member)) == []
    assert (member["triggered"], member["misses"], member["safe"]) == (True, 3, True)
    assert (tracefs / "trace_marker").read_text(encoding="ascii") == (
        "loop-timing-witness trace stop: safe misses=3 safe=1\n"
    )


@pytest.mark.parametrize(
    ("setup", "error"),
    [
        ({"on": b"0\n"}, "kernel tracing is not on"),
        ({"clock": b"local global\n"}, "tracefs trace_clock names no selected clock"),
        ({"clock": b"local [global\n"}, "tracefs trace_clock names no selected clock"),
        ({"clock": b"[] local\n"}, "tracefs trace_clock names no selected clock"),
        ({"clock": b"[" + b"a" * 33 + b"]\n"}, "tracefs trace_clock names no selected clock"),
        ({"clock": b"[Mono]\n"}, "tracefs trace_clock names no selected clock"),
        ({"marker": None}, "cannot open the tracefs marker and switch"),
        ({"switch": 0o444}, "cannot open the tracefs marker and switch"),
        ({"clock": None}, "cannot open tracefs control: "),
        ({"on": b"1" * 512}, "cannot read tracefs control: "),
        ({"marker": "full"}, "cannot write tracefs marker (errno 28)"),
    ],
)
def test_api_refuses_unusable_tracefs(
    trace_program: Path, tmp_path: Path, setup: dict[str, Any], error: str
) -> None:
    """Inactive tracing, unreadable controls, a missing clock, marker or switch, or a failed write.

    Parameters
    ----------
    trace_program
        Native trace stop API executable.
    tmp_path
        Tracefs directory.
    setup
        Changes to the tracefs directory.
    error
        Required refusal prefix.
    """
    tracefs = _tracefs(tmp_path / "tracing", on=setup.get("on", b"1\n"), clock=setup.get("clock"))
    if "clock" in setup and setup["clock"] is None:
        (tracefs / "trace_clock").unlink()
    if "marker" in setup:
        (tracefs / "trace_marker").unlink()
        if setup["marker"] == "full":
            (tracefs / "trace_marker").symlink_to("/dev/full")
    if "switch" in setup:
        (tracefs / "tracing_on").chmod(setup["switch"])
    output = _api(trace_program, "stop", str(tracefs), "miss", "1", "0")
    assert output.startswith(f"refused: {error}")


@pytest.mark.parametrize(
    ("text", "verdict"),
    [
        ("/sys/kernel/tracing", "plain"),
        ("", "refused"),
        ("relative/tracing", "refused"),
        ("/" + "a" * 256, "refused"),
        ("/trace\ning", "refused"),
        ('/tr"ace', "refused"),
        ("/trace[0]", "refused"),
        ("/trace\\ing", "refused"),
        ("/tr~ace ok", "plain"),
        ("/trace\x7f", "refused"),
    ],
)
def test_api_plain_paths(trace_program: Path, text: str, verdict: str) -> None:
    """Only absolute printable paths without quotes, backslashes, brackets or carets are plain.

    Parameters
    ----------
    trace_program
        Native trace stop API executable.
    text
        Candidate tracefs path.
    verdict
        ``plain`` or ``refused``.
    """
    assert _api(trace_program, "path", text) == verdict + "\n"


def test_api_other_refusals(trace_program: Path, tmp_path: Path) -> None:
    """A wrong condition, a non-plain path, a directory read, a clock and a failed write.

    Parameters
    ----------
    trace_program
        Native trace stop API executable.
    tmp_path
        Tracefs directory.
    """
    tracefs = _tracefs(tmp_path / "tracing")
    assert _api(trace_program, "stop", str(tracefs), "late") == (
        "refused: trace stop condition must be miss or safe\n"
    )
    assert _api(trace_program, "stop", "relative", "miss") == (
        "refused: tracefs must be an absolute plain ASCII path\n"
    )
    assert _api(trace_program, "read", str(tracefs)).startswith("refused: cannot read tracefs")
    clock = tracefs / "trace_clock"
    assert _api(trace_program, "read", str(clock)) == f"{len(clock.read_bytes())}\n"
    assert _api(trace_program, "clock", "x86-tsc [mono_raw]") == "mono_raw\n"
    assert _api(trace_program, "clock", "local [x86-tsc]") == "x86-tsc\n"
    for name in ("[a{]", "[a.b]"):
        assert _api(trace_program, "clock", name) == (
            "refused: tracefs trace_clock names no selected clock\n"
        )
    assert _api(trace_program, "full") == "refused: cannot write tracefs tracing_on (errno 28)\n"
