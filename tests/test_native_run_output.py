# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — native raw output custody and actual write failures

"""Exercise exclusive evidence files and summary failure through the real run CLI."""

from __future__ import annotations

import os
import resource
import subprocess
from pathlib import Path

import pytest
from test_native_run import configuration, native_run

__all__ = ["native_run"]


OUTPUT_LIMIT_COMMAND = (
    "env",
    "--ignore-signal=XFSZ",
    "prlimit",
)


def limited_profile_environment(directory: Path) -> dict[str, str]:
    """Keep size-limited child gcov files separate from the normal measurement data.

    Parameters
    ----------
    directory
        Exclusive child artifact allocation.

    Returns
    -------
    dict of str to str
        Actual inherited environment with profiling output relocated.
    """
    environment = os.environ.copy()
    environment["GCOV_PREFIX"] = str(directory / "limited_profile")
    return environment


def test_summary_write_failure(native_run: Path, tmp_path: Path) -> None:
    """Report a real Linux write failure while preserving completed capture evidence.

    Parameters
    ----------
    native_run
        Actual native run controller with production plant/AXI.
    tmp_path
        Managed configuration and exclusive raw output destinations.
    """
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none"), encoding="utf-8")
    events, tracking = tmp_path / "events.bin", tmp_path / "tracking.csv"
    with Path("/dev/full").open("w") as sink:
        result = subprocess.run(
            [str(native_run), str(config), str(events), str(tracking)],
            stdout=sink,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=10,
        )
    assert result.returncode == 1
    assert "cannot write run summary" in result.stderr
    assert events.stat().st_size == 128 * 16
    assert len(tracking.read_text().splitlines()) == 33


