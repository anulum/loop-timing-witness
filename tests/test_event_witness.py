# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — buffered witness simulation tests

"""Check timestamp capture, counted overflow and recovery through the drain stream."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

MakeRtlRun = Callable[[], tuple[Path, dict[str, Any]]]
RunTool = Callable[..., subprocess.CompletedProcess[str]]

RunRtl = Callable[[str, dict[str, int], list[str]], subprocess.CompletedProcess[str]]


@pytest.mark.parametrize(("overflow", "counter_bits"), [(0, 32), (1, 32), (1, 3), (1, 1)])
def test_witness_known_period_overflow_and_reset(
    overflow: int,
    counter_bits: int,
    run_rtl: RunRtl,
    tmp_path: Path,
) -> None:
    """Verify original timestamps, preserved records, saturating drops and reset.

    Parameters
    ----------
    overflow
        Zero for known periods; one for a full-buffer drop and recovery run.
    counter_bits
        Drop counter width, including saturation at one and three bits.
    run_rtl
        Real compiler and simulator runner.
    tmp_path
        Binary drain output directory.
    """
    output = tmp_path / "events.bin"
    result = run_rtl(
        "event_witness_tb",
        {
            "OVERFLOW_RUN": overflow,
            "OVERFLOW_COUNTER_BITS": counter_bits,
        },
        [f"+EVENT_FILE={output}"],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RESET_PASS" in result.stdout
    assert "WITNESS_PASS accepted=12" in result.stdout
    assert f"dropped={17 if overflow else 0}" in result.stdout
    assert len(output.read_bytes()) == 12 * 16


@pytest.mark.parametrize("overflow", [0, 1])
def test_buffered_stream_reaches_host_reports(
    overflow: int,
    run_rtl: RunRtl,
    make_rtl_run: MakeRtlRun,
    run_tool: RunTool,
    tmp_path: Path,
) -> None:
    """Analyse real drained records and refuse overflow as valid evidence.

    Parameters
    ----------
    overflow
        Select the known-period or overflow simulation.
    run_rtl
        Real buffered-witness simulation runner.
    make_rtl_run
        Factory providing a hash-bound simulation run contract.
    run_tool
        Public host analysis command runner.
    tmp_path
        Compiled simulation and report directory.
    """
    run, manifest = make_rtl_run()
    result = run_rtl(
        "event_witness_tb", {"OVERFLOW_RUN": overflow}, [f"+EVENT_FILE={run / 'events.bin'}"]
    )
    assert result.returncode == 0, result.stdout + result.stderr
    sources = [
        "rtl/event_codes_pkg.sv",
        "rtl/clock_reset_release.sv",
        "rtl/event_record_capture.sv",
        "rtl/event_record_fifo.sv",
        "rtl/event_witness.sv",
        "tests/rtl/event_witness_tb.sv",
    ]
    repository = Path(__file__).resolve().parents[1]
    for relative in sources:
        destination = run / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repository / relative, destination)
    shutil.copyfile(tmp_path / "event_witness_tb.vvp", run / "event_witness_tb.vvp")
    references = [
        {"path": relative, "sha256": hashlib.sha256((run / relative).read_bytes()).hexdigest()}
        for relative in [*sources, "event_witness_tb.vvp"]
    ]
    manifest["source"]["files"] = references
    manifest["fault_schedule"] = []
    manifest["files"]["events"]["sha256"] = hashlib.sha256(
        (run / "events.bin").read_bytes()
    ).hexdigest()
    if overflow:
        assert "dropped=17 overflow_count=17" in result.stdout
        manifest["cycle_count"] = 29
        manifest["instrument"]["fifo_overflow_count"] = 17
        manifest["files"]["tracking"] = None
        manifest["files"]["power"] = None
    else:
        assert "dropped=0 overflow_count=0" in result.stdout
    (run / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    output = tmp_path / "buffered-report"
    analysis = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert analysis.returncode == 0, analysis.stderr
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["evidence_status"] == "simulation_only"
    assert report["events"]["event_count"] == 12
    assert report["fifo_overflow_count"] == (17 if overflow else 0)
    assert report["valid"] is (not overflow)
    if overflow:
        assert "event FIFO overflow" in report["invalid_reasons"]
    else:
        assert report["events"]["intervals"]["loop_latency"]["maximum_ticks"] == 20
        assert report["events"]["control"]["deadline_misses"] == 0
        raw = (run / "events.bin").read_bytes()
        deadlines = [
            int.from_bytes(raw[offset + 8 : offset + 16], "little")
            for offset in range(0, len(raw), 16)
            if raw[offset] == 4
        ]
        assert deadlines == [5000, 10000, 15000]


@pytest.mark.parametrize(
    ("parameter", "value", "finding"),
    [
        ("ADDRESS_BITS", 15, "ADDRESS_BITS must be in [1,14]"),
        ("OVERFLOW_COUNTER_BITS", 0, "OVERFLOW_COUNTER_BITS must be in [1,32]"),
        ("OVERFLOW_COUNTER_BITS", 33, "OVERFLOW_COUNTER_BITS must be in [1,32]"),
    ],
)
def test_witness_refuses_unsupported_parameters(
    parameter: str,
    value: int,
    finding: str,
    run_rtl: RunRtl,
    tmp_path: Path,
) -> None:
    """Fail elaborated simulations before accepting unsupported hardware widths.

    Parameters
    ----------
    parameter
        Public RTL parameter to override.
    value
        Unsupported integer value.
    finding
        Required diagnostic.
    run_rtl
        Real compiler and simulator runner.
    tmp_path
        Test output directory.
    """
    result = run_rtl(
        "event_witness_tb", {parameter: value}, [f"+EVENT_FILE={tmp_path / 'events.bin'}"]
    )
    assert result.returncode != 0
    assert finding in result.stdout


def test_zero_address_width_is_rejected_at_elaboration(run_rtl: RunRtl) -> None:
    """Reject a FIFO with no address bits before any source record is accepted.

    Parameters
    ----------
    run_rtl
        Real compiler and simulator runner.
    """
    with pytest.raises(subprocess.CalledProcessError) as error:
        run_rtl("event_witness_tb", {"ADDRESS_BITS": 0}, [])
    assert "negative" in error.value.stderr.lower()
