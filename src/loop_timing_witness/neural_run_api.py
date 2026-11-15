# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete public neural analysis API

"""Load complete admitted neural acquisitions and expose independent whole-run verdicts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .manifest_io import JsonInputRefusalError, canonical_json_bytes, parse_json_object
from .neural_capture_report import neural_capture_report
from .neural_checker import verify_source_checker
from .neural_event_stream import NeuralCaptureRefusalError
from .neural_run_binding import bind_public_neural_run
from .neural_run_policy import REVIEWED_REGISTRY
from .neural_run_receipts import analyze_receipt_dimensions
from .neural_run_reset import analyze_actual_reset
from .neural_run_traces import analyze_original_traces

if TYPE_CHECKING:
    from pathlib import Path

    from .neural_checker import NeuralCheckerFindings
    from .neural_run_binding import BoundNeuralRun
    from .neural_run_policy import NeuralRegistry
    from .neural_run_receipts import NeuralReceiptFindings
    from .neural_run_traces import NeuralTraceAnalysis

_INPUT_SEAL = object()
NEURAL_REPORT_SCHEMA = "loop-timing-witness.neural-step-analysis-report.v1"
_LIMITS = (
    "Capture ticks are simulator edges; physical timing and calibration are unavailable.",
    "File integrity and correspondence do not authenticate a remote producer.",
    "This verdict covers the selected single-neuron source cohort and full original acquisition.",
    "A passing run does not establish model-family, physical or whole-project acceptance.",
)


class NeuralRunError(RuntimeError):
    """An unexpected analysis failure with a fixed caller-safe diagnostic."""


@dataclass(frozen=True, slots=True, init=False, match_args=False)
class NeuralRunInputs:
    """Immutable full-verification snapshot created only by the public run loader.

    Attributes
    ----------
    directory, manifest_bytes
        Original acquisition location and complete captured root bytes.
    report_bytes
        Canonical report derived from all admitted original bytes and real checker jobs.
    """

    directory: Path
    manifest_bytes: bytes
    report_bytes: bytes
    _loader_origin: object = field(repr=False)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        """Refuse caller construction and replacement of a verified snapshot.

        Parameters
        ----------
        *_args, **_kwargs
            Caller-supplied arguments cannot replace full loader verification.

        Raises
        ------
        NeuralCaptureRefusalError
            Always; snapshots are returned by ``load_neural_run``.
        """
        message = "Neural reports require the complete public run loader snapshot."
        raise NeuralCaptureRefusalError(message)


def _verdicts(
    run: BoundNeuralRun,
    traces: NeuralTraceAnalysis,
    receipts: NeuralReceiptFindings,
    reset: tuple[str, ...],
    checker: NeuralCheckerFindings,
) -> dict[str, dict[str, Any]]:
    """Group every finding into its independent verdict dimension.

    Parameters
    ----------
    run
        Entire byte-bound acquisition, whose capture refusals count as findings.
    traces, receipts, reset, checker
        Original trace, receipt, reset and actual source-checker analyses.

    Returns
    -------
    dict[str, dict[str, Any]]
        Pass flag and distinct findings of each of the five dimensions.
    """
    dimensions = {
        "source_binding": (*traces.source, *receipts.source, *checker.source),
        "capture": (*run.capture.refusals, *traces.joins, *receipts.capture, *traces.service),
        "numerical": (*traces.numerical, *checker.numerical),
        "completion": (*receipts.completion, *receipts.publication, *reset, *checker.completion),
        "clock": receipts.clock,
    }
    return {
        name: {"pass": not findings, "findings": list(findings)}
        for name, findings in dimensions.items()
    }


def _source_binding(run: BoundNeuralRun, verdict: dict[str, Any]) -> dict[str, Any]:
    """Return the source-binding block with its original identities and receipts.

    Parameters
    ----------
    run
        Entire byte-bound acquisition.
    verdict
        Source-binding pass flag and findings.

    Returns
    -------
    dict[str, Any]
        Verdict, source identity, tool and runtime receipts, both checker
        executions and the digest and length of every original input.
    """
    return {
        **verdict,
        "source_contract_ref": run.manifest["source_contract_ref"],
        "admitted_source_identity": list(run.contract.key),
        "tool_receipt": run.tool,
        "compiled_runtime": parse_json_object(
            run.files["compiler_simulator_runtime"], "bound native runtime receipt"
        ),
        "checker_invocations": {
            operation: parse_json_object(
                run.files[f"fresh_checker_{operation}_execution_receipt"],
                "fresh source checker execution receipt",
            )
            for operation in ("generate", "check")
        },
        "original_sources": {
            name: {"sha256": hashlib.sha256(raw).hexdigest(), "byte_length": len(raw)}
            for name, raw in run.sources.items()
        },
        "original_inputs": {
            name: {"sha256": hashlib.sha256(raw).hexdigest(), "byte_length": len(raw)}
            for name, raw in {"manifest": run.manifest_bytes, **run.files}.items()
        },
    }


def _completion(run: BoundNeuralRun, verdict: dict[str, Any]) -> dict[str, Any]:
    """Return the completion block with the declared and actual receipts.

    Parameters
    ----------
    run
        Entire byte-bound acquisition.
    verdict
        Completion pass flag and findings.

    Returns
    -------
    dict[str, Any]
        Verdict, epoch, declared completion, actual completion receipt and the
        reset receipt when the acquisition holds one.
    """
    return {
        **verdict,
        "epoch": run.manifest["epoch"],
        "declared": run.manifest["completion"],
        "actual_receipt": parse_json_object(
            run.files["actual_completion"], "bound actual completion receipt"
        ),
        "reset_receipt": (
            parse_json_object(run.files["reset_epoch_receipt"], "bound actual reset receipt")
            if "reset_epoch_receipt" in run.files
            else None
        ),
    }


def _analyse(run: BoundNeuralRun) -> dict[str, Any]:
    """Recompute all full source, capture, numerical, completion and clock verdicts.

    Parameters
    ----------
    run
        Entire byte-bound acquisition selected by the immutable source registry.

    Returns
    -------
    dict[str, Any]
        Complete public report, retaining distinct findings and whole conjunction.
    """
    traces = analyze_original_traces(run)
    receipts = analyze_receipt_dimensions(run, traces)
    reset = analyze_actual_reset(run)
    checker = verify_source_checker(run)
    verdicts = _verdicts(run, traces, receipts, reset, checker)
    capture = neural_capture_report(run.capture)
    return {
        "schema_id": NEURAL_REPORT_SCHEMA,
        "profile": run.manifest["profile"],
        "evidence_class": run.manifest["evidence_class"],
        "run_id": run.manifest["run_id"],
        "source_binding": _source_binding(run, verdicts["source_binding"]),
        "capture": {**capture, **verdicts["capture"]},
        "numerical": {
            **verdicts["numerical"],
            "requested_steps": run.manifest["step_count"],
            "actual_raw_spikes": traces.raw_spikes,
            "actual_service_packets": traces.service_packets,
            "original_oracle_equal": not traces.numerical,
            "source_checker_executed": checker.executed,
        },
        "completion": _completion(run, verdicts["completion"]),
        "clock": {
            **verdicts["clock"],
            "actual_schedule": parse_json_object(
                run.files["clock_schedule_ref"], "bound original clock schedule"
            ),
        },
        "verification": {
            **verdicts,
            "whole": all(verdict["pass"] for verdict in verdicts.values()),
        },
        "limits": list(_LIMITS),
    }


def load_neural_run(
    manifest_path: Path, *, registry: NeuralRegistry = REVIEWED_REGISTRY
) -> NeuralRunInputs:
    """Load and fully verify a public source-admitted neural acquisition.

    Parameters
    ----------
    manifest_path
        Public manifest in an immutable complete acquisition. The loader binds
        every required source, data, compiled object and receipt, verifies the
        actual source-owned checker, and computes all five independent verdicts.
    registry
        The consumer's own reviewed source entries; acquisition data never selects it.

    Returns
    -------
    NeuralRunInputs
        Immutable full-verification snapshot, including explicit known failures.

    Raises
    ------
    NeuralCaptureRefusalError
        If source admission, original file binding or grammar prevents interpretation.
    NeuralRunError
        If analysis fails unexpectedly; its diagnostic contains no interpreter details.
    """
    try:
        run = bind_public_neural_run(manifest_path, registry=registry)
        report = _analyse(run)
        inputs = object.__new__(NeuralRunInputs)
        object.__setattr__(inputs, "directory", run.directory)
        object.__setattr__(inputs, "manifest_bytes", run.manifest_bytes)
        object.__setattr__(inputs, "report_bytes", canonical_json_bytes(report))
        object.__setattr__(inputs, "_loader_origin", _INPUT_SEAL)
    except NeuralCaptureRefusalError:
        raise
    except JsonInputRefusalError as exc:
        # The native verifier names only the refused document, never decoder detail.
        message = f"Invalid original {exc.source}."
        raise NeuralCaptureRefusalError(message) from exc
    except OSError as exc:
        message = "Cannot bind the complete public neural acquisition."
        raise NeuralCaptureRefusalError(message) from exc
    except Exception as exc:
        message = "Neural run analysis failed."
        raise NeuralRunError(message) from exc
    else:
        return inputs


def build_neural_run_report(inputs: object) -> dict[str, Any]:
    """Return a fresh report from the exact full-verification loader snapshot.

    Parameters
    ----------
    inputs
        Immutable object returned by ``load_neural_run``. Declaration readers,
        partial capture envelopes and caller-created objects are not accepted.

    Returns
    -------
    dict[str, Any]
        Independent source/capture/numerical/completion/clock verdicts and their
        whole conjunction, without re-reading inputs or repeating checker jobs.

    Raises
    ------
    NeuralCaptureRefusalError
        If inputs did not originate from the complete public loader.
    """
    if (
        not isinstance(inputs, NeuralRunInputs)
        or getattr(inputs, "_loader_origin", None) is not _INPUT_SEAL
    ):
        message = "Neural reports require the complete public run loader snapshot."
        raise NeuralCaptureRefusalError(message)
    return parse_json_object(inputs.report_bytes, "complete neural report")
