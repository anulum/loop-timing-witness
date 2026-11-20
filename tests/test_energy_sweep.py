# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — marginal energy per cycle from a loop-frequency sweep

"""Check the static-power and marginal-energy fit and its declaration reader."""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
from math import inf, nan
from typing import TYPE_CHECKING, Any

import pytest

from conftest import REPOSITORY_ROOT
from loop_timing_witness.energy_sweep import (
    DECLARATION_SCHEMA,
    SweepPoint,
    fit_marginal_energy,
    load_sweep,
    main,
)
from loop_timing_witness.host_profile import scaled

if TYPE_CHECKING:
    from pathlib import Path

RATES = (500.0, 1000.0, 2000.0, 4000.0)


def _point(rate: float, powers: dict[str, float], temperature: float = 25.0) -> SweepPoint:
    """Return a sweep point whose rails draw the given mean powers.

    Parameters
    ----------
    rate
        Cycle rate in hertz.
    powers
        Mean watts by rail.
    temperature
        Logged temperature.

    Returns
    -------
    SweepPoint
        Point with window-mean energy per cycle ``power / rate``.
    """
    return SweepPoint(
        f"run-{rate}", rate, temperature, {rail: p / rate for rail, p in powers.items()}
    )


def test_an_exact_line_gives_its_static_power_and_marginal_energy() -> None:
    """Powers on a line give back its intercept and slope with zero standard errors."""
    points = [_point(rate, {"VDD": 0.5 + 2e-4 * rate, "VDDA": 0.1 + 1e-5 * rate}) for rate in RATES]
    result = fit_marginal_energy(points, 0.5)
    vdd = result["per_rail"]["VDD"]
    assert vdd["static_power_w"] == pytest.approx(0.5)
    assert vdd["marginal_energy_j"] == pytest.approx(2e-4)
    assert vdd["static_power_standard_error_w"] == pytest.approx(0.0, abs=1e-12)
    assert vdd["r_squared"] == pytest.approx(1.0)
    assert result["total"]["marginal_energy_j"] == pytest.approx(2.1e-4)
    assert result["total"]["static_power_w"] == pytest.approx(0.6)
    assert result["run_ids"] == [f"run-{rate}" for rate in RATES]
    assert result["temperature_span_c"] == 0.0


def test_a_noisy_sweep_matches_an_independent_fit_and_its_standard_errors() -> None:
    """The fit equals the standard library's least-squares line, with textbook standard errors."""
    powers = [0.62, 0.71, 0.93, 1.38]
    points = [
        _point(rate, {"VDD": power}, 25.0 + 0.1 * index)
        for index, (rate, power) in enumerate(zip(RATES, powers, strict=True))
    ]
    result = fit_marginal_energy(points, 0.5)["per_rail"]["VDD"]
    expected = statistics.linear_regression(RATES, powers)
    assert result["marginal_energy_j"] == pytest.approx(expected.slope)
    assert result["static_power_w"] == pytest.approx(expected.intercept)
    residuals = [
        p - expected.intercept - expected.slope * r for r, p in zip(RATES, powers, strict=True)
    ]
    variance = sum(e * e for e in residuals) / (len(RATES) - 2)
    sxx = sum((r - statistics.fmean(RATES)) ** 2 for r in RATES)
    assert result["marginal_energy_standard_error_j"] == pytest.approx((variance / sxx) ** 0.5)
    assert 0 < result["r_squared"] < 1


def test_constant_power_has_no_coefficient_of_determination() -> None:
    """When every run draws the same power the slope is zero and r² is undefined."""
    result = fit_marginal_energy([_point(rate, {"VDD": 0.8}) for rate in RATES[:3]], 0.0)
    assert result["per_rail"]["VDD"]["marginal_energy_j"] == pytest.approx(0.0, abs=1e-15)
    assert result["per_rail"]["VDD"]["r_squared"] is None


@pytest.mark.parametrize(
    ("points", "tolerance", "message"),
    [
        ([_point(500.0, {"VDD": 1.0}), _point(1000.0, {"VDD": 1.0})], 1.0, "3 distinct positive"),
        ([_point(r, {"VDD": 1.0}) for r in (500.0, 500.0, 1000.0)], 1.0, "3 distinct positive"),
        (
            [SweepPoint(f"r{r}", r, 25.0, {"VDD": 1e-3}) for r in (0.0, 500.0, 1000.0)],
            1.0,
            "3 distinct positive",
        ),
        ([_point(r, {"VDD": 1.0}) for r in RATES[:3]], -1.0, "3 distinct positive"),
        ([_point(r, {"VDD": 1.0}) for r in (inf, 500.0, 1000.0)], 1.0, "must be finite"),
        ([_point(r, {"VDD": nan}) for r in RATES[:3]], 1.0, "must be finite"),
        (
            [
                _point(500.0, {"VDD": 1.0}),
                _point(1000.0, {"VDDA": 1.0}),
                _point(2000.0, {"VDD": 1.0}),
            ],
            1.0,
            "different rails",
        ),
        (
            [_point(r, {"VDD": 1.0}, 25.0 + i) for i, r in enumerate(RATES[:3])],
            1.5,
            "spread 2.0 °C beyond 1.5 °C",
        ),
    ],
)
def test_unusable_sweeps_are_refused(
    points: list[SweepPoint], tolerance: float, message: str
) -> None:
    """Too few rates, non-positive or non-finite values, mixed rails or warm runs are refused.

    Parameters
    ----------
    points
        Sweep points.
    tolerance
        Temperature tolerance.
    message
        Expected refusal text.
    """
    with pytest.raises(ValueError, match=message):
        fit_marginal_energy(points, tolerance)


