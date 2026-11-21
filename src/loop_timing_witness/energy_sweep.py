# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — marginal energy per cycle from a loop-frequency sweep

"""Separate static rail power from the energy each control cycle adds.

A run report gives each rail's window-mean energy per cycle, ``E = P / f`` for a mean rail power
``P`` at the loop's cycle rate ``f``. Runs of one placement at several cycle rates and one
temperature give ``P(f)``; a least-squares line ``P = P0 + E_dyn * f`` separates the static power
``P0``, which the rail draws whatever the loop does, from the marginal energy ``E_dyn`` each
additional cycle costs. The slope is a per-cycle quantity that the window mean alone cannot give,
because the power monitor samples far more slowly than a cycle. Temperature changes static
power, so the runs must share a temperature within a declared tolerance.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from math import isfinite, sqrt
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from loop_timing_witness.manifest_io import parse_bounded_json_object, read_regular_bytes

if TYPE_CHECKING:
    from collections.abc import Sequence

DECLARATION_SCHEMA: Final = "loop-timing-witness.energy-sweep.v1"
"""Schema identifier of a sweep declaration."""

RESULT_SCHEMA: Final = "loop-timing-witness.energy-sweep-result.v1"
"""Schema identifier of a sweep result."""

MINIMUM_RATES: Final = 3
"""Distinct cycle rates a fit needs: a line and one degree of freedom for its residual."""


@dataclass(frozen=True)
class SweepPoint:
    """One run of the sweep.

    Attributes
    ----------
    run_id
        Run identifier from its report.
    frequency_hz
        Cycle rate of the run.
    temperature_c
        Temperature logged for the run.
    energy_per_cycle
        Window-mean joules per cycle by rail, from the report.
    """

    run_id: str
    frequency_hz: float
    temperature_c: float
    energy_per_cycle: dict[str, float]


def _line(rates: Sequence[float], powers: Sequence[float]) -> dict[str, float | None]:
    """Fit ``power = static + marginal * rate`` by ordinary least squares.

    Parameters
    ----------
    rates
        Cycle rates in hertz, at least ``MINIMUM_RATES`` distinct values.
    powers
        Mean rail power in watts at each rate.

    Returns
    -------
    dict[str, float | None]
        Static power and marginal energy with their standard errors, and the coefficient of
        determination, ``None`` when the powers agree to twelve significant digits, so that no
        variation is left to explain.
    """
    count = len(rates)
    mean_rate = sum(rates) / count
    mean_power = sum(powers) / count
    sxx = sum((rate - mean_rate) ** 2 for rate in rates)
    sxy = sum(
        (rate - mean_rate) * (power - mean_power) for rate, power in zip(rates, powers, strict=True)
    )
    marginal = sxy / sxx
    static = mean_power - marginal * mean_rate
    residual = sum(
        (power - static - marginal * rate) ** 2 for rate, power in zip(rates, powers, strict=True)
    )
    total = sum((power - mean_power) ** 2 for power in powers)
    variance = residual / (count - 2)
    return {
        "static_power_w": static,
        "static_power_standard_error_w": sqrt(variance * (1 / count + mean_rate**2 / sxx)),
        "marginal_energy_j": marginal,
        "marginal_energy_standard_error_j": sqrt(variance / sxx),
        "r_squared": None
        if max(powers) - min(powers) <= 1e-12 * max(map(abs, powers))
        else 1 - residual / total,
    }


def fit_marginal_energy(
    points: Sequence[SweepPoint], temperature_tolerance_c: float
) -> dict[str, Any]:
    """Fit each rail's static power and marginal energy per cycle over a sweep.

    Parameters
    ----------
    points
        Runs of one placement at different cycle rates.
    temperature_tolerance_c
        Largest allowed spread of the runs' temperatures.

    Returns
    -------
    dict[str, Any]
        Per rail and for all rails together: static power, marginal energy per cycle, their
        standard errors and the coefficient of determination; the rates, the temperature span and
        the method.

    Raises
    ------
    ValueError
        If fewer than ``MINIMUM_RATES`` distinct rates are given, a rate, temperature or energy is
        not finite, a rate is not positive, the runs have different rails, or their temperatures
        spread beyond the tolerance.
    """
    rates = [point.frequency_hz for point in points]
    temperatures = [point.temperature_c for point in points]
    values = [value for point in points for value in point.energy_per_cycle.values()]
    if not all(
        isfinite(number) for number in (*rates, *temperatures, *values, temperature_tolerance_c)
    ):
        message = "energy sweep values must be finite"
        raise ValueError(message)
    if len(set(rates)) < MINIMUM_RATES or min(rates) <= 0 or temperature_tolerance_c < 0:
        message = (
            f"energy sweep needs {MINIMUM_RATES} distinct positive cycle rates and a tolerance"
        )
        raise ValueError(message)
    rails = list(points[0].energy_per_cycle)
    if any(list(point.energy_per_cycle) != rails for point in points):
        message = "energy sweep runs report different rails"
        raise ValueError(message)
    span = max(temperatures) - min(temperatures)
    if span > temperature_tolerance_c:
        message = f"energy sweep temperatures spread {span} °C beyond {temperature_tolerance_c} °C"
        raise ValueError(message)
    per_rail = {
        rail: _line(rates, [point.energy_per_cycle[rail] * point.frequency_hz for point in points])
        for rail in rails
    }
    totals = [sum(point.energy_per_cycle.values()) * point.frequency_hz for point in points]
    return {
        "schema": RESULT_SCHEMA,
        "method": "least_squares_power_against_cycle_rate",
        "run_ids": [point.run_id for point in points],
        "cycle_rates_hz": rates,
        "temperature_span_c": span,
        "per_rail": per_rail,
        "total": _line(rates, totals),
    }


def _report_point(run: dict[str, Any], base: Path) -> tuple[SweepPoint, str]:
    """Read one declared run's report and return its point and placement.

    Parameters
    ----------
    run
        Declaration entry: ``report``, ``cycle_rate_hz`` and ``temperature_c``.
    base
        Directory that relative report paths start from.

    Returns
    -------
    tuple[SweepPoint, str]
        The run's sweep point and its placement.

    Raises
    ------
    ValueError
        If the entry is malformed, or the report is invalid or has no window-mean energy.
    """
    if set(run) != {"report", "cycle_rate_hz", "temperature_c"} or not isinstance(
        run["report"], str
    ):
        message = "energy sweep run needs exactly report, cycle_rate_hz and temperature_c"
        raise ValueError(message)
    path = base / run["report"]
    report = parse_bounded_json_object(read_regular_bytes(path), str(path))
    energy = report.get("energy", {})
    if report.get("valid") is not True or energy.get("method") != "window_mean":
        message = f"{path}: energy sweep needs a valid report with window-mean energy"
        raise ValueError(message)
    numbers = (run["cycle_rate_hz"], run["temperature_c"])
    if not all(type(number) in {int, float} for number in numbers):
        message = f"{path}: cycle rate and temperature must be numbers"
        raise ValueError(message)
    point = SweepPoint(
        report["run_id"],
        float(run["cycle_rate_hz"]),
        float(run["temperature_c"]),
        {rail: float(value) for rail, value in energy["per_rail"].items()},
    )
    return point, report["placement"]


def load_sweep(path: Path) -> tuple[list[SweepPoint], float]:
    """Read a sweep declaration and its run reports.

    The declaration is ``{"schema": "loop-timing-witness.energy-sweep.v1",
    "temperature_tolerance_c": number, "runs": [{"report": path, "cycle_rate_hz": number,
    "temperature_c": number}, ...]}``; report paths are relative to the declaration.

    Parameters
    ----------
    path
        Sweep declaration.

    Returns
    -------
    tuple[list[SweepPoint], float]
        The runs' points and the temperature tolerance.

    Raises
    ------
    ValueError
        If the declaration is malformed, a report is unusable, a run appears twice or the runs come
        from different placements.
    """
    declaration = parse_bounded_json_object(read_regular_bytes(path), str(path))
    tolerance = declaration.get("temperature_tolerance_c")
    runs = declaration.get("runs")
    if (
        set(declaration) != {"schema", "temperature_tolerance_c", "runs"}
        or declaration["schema"] != DECLARATION_SCHEMA
        or not isinstance(tolerance, int | float)
        or isinstance(tolerance, bool)
        or not isinstance(runs, list)
        or not all(isinstance(run, dict) for run in runs)
    ):
        message = f"{path}: not an energy sweep declaration"
        raise ValueError(message)
    loaded = [_report_point(run, path.parent) for run in runs]
    points = [point for point, _ in loaded]
    if (
        len({point.run_id for point in points}) != len(points)
        or len({place for _, place in loaded}) > 1
    ):
        message = f"{path}: energy sweep runs must be distinct runs of one placement"
        raise ValueError(message)
    return points, float(tolerance)


def main(argv: list[str] | None = None) -> int:
    """Fit a declared sweep and print the result as JSON.

    Parameters
    ----------
    argv
        One argument, the sweep declaration path; ``None`` reads ``sys.argv``.

    Returns
    -------
    int
        0 after printing the result, 2 for a refused declaration or wrong usage.
    """
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        print("usage: python -m loop_timing_witness.energy_sweep DECLARATION", file=sys.stderr)
        return 2
    try:
        points, tolerance = load_sweep(Path(arguments[0]))
        result = fit_marginal_energy(points, tolerance)
    except (OSError, ValueError) as error:
        print(f"energy sweep refused: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
