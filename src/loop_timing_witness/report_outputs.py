# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — atomic host report outputs

"""Write deterministic JSON, CSV and SVG reports as one directory transaction."""

from __future__ import annotations

import csv
import io
import shutil
import tempfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from .manifest_io import canonical_json_bytes


def _csv_bytes(columns: tuple[str, ...], rows: list[dict[str, Any]]) -> bytes:
    """Serialise one table with a fixed column order.

    Parameters
    ----------
    columns
        CSV header.
    rows
        Values to render under that header.

    Returns
    -------
    bytes
        UTF-8 CSV with CRLF row separators.
    """
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _interval_summary_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten per-interval distribution objects into a CSV table.

    Parameters
    ----------
    report
        Valid analysis report.

    Returns
    -------
    list[dict[str, Any]]
        Rows sorted by interval name.
    """
    return [
        {
            "run_id": report["run_id"],
            "evidence_status": report["evidence_status"],
            "interval": name,
            **statistics,
        }
        for name, statistics in sorted(report["events"]["intervals"].items())
    ]


def _svg_plot(title: str, labels: list[str], values: list[float], unit: str) -> bytes:
    """Render a labelled horizontal bar chart without a plotting dependency.

    Parameters
    ----------
    title
        Descriptive chart title.
    labels
        Row labels.
    values
        Finite nonnegative values paired with labels.
    unit
        Unit on the horizontal axis.

    Returns
    -------
    bytes
        Standalone UTF-8 SVG plot.
    """
    width = 960
    height = max(160, 100 + 38 * len(labels))
    extent = max(values, default=0.0)
    scale = 580 / extent if extent else 0.0
    lines = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">'
        ),
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="24" y="32" font-family="sans-serif" font-size="20">{escape(title)}</text>',
        f'<text x="354" y="57" font-family="sans-serif" font-size="12">{escape(unit)}</text>',
    ]
    for index, (label, value) in enumerate(zip(labels, values, strict=True)):
        y = 76 + 38 * index
        lines.extend(
            [
                (
                    f'<text x="24" y="{y + 16}" font-family="sans-serif" font-size="13">'
                    f"{escape(label)}</text>"
                ),
                f'<rect x="354" y="{y}" width="{value * scale:.3f}" height="22" fill="#24579b"/>',
                (
                    f'<text x="{min(930, 362 + value * scale):.3f}" y="{y + 16}" '
                    f'font-family="sans-serif" font-size="12">{value:.6g}</text>'
                ),
            ]
        )
    lines.append("</svg>")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _plots(report: dict[str, Any]) -> dict[str, bytes]:
    """Build honest plots from available report metrics.

    Parameters
    ----------
    report
        Valid analysis report.

    Returns
    -------
    dict[str, bytes]
        SVG filenames and contents.
    """
    intervals = report["events"]["intervals"]
    labels = [name for name, data in sorted(intervals.items()) if data["p99_ticks"] is not None]
    values = [float(intervals[name]["p99_ticks"]) for name in labels]
    result = {
        "interval_p99.svg": _svg_plot(
            f"99th percentile event intervals ({report['evidence_status']})",
            labels,
            values,
            "clock ticks",
        )
    }
    energy = report["energy"]
    if energy["status"] == "available":
        rail_labels = sorted(energy["per_rail"])
        rail_values = [energy["per_rail"][rail] for rail in rail_labels]
        result["energy_per_cycle.svg"] = _svg_plot(
            f"Mean rail energy per cycle ({report['evidence_status']})",
            rail_labels,
            rail_values,
            "J/cycle",
        )
    return result


def write_report(
    output_directory: Path, report: dict[str, Any], cycle_rows: list[dict[str, int | str]]
) -> None:
    """Create an output directory only after every artefact is written.

    Parameters
    ----------
    output_directory
        New directory for the report. It must not already exist.
    report
        Complete validated report.
    cycle_rows
        Per-cycle event intervals.

    Raises
    ------
    FileExistsError
        If the output directory already exists.
    OSError
        If an artefact cannot be written or the transaction cannot land.
    """
    target = output_directory.resolve()
    if target.exists():
        message = f"report directory already exists: {target}"
        raise FileExistsError(message)
    parent = target.parent
    if not parent.is_dir():
        message = f"report parent does not exist: {parent}"
        raise FileNotFoundError(message)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=parent))
    try:
        (staging / "report.json").write_bytes(canonical_json_bytes(report))
        (staging / "interval_summary.csv").write_bytes(
            _csv_bytes(
                (
                    "run_id",
                    "evidence_status",
                    "interval",
                    "sample_count",
                    "median_ticks",
                    "p95_ticks",
                    "p99_ticks",
                    "p999_ticks",
                    "maximum_ticks",
                    "duration_ticks",
                ),
                _interval_summary_rows(report),
            )
        )
        (staging / "cycle_intervals.csv").write_bytes(
            _csv_bytes(
                ("run_id", "evidence_status", "cycle", "interval", "ticks"),
                [
                    {
                        "run_id": report["run_id"],
                        "evidence_status": report["evidence_status"],
                        **row,
                    }
                    for row in cycle_rows
                ],
            )
        )
        for filename, content in _plots(report).items():
            (staging / filename).write_bytes(content)
        staging.rename(target)
    except BaseException:
        shutil.rmtree(staging)
        raise