def test_existing_tracking_preserved(native_run: Path, tmp_path: Path) -> None:
    """Retain a preexisting trace and the new empty failed-run file without reset/start.

    Parameters
    ----------
    native_run
        Production native run executable.
    tmp_path
        Exact managed destinations, including a preexisting trace.
    """
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none"), encoding="utf-8")
    events, tracking = tmp_path / "events.bin", tmp_path / "tracking.csv"
    tracking.write_bytes(b"previous-evidence\n")
    result = subprocess.run(
        [str(native_run), str(config), str(events), str(tracking)],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    assert result.returncode == 1
    assert "exclusive tracking" in result.stderr
    assert result.stdout == ""
    assert tracking.read_bytes() == b"previous-evidence\n"
    assert events.read_bytes() == b""


@pytest.mark.parametrize("maximum", [0, 32])
def test_header_write_refusal(native_run: Path, tmp_path: Path, maximum: int) -> None:
    """Refuse genuine trace-header write failure before any actual RTL run events.

    Parameters
    ----------
    native_run
        Actual production run executable against the selected plant.
    tmp_path
        Exclusive configuration and output files.
    maximum
        Real regular-file limit smaller than the header.
    """
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none"), encoding="utf-8")
    events, raw = tmp_path / "events.bin", tmp_path / "raw.csv"
    inherited = resource.getrlimit(resource.RLIMIT_FSIZE)
    result = subprocess.run(
        [
            *OUTPUT_LIMIT_COMMAND,
            f"--fsize={maximum}:{maximum}",
            "--",
            str(native_run),
            str(config),
            str(events),
            str(raw),
        ],
        env=limited_profile_environment(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 1
    assert "cannot write tracking header" in result.stderr
    assert result.stdout == ""
    assert events.read_bytes() == b""
    assert raw.stat().st_size == maximum
    assert resource.getrlimit(resource.RLIMIT_FSIZE) == inherited


def test_usage_refusal(native_run: Path) -> None:
    """Reject missing arguments through the actual native run CLI.

    Parameters
    ----------
    native_run
        Actual native entry point.
    """
    result = subprocess.run(
        [str(native_run)], capture_output=True, text=True, check=False, timeout=5
    )
    assert result.returncode == 1
    assert "usage: run_simulation" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize(
    ("fault", "error"), [("overload", "tracking sample"), ("freeze", "event record")]
)
def test_runtime_write_refusal(native_run: Path, tmp_path: Path, fault: str, error: str) -> None:
    """Stop on actual buffered output failure after a successful header flush.

    Parameters
    ----------
    native_run
        Actual production run executable.
    tmp_path
        Exclusive input and partial output allocation.
    fault
        Freeze retains few samples; real overload work with zero modeled delay fills the trace.
    error
        Expected native output operation that detects the real size limit.
    """
    config = tmp_path / "run.conf"
    text = configuration("pid", fault).replace("pid 32", "pid 256")
    if fault == "overload":
        text = text.replace("overload 0 3", "overload 0 256").replace("1000 1100000", "1000 0")
    config.write_text(text, encoding="utf-8")
    events, raw = tmp_path / "events.bin", tmp_path / "raw.csv"
    result = subprocess.run(
        [
            *OUTPUT_LIMIT_COMMAND,
            "--fsize=512:512",
            "--",
            str(native_run),
            str(config),
            str(events),
            str(raw),
        ],
        env=limited_profile_environment(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 1
    assert f"cannot write {error}" in result.stderr
    assert result.stdout == ""
    assert raw.read_bytes().startswith(b"cycle,reference_raw,")
    assert 0 < events.stat().st_size <= 512
    assert 0 < raw.stat().st_size <= 512


def test_close_write_refusal(native_run: Path, tmp_path: Path) -> None:
    """Refuse a real final flush failure after both output buffers fit the complete run.

    Parameters
    ----------
    native_run
        Actual production run executable.
    tmp_path
        Exclusive configuration and partial output allocation.
    """
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none"), encoding="utf-8")
    events, raw = tmp_path / "events.bin", tmp_path / "raw.csv"
    result = subprocess.run(
        [
            *OUTPUT_LIMIT_COMMAND,
            "--fsize=512:512",
            "--",
            str(native_run),
            str(config),
            str(events),
            str(raw),
        ],
        env=limited_profile_environment(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 1
    assert "cannot finish run output" in result.stderr
    assert events.stat().st_size == 512
    assert raw.stat().st_size == 512
    assert result.stdout == ""


def test_compiled_period_refusal_retains_only_header(native_run: Path, tmp_path: Path) -> None:
    """Refuse a valid contract with a mismatched compiled period before run START.

    Parameters
    ----------
    native_run
        Production run executable linked to the actual compiled RTL schedule.
    tmp_path
        Exclusive configuration and output allocation.
    """
    config = tmp_path / "run.conf"
    config.write_text(
        configuration("pid", "none").replace("pid 32 32768", "pid 32 32769"),
        encoding="utf-8",
    )
    events, raw, metadata = (tmp_path / name for name in ("events.bin", "raw.csv", "metadata.json"))
    result = subprocess.run(
        [str(native_run), str(config), str(events), str(raw), "--metadata", str(metadata)],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    assert result.returncode == 1
    assert result.stderr.strip() == "compiled register ABI, Q format or period mismatch"
    assert result.stdout == ""
    assert events.read_bytes() == b""
    header = raw.read_text().splitlines()
    assert len(header) == 1
    assert header[0].startswith("cycle,reference_raw,")
    assert not metadata.exists()


@pytest.mark.parametrize(
    ("maximum", "finding"), [(32, "write tracking header"), (512, "finish run output")]
)
def test_output_limit_literal_paths(
    native_run: Path, tmp_path: Path, maximum: int, finding: str
) -> None:
    """Forward literal paths through real child limits without interpreting path contents.

    Parameters
    ----------
    native_run
        Actual production native run executable.
    tmp_path
        Exclusive allocation for literal paths and failed capture files.
    maximum
        Actual kernel file-size limit in bytes.
    finding
        Required production write refusal at the selected limit.
    """
    config = tmp_path / "run configuration;literal.conf"
    config.write_text(configuration("pid", "none"), encoding="utf-8")
    events = tmp_path / "events $(touch executed).bin"
    raw = tmp_path / "tracking data.csv"
    inherited = resource.getrlimit(resource.RLIMIT_FSIZE)
    result = subprocess.run(
        [
            *OUTPUT_LIMIT_COMMAND,
            f"--fsize={maximum}:{maximum}",
            "--",
            str(native_run),
            str(config),
            str(events),
            str(raw),
        ],
        cwd=tmp_path,
        env=limited_profile_environment(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 1
    assert f"cannot {finding}" in result.stderr
    assert result.stdout == ""
    assert raw.stat().st_size == maximum
    assert events.stat().st_size <= maximum
    assert not (tmp_path / "executed").exists()
    assert resource.getrlimit(resource.RLIMIT_FSIZE) == inherited
