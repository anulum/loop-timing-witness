# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete neural run observations

"""Reconcile actual compiled source and historical source-checker receipts."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from .neural_run_clock import FLAG, TEXT, UNSIGNED, decode_actual_receipt
from .neural_run_native_runtime import analyze_native_runtime

if TYPE_CHECKING:
    from .neural_run_binding import BoundNeuralRun
    from .neural_run_traces import NeuralTraceAnalysis


def _checker_findings(run: BoundNeuralRun, traces: NeuralTraceAnalysis) -> tuple[str, ...]:
    """Reconcile recorded historical checker fields without treating them as execution.

    Parameters
    ----------
    run
        Complete original stimulus, oracle, projection and source bindings.
    traces
        Independently recomputed original trace counts.

    Returns
    -------
    tuple[str, ...]
        Located historical checker receipt inconsistencies.

    Raises
    ------
    ValueError
        If recorded checker structure prevents reliable interpretation.
    """
    checker = decode_actual_receipt(
        run.files["source_owned_public_model_checker"],
        "historical source checker",
        {
            **dict.fromkeys(("rows", "spikes"), UNSIGNED),
            **dict.fromkeys(
                (
                    "original_input_sha256",
                    "reference_sha256",
                    "actual_projection_sha256",
                    "model_module",
                    "model_sha256",
                    "constants_module",
                    "constants_sha256",
                ),
                TEXT,
            ),
            "source_owned_public_checker_pass": FLAG,
        },
    )
    expected = {
        "rows": run.manifest["step_count"],
        "spikes": traces.raw_spikes,
        "original_input_sha256": hashlib.sha256(run.files["original_stimulus"]).hexdigest(),
        "reference_sha256": hashlib.sha256(run.files["reference_projection"]).hexdigest(),
        "actual_projection_sha256": hashlib.sha256(run.files["numerical_projection"]).hexdigest(),
        "model_sha256": run.manifest["sc_body_pins"]["src/sc_neurocore/neurons/fixed_point_lif.py"],
        "constants_sha256": run.manifest["sc_body_pins"]["src/sc_neurocore/constants.py"],
        "source_owned_public_checker_pass": True,
    }
    return tuple(
        f"Historical source checker binding differs: {name}."
        for name, value in expected.items()
        if checker[name] != value
    )


def analyze_source_receipts(run: BoundNeuralRun, traces: NeuralTraceAnalysis) -> tuple[str, ...]:
    """Reconcile actual compiled source and recorded checker provenance independently.

    Parameters
    ----------
    run
        Full original source, compiler and checker receipt bindings.
    traces
        Independent actual original numerical/raw trace counts.

    Returns
    -------
    tuple[str, ...]
        Located source, configuration, command and checker inconsistencies.

    Raises
    ------
    ValueError
        If actual recorded receipt structure prevents reliable interpretation.
    """
    return (*analyze_native_runtime(run), *_checker_findings(run, traces))
