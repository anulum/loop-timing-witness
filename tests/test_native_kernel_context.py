# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — Linux real-time context of a native run

"""Read the Linux real-time context through the native API from real kernel and test files."""

from __future__ import annotations

import json
import os
import struct
import subprocess
from pathlib import Path
from typing import Any, Final

import pytest
from jsonschema import Draft202012Validator

from conftest import REPOSITORY_ROOT
from loop_timing_witness.host_profile import scaled

COVERAGE_DIRECTORY: Final = "WITNESS_POLICY_COVERAGE_DIRECTORY"
SOURCES: Final = ("realtime", "isolated", "nohz_full", "cmdline", "status", "dma")
BOOT_KEYS: Final = frozenset(
    {
        "isolcpus",
        "nohz",
        "nohz_full",
        "rcu_nocbs",
        "rcu_nocb_poll",
        "irqaffinity",
        "kthread_cpus",
        "preempt",
        "threadirqs",
        "skew_tick",
        "idle",
        "cpuidle.off",
        "processor.max_cstate",
        "intel_idle.max_cstate",
        "nosoftlockup",
        "nowatchdog",
        "nmi_watchdog",
        "clocksource",
        "tsc",
        "mitigations",
    }
)
COMMAND_LINE: Final = (
    "BOOT_IMAGE=/vmlinuz root=UUID=1 ro quiet nohz_full=2-3  isolcpus=domain,2-3 "
    'nohz=on rcu_nocbs=2-3 threadirqs note="a b" idle'
)
VALID: Final[dict[str, bytes | None]] = {
    "realtime": None,
    "isolated": b"0-3,8\n",
    "nohz_full": b"(null)\n",
    "cmdline": COMMAND_LINE.encode() + b"\n",
    "status": b"Name:\tx\nVmLck:\t      12 kB\nVmPin:\t0 kB\n",
    "dma": struct.pack("=i", 2_000_000_000),
}
DENIED: Final = b"denied"


def _member(output: str) -> dict[str, Any]:
    """Decode the JSON member the native API prints.

    Parameters
    ----------
    output
        ``  "host_kernel": {...},`` and a newline.

    Returns
    -------
    dict[str, Any]
        The member's value, checked against the native run schema.
    """
    document = json.loads("{" + output.rstrip().removesuffix(",") + "}")
    schema = json.loads((REPOSITORY_ROOT / "native-run.schema.json").read_text(encoding="utf-8"))
    member = schema["properties"]["host_kernel"]
    assert list(Draft202012Validator(member).iter_errors(document["host_kernel"])) == []
    assert set(document) == {"host_kernel"}
    value: dict[str, Any] = document["host_kernel"]
    return value


@pytest.fixture(scope="module")
def kernel_program() -> Path:
    """Build the native kernel context API corpus with strict warnings.

    When ``WITNESS_POLICY_COVERAGE_DIRECTORY`` names a directory, the corpus is built there
    unoptimised with GCC line and branch counters for the runtime coverage gate.

    Returns
    -------
    Path
        Native executable reading the context through the public header.
    """
    coverage = os.environ.get(COVERAGE_DIRECTORY)
    if coverage:
        directory = Path(coverage)
        flags = ["-O0", "--coverage", "-fprofile-abs-path"]
    else:
        directory = REPOSITORY_ROOT / "build/kernel_context_api"
        flags = ["-O2"]
    directory.mkdir(parents=True, exist_ok=True)
    program = directory / "kernel_context_api_test"
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
            str(REPOSITORY_ROOT / "tests/native/kernel_context_api_test.cpp"),
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


