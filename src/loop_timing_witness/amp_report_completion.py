# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual dedicated-hart logger counters in public analysis

"""Attach actual AMP completion after reconciling run configuration and full event history."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .amp_capture_observations import fault_schedule, tracking_csv
from .amp_completion import completion_receipt
from .amp_run_input import read_amp_run
from .amp_simulation_manifest import COEFFICIENT_NAMES, admitted_capture
from .run_analysis import analyse_events

if TYPE_CHECKING:
    from pathlib import Path

    from .amp_completion import AmpCompletion
    from .amp_contract import AmpRun
    from .event_stream import Event
    from .run_manifest import RunInputs


def _run_matches(
    manifest: dict[str, Any], capture: dict[str, Any], run: AmpRun, configuration: bytes
) -> bool:
    """Tell whether the declared run is the captured run configuration.

    Parameters
    ----------
    manifest
        Run declaration.
    capture
        Admitted capture receipt.
    run, configuration
        Decoded run configuration and its original bytes.

    Returns
    -------
    bool
        Whether start time, placement, source, cycles, period, controller,
        coefficients and fault schedule all agree.
    """
    return not (
        manifest["started_utc"] != capture["started_utc"]
        or manifest["placement"] != "bare_metal_amp"
        or manifest["source"]["kind"] != "rtl_simulation"
        or manifest["cycle_count"] != run.cycles
        or manifest["sample_period_ticks"] != run.period_ticks
        or manifest["controller"]["name"] != ("lqr" if run.lqr else "pid")
        or manifest["controller"]["coefficients"]
        != dict(zip(COEFFICIENT_NAMES, run.coefficients, strict=True))
        or manifest["fault_schedule"] != fault_schedule(configuration)
    )


def _outputs_match(
    inputs: RunInputs,
    directory: Path,
    capture: dict[str, Any],
    completion: AmpCompletion,
    run: AmpRun,
) -> bool:
    """Tell whether the declared tracking, domain, plant and events are the captured ones.

    Parameters
    ----------
    inputs
        Public schema-valid, hash-bound run inputs.
    directory
        The inputs' original directory.
    capture, completion
        Admitted capture receipt and the logger's completion receipt.
    run
        Decoded run configuration.

    Returns
    -------
    bool
        Whether the observed tracking, measurement domain, plant and event file agree.
    """
    manifest = inputs.manifest
    return not (
        inputs.files["tracking"]
        != tracking_csv(
            (directory / "tracking_raw.csv").read_bytes(), run.cycles, completion.samples
        )
        or manifest["measurement_domain"]["sha256"] != capture["files"]["measurement-domain.json"]
        or manifest["plant"]["fixed_point_format"] != "Q8.24"
        or manifest["plant"]["tracking_unit"] != "model_output"
        or manifest["plant"]["name"]
        != ("first_order_thermal" if completion.thermal else "second_order_mechanical")
        or manifest["files"]["events"]["sha256"] != capture["files"]["events.bin"]
    )


def _counters_match(
    events: tuple[Event, ...],
    completion: AmpCompletion,
    control: dict[str, Any],
    manifest: dict[str, Any],
    cycles: int,
) -> bool:
    """Tell whether the logger's final counters agree with the captured events.

    Parameters
    ----------
    events
        Entire original history, including any excluded warm-up cycles.
    completion
        The logger's completion receipt.
    control
        Full-run control analysis of the events.
    manifest
        Run declaration.
    cycles
        Configured control cycles.

    Returns
    -------
    bool
        Whether records, samples, overflow, misses, deadlines and the safe state
        all agree.
    """
    return not (
        completion.events != len(events)
        or completion.samples != sum(event.name == "SAMPLE_READ" for event in events)
        or completion.overflow != manifest["instrument"]["fifo_overflow_count"]
        or completion.misses != control["deadline_misses"]
        or control["observed_deadlines"] != cycles
        or completion.safe != bool(control["safe_state_events"])
    )


def attach_amp_completion(
    inputs: RunInputs, report: dict[str, Any], events: tuple[Event, ...]
) -> None:
    """Compare actual final counters and original inputs with the complete captured event history.

    Parameters
    ----------
    inputs
        Public schema-valid, hash-bound run inputs.
    report
        Report assembled from all admitted observations.
    events
        Entire original history, including any excluded warm-up cycles.

    Raises
    ------
    OSError
        If original source artifacts are unavailable.
    ValueError
        If placement, configuration, plant, artifacts or actual final counters disagree.
    """
    if "amp_capture" not in inputs.files:
        return
    directory = inputs.directory
    if directory is None:
        message = "AMP analysis requires the original hash-bound manifest directory"
        raise ValueError(message)
    capture = admitted_capture(directory, inputs.files["amp_capture"])
    completion = completion_receipt((directory / "spike.log").read_bytes())
    configuration = (directory / "image/configuration.txt").read_bytes()
    run = read_amp_run(configuration)
    manifest = inputs.manifest
    if not (
        _run_matches(manifest, capture, run, configuration)
        and _outputs_match(inputs, directory, capture, completion, run)
    ):
        message = "AMP capture configuration does not match the run declaration"
        raise ValueError(message)
    full, _ = analyse_events(
        events, inputs.domain["design_contracts"]["event_profiles"]["CONTROL"], run.cycles, 0
    )
    if not _counters_match(events, completion, full["control"], manifest, run.cycles):
        message = "AMP completion counters do not match captured events"
        raise ValueError(message)
    report["amp_completion"] = capture["completion"]
    report["input_sha256"]["amp_capture"] = manifest["amp_capture"]["sha256"]
    report["limits"].append(
        "ISA functional clock mapping does not establish physical U54 execution latency."
    )
