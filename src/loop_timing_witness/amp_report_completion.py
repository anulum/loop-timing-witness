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
    from .event_stream import Event
    from .run_manifest import RunInputs


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
    coefficients = dict(zip(COEFFICIENT_NAMES, run.coefficients, strict=True))
    if (
        manifest["started_utc"] != capture["started_utc"]
        or manifest["placement"] != "bare_metal_amp"
        or manifest["source"]["kind"] != "rtl_simulation"
        or manifest["cycle_count"] != run.cycles
        or manifest["sample_period_ticks"] != run.period_ticks
        or manifest["controller"]["name"] != ("lqr" if run.lqr else "pid")
        or manifest["controller"]["coefficients"] != coefficients
        or manifest["fault_schedule"] != fault_schedule(configuration)
        or inputs.files["tracking"]
        != tracking_csv(
            (directory / "tracking_raw.csv").read_bytes(), run.cycles, completion.samples
        )
        or manifest["measurement_domain"]["sha256"] != capture["files"]["measurement-domain.json"]
        or manifest["plant"]["fixed_point_format"] != "Q8.24"
        or manifest["plant"]["tracking_unit"] != "model_output"
        or manifest["plant"]["name"]
        != ("first_order_thermal" if completion.thermal else "second_order_mechanical")
        or manifest["files"]["events"]["sha256"] != capture["files"]["events.bin"]
    ):
        message = "AMP capture configuration does not match the run declaration"
        raise ValueError(message)
    full, _ = analyse_events(
        events, inputs.domain["design_contracts"]["event_profiles"]["CONTROL"], run.cycles, 0
    )
    control = full["control"]
    if (
        completion.events != len(events)
        or completion.samples != sum(event.name == "SAMPLE_READ" for event in events)
        or completion.overflow != manifest["instrument"]["fifo_overflow_count"]
        or completion.misses != control["deadline_misses"]
        or control["observed_deadlines"] != run.cycles
        or completion.safe != bool(control["safe_state_events"])
    ):
        message = "AMP completion counters do not match captured events"
        raise ValueError(message)
    report["amp_completion"] = capture["completion"]
    report["input_sha256"]["amp_capture"] = manifest["amp_capture"]["sha256"]
    report["limits"].append(
        "ISA functional clock mapping does not establish physical U54 execution latency."
    )