def _run(program: Path, *arguments: str) -> str:
    """Run the native API corpus once and return its standard output.

    Parameters
    ----------
    program
        Native kernel context API executable.
    *arguments
        Scenario and its paths.

    Returns
    -------
    str
        The printed member or refusal.
    """
    result = subprocess.run(
        [str(program), *arguments],
        capture_output=True,
        text=True,
        check=False,
        timeout=scaled(5),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""
    return result.stdout


def _files(directory: Path, changes: dict[str, bytes | None]) -> list[str]:
    """Write the six source files of one scenario.

    Parameters
    ----------
    directory
        Empty directory of the scenario.
    changes
        Contents that replace the valid ones; ``None`` leaves a file absent and ``DENIED``
        creates an unreadable one.

    Returns
    -------
    list[str]
        The six paths in the order of ``KernelContextSources``.
    """
    paths = []
    for name in SOURCES:
        path = directory / name
        content = changes.get(name, VALID[name])
        if content is not None:
            path.write_bytes(b"" if content == DENIED else content)
        if content == DENIED:
            path.chmod(0)
        paths.append(str(path))
    return paths


def _expected_host() -> dict[str, Any]:
    """Read the running kernel's context independently of the native code.

    Returns
    -------
    dict[str, Any]
        Every recorded field except the child's own locked memory.
    """
    realtime = Path("/sys/kernel/realtime")
    nohz = Path("/sys/devices/system/cpu/nohz_full")
    nohz_text = nohz.read_text(encoding="ascii").lstrip(" ") if nohz.exists() else None
    try:
        with Path("/dev/cpu_dma_latency").open("rb") as device:
            dma: int | None = struct.unpack("=i", device.read())[0]
    except PermissionError, FileNotFoundError:
        dma = None
    tokens = Path("/proc/cmdline").read_text(encoding="ascii").split()
    return {
        "release": os.uname().release,
        "version": os.uname().version,
        "realtime": realtime.exists() and realtime.read_text(encoding="ascii") == "1\n",
        "isolated_cpus": Path("/sys/devices/system/cpu/isolated")
        .read_text(encoding="ascii")
        .removesuffix("\n"),
        "nohz_full_cpus": None
        if nohz_text is None
        else ("" if nohz_text == "(null)\n" else nohz_text.removesuffix("\n")),
        "boot_parameters": [token for token in tokens if token.split("=")[0] in BOOT_KEYS],
        "cpu_dma_latency_us": dma,
    }


def test_the_running_kernel_is_recorded_as_read_independently(kernel_program: Path) -> None:
    """The native reader gives the running kernel's own context, valid under the schema."""
    member = _member(_run(kernel_program, "host"))
    locked = member.pop("locked_memory_kib")
    assert isinstance(locked, int)
    assert locked >= 0
    assert member == _expected_host()


def test_valid_files_give_every_field(kernel_program: Path, tmp_path: Path) -> None:
    """Valid files give each field, recorded boot parameters in boot order."""
    member = _member(_run(kernel_program, "files", *_files(tmp_path, {})))
    assert member == {
        "release": os.uname().release,
        "version": os.uname().version,
        "realtime": False,
        "isolated_cpus": "0-3,8",
        "nohz_full_cpus": "",
        "boot_parameters": [
            "nohz_full=2-3",
            "isolcpus=domain,2-3",
            "nohz=on",
            "rcu_nocbs=2-3",
            "threadirqs",
            "idle",
        ],
        "locked_memory_kib": 12,
        "cpu_dma_latency_us": 2_000_000_000,
    }


@pytest.mark.parametrize(
    ("changes", "field", "value"),
    [
        ({"realtime": b"1\n"}, "realtime", True),
        ({"isolated": b"\n"}, "isolated_cpus", ""),
        ({"isolated": b"7"}, "isolated_cpus", "7"),
        ({"nohz_full": None}, "nohz_full_cpus", None),
        ({"nohz_full": b"2-3\n"}, "nohz_full_cpus", "2-3"),
        ({"nohz_full": b"\n"}, "nohz_full_cpus", ""),
        ({"nohz_full": b""}, "nohz_full_cpus", ""),
        ({"nohz_full": b" " * 18 + b"(null)\n"}, "nohz_full_cpus", ""),
        ({"nohz_full": b"  2-3\n"}, "nohz_full_cpus", "2-3"),
        ({"cmdline": b"isolcpus=1"}, "boot_parameters", ["isolcpus=1"]),
        ({"cmdline": b"\n"}, "boot_parameters", []),
        ({"status": b"Name:\tx\nVmLck:\t0 kB\n"}, "locked_memory_kib", 0),
        ({"status": b"Name:\tx\nVmLck: " + b"9" * 15 + b" kB\n"}, "locked_memory_kib", 10**15 - 1),
        ({"dma": None}, "cpu_dma_latency_us", None),
        ({"dma": DENIED}, "cpu_dma_latency_us", None),
        ({"dma": struct.pack("=i", 0)}, "cpu_dma_latency_us", 0),
    ],
)
def test_each_source_gives_its_field(
    kernel_program: Path,
    tmp_path: Path,
    changes: dict[str, bytes | None],
    field: str,
    value: object,
) -> None:
    """Each source file decides its own field: present, empty, absent or unreadable.

    Parameters
    ----------
    kernel_program
        Native kernel context API executable.
    tmp_path
        Scenario directory.
    changes
        Replaced source contents.
    field
        Recorded field.
    value
        Its expected value.
    """
    if os.geteuid() == 0 and DENIED in changes.values():
        pytest.skip("root reads a file without permissions")
    assert _member(_run(kernel_program, "files", *_files(tmp_path, changes)))[field] == value


@pytest.mark.parametrize(
    ("changes", "refusal"),
    [
        ({"realtime": b"0\n"}, "unsupported Linux realtime flag"),
        ({"realtime": DENIED}, "unsupported Linux realtime flag"),
        ({"isolated": None}, "cannot read {isolated}"),
        ({"isolated": DENIED}, "cannot read {isolated}"),
        ({"isolated": b"1,\n"}, "malformed Linux isolated CPU list"),
        ({"isolated": b",1\n"}, "malformed Linux isolated CPU list"),
        ({"isolated": b"1-2-3\n"}, "malformed Linux isolated CPU list"),
        ({"isolated": b"1-\n"}, "malformed Linux isolated CPU list"),
        ({"isolated": b"a\n"}, "malformed Linux isolated CPU list"),
        ({"isolated": b"1 2\n"}, "malformed Linux isolated CPU list"),
        ({"nohz_full": b"x\n"}, "malformed Linux full dynamic tick CPU list"),
        ({"nohz_full": DENIED}, "cannot read Linux full dynamic tick CPUs"),
        ({"cmdline": None}, "cannot read {cmdline}"),
        ({"cmdline": b'nohz_full="2"\n'}, "unsupported Linux boot parameter text"),
        ({"cmdline": b"isolcpus=" + b"1" * 248}, "unsupported Linux boot parameter text"),
        ({"cmdline": b"isolcpus=\x01"}, "unsupported Linux boot parameter text"),
        ({"cmdline": b"isolcpus=[1]"}, "unsupported Linux boot parameter text"),
        ({"cmdline": b"isolcpus=1\x7f"}, "unsupported Linux boot parameter text"),
        ({"cmdline": b"x" * 8192}, "cannot read the whole of {cmdline}"),
        ({"status": None}, "cannot read {status}"),
        ({"status": b"Name:\tx\n"}, "cannot read locked memory of this process"),
        ({"status": b"Name:\tx\nVmLck:\t kB\n"}, "cannot read locked memory of this process"),
        (
            {"status": b"Name:\tx\nVmLck:" + b"9" * 16 + b" kB\n"},
            "cannot read locked memory of this process",
        ),
        ({"status": b"Name:\tx\nVmLck:\t5 MB\n"}, "cannot read locked memory of this process"),
        ({"status": b"Name:\tx\nVmLck:\t5"}, "cannot read locked memory of this process"),
        ({"status": b"Name:\tx\nVmLck:\t5kB\n"}, "cannot read locked memory of this process"),
        ({"status": b"Name:\tx\nVmLck:\t"}, "cannot read locked memory of this process"),
        ({"dma": b"\x00\x00\x00"}, "unsupported Linux CPU latency request value"),
        ({"dma": struct.pack("=i", -1)}, "unsupported Linux CPU latency request value"),
    ],
)
def test_malformed_or_unreadable_sources_are_refused(
    kernel_program: Path,
    tmp_path: Path,
    changes: dict[str, bytes | None],
    refusal: str,
) -> None:
    """A malformed or unreadable source refuses the run with its authored message.

    Parameters
    ----------
    kernel_program
        Native kernel context API executable.
    tmp_path
        Scenario directory.
    changes
        Replaced source contents.
    refusal
        Expected refusal, with ``{name}`` standing for that source's path.
    """
    if os.geteuid() == 0 and DENIED in changes.values():
        pytest.skip("root reads a file without permissions")
    paths = _files(tmp_path, changes)
    expected = refusal.format(**dict(zip(SOURCES, paths, strict=True)))
    assert _run(kernel_program, "files", *paths) == f"refused: {expected}\n"


def test_unopenable_and_unreadable_paths_are_refused(kernel_program: Path, tmp_path: Path) -> None:
    """A path that cannot be opened at all, or a directory that cannot be read, is refused."""
    paths = _files(tmp_path, {})
    not_a_directory = paths[1] + "/below"
    assert (
        _run(kernel_program, "files", paths[0], not_a_directory, *paths[2:])
        == f"refused: cannot open {not_a_directory}\n"
    )
    assert (
        _run(kernel_program, "files", paths[0], str(tmp_path), *paths[2:])
        == f"refused: cannot read the whole of {tmp_path}\n"
    )


@pytest.mark.parametrize(
    ("scenario", "refusal"),
    [
        ("uname_denied", "cannot read Linux kernel identity"),
        ("empty_text", "unsupported Linux kernel release text"),
    ],
)
def test_identity_failures_are_refused(kernel_program: Path, scenario: str, refusal: str) -> None:
    """A kernel that refuses uname, or an empty identity text, refuses the run.

    Parameters
    ----------
    kernel_program
        Native kernel context API executable.
    scenario
        ``uname_denied`` installs a seccomp answer in the child; ``empty_text`` checks the text
        rule directly.
    refusal
        Expected refusal.
    """
    assert _run(kernel_program, scenario) == f"refused: {refusal}\n"


def test_unknown_scenarios_fail(kernel_program: Path) -> None:
    """The corpus refuses an unknown scenario or a wrong argument count."""
    for arguments in ([], ["host", "extra"], ["files"], ["unknown"]):
        result = subprocess.run(
            [str(kernel_program), *arguments],
            capture_output=True,
            check=False,
            timeout=scaled(5),
        )
        assert result.returncode == 1