def _report(
    run_id: str, placement: str = "linux_user", *, valid: bool = True, method: str = "window_mean"
) -> dict[str, Any]:
    """Return the report fields a sweep reads.

    Parameters
    ----------
    run_id, placement
        Report identity.
    valid
        Report validity.
    method
        Energy method.

    Returns
    -------
    dict[str, Any]
        A minimal report.
    """
    return {
        "run_id": run_id,
        "placement": placement,
        "valid": valid,
        "energy": {
            "status": "available",
            "method": method,
            "per_rail": {"VDD": 1e-3, "VDDA": 2e-4},
        },
    }


def _declaration(directory: Path, reports: list[dict[str, Any]], **changes: object) -> Path:
    """Write reports and a declaration over them at cycle rates of 1, 2 and 4 kHz.

    Parameters
    ----------
    directory
        Owned directory.
    reports
        Report documents.
    **changes
        Declaration members to replace.

    Returns
    -------
    Path
        Declaration path.
    """
    runs = []
    for index, report in enumerate(reports):
        name = f"report-{index}.json"
        (directory / name).write_text(json.dumps(report), encoding="utf-8")
        runs.append({"report": name, "cycle_rate_hz": 1000 * 2**index, "temperature_c": 25.0})
    declaration = {
        "schema": DECLARATION_SCHEMA,
        "temperature_tolerance_c": 1,
        "runs": runs,
        **changes,
    }
    path = directory / "sweep.json"
    path.write_text(json.dumps(declaration), encoding="utf-8")
    return path


def test_a_declared_sweep_is_read_and_fitted(tmp_path: Path) -> None:
    """Reports named by a declaration become sweep points of one placement."""
    path = _declaration(tmp_path, [_report(f"r{i}") for i in range(3)])
    points, tolerance = load_sweep(path)
    assert tolerance == 1.0
    assert [point.frequency_hz for point in points] == [1000.0, 2000.0, 4000.0]
    assert points[0].energy_per_cycle == {"VDD": 1e-3, "VDDA": 2e-4}
    result = fit_marginal_energy(points, tolerance)
    assert result["per_rail"]["VDD"]["marginal_energy_j"] == pytest.approx(1e-3)
    assert result["per_rail"]["VDD"]["static_power_w"] == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize(
    ("reports", "changes", "message"),
    [
        ([_report("r0")] * 1, {"schema": "other"}, "not an energy sweep declaration"),
        ([_report("r0")] * 1, {"temperature_tolerance_c": "1"}, "not an energy sweep declaration"),
        ([_report("r0")] * 1, {"runs": {}}, "not an energy sweep declaration"),
        ([_report("r0")] * 1, {"runs": [1]}, "not an energy sweep declaration"),
        ([_report("r0")] * 1, {"extra": 1}, "not an energy sweep declaration"),
        (
            [_report("r0")] * 1,
            {"runs": [{"report": "report-0.json"}]},
            "exactly report, cycle_rate_hz",
        ),
        ([_report("r0", valid=False)], {}, "valid report with window-mean energy"),
        ([_report("r0", method="other")], {}, "valid report with window-mean energy"),
        (
            [_report("r0")],
            {"runs": [{"report": "report-0.json", "cycle_rate_hz": "1", "temperature_c": 25}]},
            "must be numbers",
        ),
        ([_report("r0"), _report("r0")], {}, "distinct runs of one placement"),
        ([_report("r0"), _report("r1", "fabric")], {}, "distinct runs of one placement"),
    ],
)
def test_unusable_declarations_are_refused(
    tmp_path: Path, reports: list[dict[str, Any]], changes: dict[str, Any], message: str
) -> None:
    """Malformed declarations, unusable reports, repeated runs and mixed placements are refused.

    Parameters
    ----------
    tmp_path
        Owned directory.
    reports
        Report documents.
    changes
        Declaration members to replace.
    message
        Expected refusal text.
    """
    with pytest.raises(ValueError, match=message):
        load_sweep(_declaration(tmp_path, reports, **changes))


def test_the_command_prints_the_fit_or_refuses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The module command prints the result, refuses an unusable declaration and wrong usage."""
    assert main([]) == 2
    assert "usage:" in capsys.readouterr().err
    assert main([str(tmp_path / "missing.json")]) == 2
    assert "energy sweep refused:" in capsys.readouterr().err
    path = _declaration(tmp_path, [_report(f"r{i}") for i in range(3)])
    result = subprocess.run(
        [sys.executable, "-m", "loop_timing_witness.energy_sweep", str(path)],
        cwd=REPOSITORY_ROOT,
        env={**os.environ},
        capture_output=True,
        text=True,
        check=False,
        timeout=scaled(30),
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["method"] == "least_squares_power_against_cycle_rate"
