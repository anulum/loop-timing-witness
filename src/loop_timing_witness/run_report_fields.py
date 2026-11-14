# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — control-run report fields

"""Derive the tracking, energy, validity, input and limit fields of a run report."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from .run_series import energy_per_cycle, tracking_error
from .tracking_observations import observed_tracking_error

if TYPE_CHECKING:
    from .event_stream import Event
    from .run_manifest import RunInputs

REPORT_SCHEMA: Final = "loop-timing-witness.analysis-report.v1"


def tracking_block(
    inputs: RunInputs, events: tuple[Event, ...], duration_ticks: int
) -> dict[str, Any]:
    """Return the tracking-error block the run's sampling and profile call for.

    Parameters
    ----------
    inputs
        Validated run inputs.
    events
        Decoded events of the run.
    duration_ticks
        Observation span of the ``events`` block.

    Returns
    -------
    dict[str, Any]
        Observed or complete tracking error, or ``not_applicable`` for COMPUTE, with the
        shared ``duration_ticks`` and a ``sample_count``.

    Raises
    ------
    ValueError
        If the tracking series contradicts the run contract.
    """
    manifest = inputs.manifest
    if manifest.get("tracking_sampling") == "observed":
        tracking = observed_tracking_error(
            inputs.files["tracking"],
            events,
            manifest["cycle_count"],
            manifest["warmup_cycles"],
            manifest["plant"]["tracking_unit"],
        )
    elif manifest["profile"] == "CONTROL":
        tracking = tracking_error(
            inputs.files.get("tracking"),
            manifest["cycle_count"],
            manifest["warmup_cycles"],
            manifest["plant"]["tracking_unit"],
        )
    else:
        tracking = {"status": "not_applicable", "reason": "COMPUTE has no control plant"}
    tracking["duration_ticks"] = duration_ticks
    tracking.setdefault("sample_count", 0)
    return tracking


def energy_block(
    inputs: RunInputs, events: tuple[Event, ...], duration_ticks: int
) -> dict[str, Any]:
    """Return the energy block with the shared ``duration_ticks``.

    Parameters
    ----------
    inputs
        Validated run inputs.
    events
        Decoded events of the run.
    duration_ticks
        Observation span of the ``events`` block.

    Returns
    -------
    dict[str, Any]
        Energy per cycle, or an unavailable block with a zero ``sample_count``.

    Raises
    ------
    ValueError
        If the power series contradicts the run contract.
    """
    manifest = inputs.manifest
    energy = energy_per_cycle(
        inputs.files.get("power"),
        events,
        manifest["profile"],
        manifest["warmup_cycles"],
        inputs.domain["design_contracts"]["power_rails"],
    )
    energy["duration_ticks"] = duration_ticks
    if energy["status"] == "unavailable":
        energy["sample_count"] = 0
    return energy


def anchor_count(
    manifest: dict[str, Any], summary: dict[str, Any], events: tuple[Event, ...]
) -> int:
    """Count the analysed cycles that carry their profile's anchor event.

    Parameters
    ----------
    manifest
        Schema-valid run manifest.
    summary
        The ``events`` block.
    events
        Decoded events of the run.

    Returns
    -------
    int
        Observed deadlines for CONTROL; post-warm-up ``INPUT_WRITE`` events for COMPUTE.
    """
    if manifest["profile"] == "CONTROL":
        return int(summary["control"]["observed_deadlines"])
    return sum(
        event.name == "INPUT_WRITE" and event.cycle >= manifest["warmup_cycles"] for event in events
    )


def input_sha256(manifest: dict[str, Any]) -> dict[str, str]:
    """Return the digest of every bound input: files, domain, sources and hardware.

    Parameters
    ----------
    manifest
        Schema-valid run manifest.

    Returns
    -------
    dict[str, str]
        SHA-256 by input name, in the report's order.
    """
    hashes = {name: item["sha256"] for name, item in manifest["files"].items() if item is not None}
    hashes["measurement_domain"] = manifest["measurement_domain"]["sha256"]
    hashes.update(
        {f"source:{item['path']}": item["sha256"] for item in manifest["source"]["files"]}
    )
    if manifest["hardware_artifacts"] is not None:
        hashes.update(
            {
                name: manifest["hardware_artifacts"][name]["sha256"]
                for name in ("bitstream", "firmware", "linux_image", "controller_binary")
            }
        )
    return hashes


def invalid_reasons(
    overflow: int,
    tracking: dict[str, Any],
    *,
    complete: bool,
    missing_tracking: bool,
    missing_energy: bool,
) -> list[str]:
    """Return why a run is not valid measurement evidence, in the report's order.

    Parameters
    ----------
    overflow
        FIFO overflow count.
    tracking
        The tracking-error block.
    complete
        Whether every analysed cycle has its anchor event.
    missing_tracking
        Whether a CONTROL run lacks an available tracking series.
    missing_energy
        Whether the power series is unavailable.

    Returns
    -------
    list[str]
        The reasons; empty for a valid run.
    """
    return [
        *(["event FIFO overflow"] if overflow else []),
        *(["missing cycle anchor events"] if not complete else []),
        *(
            ["tracking series incomplete"]
            if tracking["status"] == "partial"
            else ["tracking series unavailable"]
            if missing_tracking
            else []
        ),
        *(["power series unavailable"] if missing_energy else []),
    ]


def report_limits(contracts: dict[str, Any], tracking: dict[str, Any]) -> list[str]:
    """Return the stated limits of the report's claims.

    Parameters
    ----------
    contracts
        Valid measurement-domain design contracts.
    tracking
        The tracking-error block.

    Returns
    -------
    list[str]
        Timebase, plant, power and, for observed sampling, tracking limits.
    """
    return [
        (
            f"Timebase ticks resolve {contracts['timebase']['resolution_ns']} ns; "
            "interconnect offsets require calibration."
        ),
        "The plant is emulated; these are not physical-machine control results.",
        "Power rails share processor and fabric consumption. Energy is a window mean.",
        *(
            [
                (
                    "Tracking errors describe observed cycles only; "
                    "missing samples may bias the metric."
                )
            ]
            if tracking.get("sampling") == "observed"
            else []
        ),
    ]


def report_identity(manifest: dict[str, Any], contracts: dict[str, Any]) -> dict[str, Any]:
    """Return the report fields that identify the run, its evidence status and its inputs.

    Parameters
    ----------
    manifest
        Schema-valid run manifest.
    contracts
        Valid measurement-domain design contracts.

    Returns
    -------
    dict[str, Any]
        Schema through instrument floor, in the report's order.
    """
    return {
        "schema": REPORT_SCHEMA,
        "run_id": manifest["run_id"],
        "started_utc": manifest["started_utc"],
        "source_kind": manifest["source"]["kind"],
        "evidence_status": "simulation_only"
        if manifest["source"]["kind"] == "rtl_simulation"
        else "board_declaration_unverified",
        "profile": manifest["profile"],
        "placement": manifest["placement"],
        "measurement_domain_sha256": manifest["measurement_domain"]["sha256"],
        "input_sha256": input_sha256(manifest),
        "timebase_resolution_ns": contracts["timebase"]["resolution_ns"],
        "instrument_floor_ticks": manifest["instrument"]["floor_ticks"],
    }
