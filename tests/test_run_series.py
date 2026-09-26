# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — tracking and power series tests

"""Validate time-aligned CSV series through the host analysis command."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

MakeRtlRun = Callable[[], tuple[Path, dict[str, Any]]]
RunTool = Callable[..., subprocess.CompletedProcess[str]]


def _bad_tracking(variant: str, content: bytes) -> bytes:
    """Change one tracking CSV property used by a public CLI refusal test.

    Parameters
    ----------
    variant
        Named corruption.
    content
        Valid simulation tracking CSV.

    Returns
    -------
    bytes
        Corrupted CSV bytes.
    """
    formats = {
        "tracking_utf8": b"\xff",
        "tracking_empty": b"cycle,reference,output\n",
        "tracking_ragged": b"cycle,reference,output\n0,1\n",
        "tracking_csv_quote": b'cycle,reference,output\n"unterminated,1,0\n',
    }
    if variant in formats:
        return formats[variant]
    replacements = {
        "tracking_header": (b"cycle,reference,output", b"cycle,output,reference"),
        "tracking_cycle_text": (b"0,1,0.9", b"-1,1,0.9"),
        "tracking_cycle_duplicate": (b"1,2,1.8", b"0,2,1.8"),
        "tracking_cycle_outside": (b"1,2,1.8", b"3,2,1.8"),
        "tracking_cycle_missing": (b"1,2,1.8\n", b""),
        "tracking_decimal": (b"1,0.9", b"abc,0.9"),
        "tracking_infinite": (b"1,0.9", b"Infinity,0.9"),
    }
    old, new = replacements[variant]
    return content.replace(old, new)


def _bad_power(variant: str, content: bytes) -> bytes:
    """Change one cumulative-energy CSV property used by a CLI refusal test.

    Parameters
    ----------
    variant
        Named corruption.
    content
        Valid simulation power CSV.

    Returns
    -------
    bytes
        Corrupted CSV bytes.
    """
    if variant == "power_single_sample":
        return b"\n".join(content.split(b"\n")[:5]) + b"\n"
    replacements = {
        "power_unknown_rail": (b"0,VDD,", b"0,UNKNOWN,"),
        "power_duplicate_rail": (b"0,VDD25,", b"0,VDD,"),
        "power_negative": (b"0,VDD,1,0.1,0", b"0,VDD,-1,0.1,0"),
        "power_incomplete": (b"0,VDDA,1,0.1,0\n", b""),
        "power_regression": (b"0,VDD,1,0.1,0", b"0,VDD,1,0.1,1"),
        "power_uncovered": (b"15021,", b"10000,"),
    }
    old, new = replacements[variant]
    return content.replace(old, new, 1 if variant != "power_uncovered" else -1)


@pytest.mark.parametrize(
    ("variant", "finding"),
    [
        ("tracking_utf8", "not UTF-8"),
        ("tracking_header", "CSV header must be"),
        ("tracking_empty", "CSV has no data"),
        ("tracking_ragged", "incomplete row"),
        ("tracking_csv_quote", "invalid CSV"),
        ("tracking_cycle_text", "nonnegative decimal integer"),
        ("tracking_cycle_duplicate", "duplicated or outside"),
        ("tracking_cycle_outside", "duplicated or outside"),
        ("tracking_cycle_missing", "lacks an analysed cycle"),
        ("tracking_decimal", "not a decimal"),
        ("tracking_infinite", "must be finite"),
        ("power_unknown_rail", "unknown or duplicated"),
        ("power_duplicate_rail", "unknown or duplicated"),
        ("power_negative", "cannot be negative"),
        ("power_incomplete", "complete four-rail samples"),
        ("power_single_sample", "complete four-rail samples"),
        ("power_regression", "cumulative energy decreases"),
        ("power_uncovered", "do not cover every analysed cycle"),
    ],
)
def test_bad_series_is_refused(
    variant: str,
    finding: str,
    make_rtl_run: MakeRtlRun,
    run_tool: RunTool,
    tmp_path: Path,
) -> None:
    """Digest-correct CSV still needs complete physical and cycle structure.

    Parameters
    ----------
    variant
        Corruption of a simulation CSV input.
    finding
        Expected public refusal.
    make_rtl_run
        Icarus Verilog event producer.
    run_tool
        Host command runner.
    tmp_path
        New report path.
    """
    run, manifest = make_rtl_run()
    name = "tracking" if variant.startswith("tracking") else "power"
    path = run / f"{name}.csv"
    content = path.read_bytes()
    content = (
        _bad_tracking(variant, content) if name == "tracking" else _bad_power(variant, content)
    )
    path.write_bytes(content)
    manifest["files"][name]["sha256"] = hashlib.sha256(content).hexdigest()
    (run / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    output = tmp_path / "report"
    result = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert result.returncode == 1
    assert finding in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("missing", ["tracking", "power"])
def test_missing_simulation_series_is_reported_as_incomplete(
    missing: str, make_rtl_run: MakeRtlRun, run_tool: RunTool, tmp_path: Path
) -> None:
    """A simulation report can retain event evidence without inventing a metric.

    Parameters
    ----------
    missing
        Auxiliary series deliberately not supplied.
    make_rtl_run
        Icarus Verilog event producer.
    run_tool
        Host command runner.
    tmp_path
        New report path.
    """
    run, manifest = make_rtl_run()
    manifest["files"][missing] = None
    (run / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    output = tmp_path / "report"
    result = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert result.returncode == 0, result.stderr
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["valid"] is False
    metric = "tracking_error" if missing == "tracking" else "energy"
    assert report[metric]["status"] == "unavailable"
    assert (output / "energy_per_cycle.svg").is_file() is (missing == "tracking")


@pytest.mark.parametrize("alignment", ["overlap", "aligned"])
def test_warmup_energy_requires_post_warmup_window(
    alignment: str, make_rtl_run: MakeRtlRun, run_tool: RunTool, tmp_path: Path
) -> None:
    """Warm-up energy cannot be attributed to analysed control cycles.

    Parameters
    ----------
    alignment
        Whether the first power sample overlaps warm-up or starts at the first analysed cycle.
    make_rtl_run
        Icarus Verilog event producer.
    run_tool
        Host command runner.
    tmp_path
        New report path.
    """
    run, manifest = make_rtl_run()
    manifest["warmup_cycles"] = 1
    if alignment == "aligned":
        power = run / "power.csv"
        content = power.read_bytes().replace(b"\n0,", b"\n5010,")
        power.write_bytes(content)
        manifest["files"]["power"]["sha256"] = hashlib.sha256(content).hexdigest()
    (run / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    output = tmp_path / "report"
    result = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    if alignment == "aligned":
        assert result.returncode == 0, result.stderr
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        assert report["energy"]["sample_count"] == 2
        assert report["tracking_error"]["sample_count"] == 2
    else:
        assert result.returncode == 1
        assert "overlaps discarded warm-up" in result.stderr


def test_power_window_without_cycle_is_excluded(
    make_rtl_run: MakeRtlRun, run_tool: RunTool, tmp_path: Path
) -> None:
    """Counter windows before the first anchor do not add energy to a cycle.

    Parameters
    ----------
    make_rtl_run
        Real RTL event producer.
    run_tool
        Public host command runner.
    tmp_path
        Report parent.
    """
    run, manifest = make_rtl_run()
    power = run / "power.csv"
    rows = power.read_text(encoding="utf-8").splitlines()
    rows[5:5] = [
        "5,VDD,1,0.1,0.01",
        "5,VDD25,2.5,0.1,0.02",
        "5,VDDA25,2.5,0.1,0.03",
        "5,VDDA,1,0.1,0.04",
    ]
    content = ("\n".join(rows) + "\n").encode()
    power.write_bytes(content)
    manifest["files"]["power"]["sha256"] = hashlib.sha256(content).hexdigest()
    (run / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    output = tmp_path / "report"
    result = run_tool("analyze_run", str(run / "manifest.json"), "--output-dir", str(output))
    assert result.returncode == 0, result.stderr
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["energy"]["window_count"] == 1
    assert report["energy"]["per_rail"]["VDD"] == pytest.approx((0.3 - 0.01) / 3)
