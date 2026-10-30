# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete public neural acquisition binding

"""Bind an admitted public acquisition and every source, channel and receipt byte."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .manifest_io import parse_json_object
from .neural_event_stream import NeuralCaptureRefusalError
from .neural_run_capture_binding import bind_neural_capture
from .neural_run_files import read_neural_manifest_root
from .neural_run_files import read_neural_run_file as read_neural_bound_file
from .neural_run_manifest import decode_neural_manifest
from .neural_run_policy import REVIEWED_REGISTRY, admitted_neural_contract

if TYPE_CHECKING:
    from pathlib import Path

    from .neural_capture import NeuralCaptureBundle
    from .neural_run_policy import NeuralRegistry, NeuralSourceContract

JSON_LIMIT = 65536
SOURCE_LIMIT = 1048576
TRACE_FIELDS = (
    "input_trace",
    "numerical_trace",
    "numerical_projection",
    "reference_projection",
    "service_trace",
    "clock_schedule_ref",
)
TOOL_FIELDS = (
    "compiler_simulator_runtime",
    "source_owned_public_model_checker",
    "counter_receipt",
    "raw_spike_trace",
    "original_stimulus",
    "actual_completion",
    "existing_trial_analysis",
    "declared_clock_schedule",
)
ORIGINAL_PINS = {
    "original_stimulus": "8f0e0a2ced3e5170c78c5ee058eb90faea1ceb77cece2f940568851fe9ed64f8",
    "reference_projection": "c405de711cdbf8fae3a0c668ecfa643e7a6e460bad60c05b5bd0bfca208a3dd2",
}


@dataclass(frozen=True, slots=True)
class BoundNeuralRun:
    """Complete source-admitted original bytes awaiting independent full analysis.

    Attributes
    ----------
    directory, manifest_bytes, manifest
        Immutable acquisition root and original carrier declarations.
    contract
        Consumer-owned reviewed source and checker installation selection.
    files, sources, tool
        Complete original auxiliary bytes, source bodies and closed tool receipt.
    capture
        Independent interpretation of all three original capture channels.
    """

    directory: Path
    manifest_bytes: bytes
    manifest: dict[str, Any]
    contract: NeuralSourceContract
    files: dict[str, bytes]
    sources: dict[str, bytes]
    tool: dict[str, Any]
    capture: NeuralCaptureBundle


def _sources(
    directory: Path, manifest: dict[str, Any], contract: NeuralSourceContract
) -> dict[str, bytes]:
    """Require the entire reviewed source population and all seven SC body pins.

    Parameters
    ----------
    directory, manifest
        Immutable run and closed carrier declarations.
    contract
        Exact consumer-reviewed source policy.

    Returns
    -------
    dict[str, bytes]
        Complete original source bodies, never executable paths supplied by a run.

    Raises
    ------
    NeuralCaptureRefusalError
        If any body, population, source pin or duplicate differs from the policy.
    """
    expected = contract.policy["sources"]
    references = manifest["source_files"]
    if {item["path"] for item in references} != set(expected):
        message = "Complete public neural source population differs from its reviewed policy."
        raise NeuralCaptureRefusalError(message)
    result = {}
    for reference in references:
        name = reference["path"]
        if {key: reference[key] for key in ("sha256", "byte_length")} != expected[name]:
            message = "Public neural source reference differs from its reviewed policy."
            raise NeuralCaptureRefusalError(message)
        result[name] = read_neural_bound_file(directory, reference, SOURCE_LIMIT)
    for name, digest in manifest["sc_body_pins"].items():
        body = result.get(f"source/SC-NEUROCORE/{name}")
        if body is None or hashlib.sha256(body).hexdigest() != digest:
            message = "Public neural SC body pin differs from its complete source binding."
            raise NeuralCaptureRefusalError(message)
    return result


def _auxiliary_files(
    directory: Path, manifest: dict[str, Any]
) -> tuple[dict[str, bytes], dict[str, Any]]:
    """Bind every closed native, source-checker and actual reset auxiliary role.

    Parameters
    ----------
    directory, manifest
        Source-admitted acquisition and closed public declarations.

    Returns
    -------
    tuple[dict[str, bytes], dict[str, Any]]
        Complete original files and the closed versioned tool receipt.

    Raises
    ------
    NeuralCaptureRefusalError
        If the tool, source-checker or original reset roles are incomplete.
    """
    files = {
        name: read_neural_bound_file(directory, manifest[name], JSON_LIMIT)
        for name in (*TRACE_FIELDS, "tool_receipt")
    }
    tool = parse_json_object(files["tool_receipt"], "public neural tool receipt")
    resets = {"reset_epoch_receipt", "abandoned_prefix_traces"} if manifest["epoch"] else set()
    if (
        set(tool) != {"schema_id", "scope", "checker_receipts", *TOOL_FIELDS, *resets}
        or tool["schema_id"] != "loop-timing-witness.neural-tool-receipt.v1"
        or type(tool["scope"]) is not str
    ):
        message = "Public neural tool receipt requires its complete closed successor."
        raise NeuralCaptureRefusalError(message)
    for name in TOOL_FIELDS:
        files[name] = read_neural_bound_file(
            directory, tool[name], SOURCE_LIMIT if name == "existing_trial_analysis" else JSON_LIMIT
        )
    checker = tool["checker_receipts"]
    if not isinstance(checker, dict) or set(checker) != {"generation", "check"}:
        message = "Public neural tool receipt requires both actual checker invocations."
        raise NeuralCaptureRefusalError(message)
    for operation, reference in checker.items():
        files[f"checker_{operation}_receipt"] = read_neural_bound_file(
            directory, reference, JSON_LIMIT
        )
    if resets:
        files["reset_epoch_receipt"] = read_neural_bound_file(
            directory, tool["reset_epoch_receipt"], JSON_LIMIT
        )
        prefixes = tool["abandoned_prefix_traces"]
        if not isinstance(prefixes, dict) or set(prefixes) != {
            "input",
            "numerical",
            "raw_spike",
            "service",
        }:
            message = "Public neural reset requires all four original abandoned-prefix traces."
            raise NeuralCaptureRefusalError(message)
        for name, reference in prefixes.items():
            files[f"abandoned_{name}_trace"] = read_neural_bound_file(
                directory, reference, JSON_LIMIT
            )
    return files, tool


def bind_public_neural_run(
    path: Path, *, registry: NeuralRegistry = REVIEWED_REGISTRY
) -> BoundNeuralRun:
    """Bind the complete public run before full numerical, timing and runtime analysis.

    Parameters
    ----------
    path
        Closed public manifest in an immutable complete acquisition directory.
    registry
        The consumer's own reviewed source entries; acquisition data never selects it.

    Returns
    -------
    BoundNeuralRun
        Source-admitted original bytes. Full verdicts require all trace, runtime,
        source-owned checker, completion, clock and reset analyses.

    Raises
    ------
    NeuralCaptureRefusalError
        If source admission or any original required file prevents interpretation.
    """
    raw = read_neural_manifest_root(path)
    manifest = decode_neural_manifest(raw)
    directory = path.parent.resolve(strict=True)
    contract = admitted_neural_contract(directory, manifest, registry)
    sources = _sources(directory, manifest, contract)
    files, tool = _auxiliary_files(directory, manifest)
    for name, digest in ORIGINAL_PINS.items():
        if hashlib.sha256(files[name]).hexdigest() != digest:
            message = "Public neural fixture differs from the selected source contract."
            raise NeuralCaptureRefusalError(message)
    if sources.get("stimuli.txt") != files["original_stimulus"]:
        message = "Public neural source stimulus differs from its identified input binding."
        raise NeuralCaptureRefusalError(message)
    capture = bind_neural_capture(directory, manifest, tool)
    return BoundNeuralRun(directory, raw, manifest, contract, files, sources, tool, capture)
