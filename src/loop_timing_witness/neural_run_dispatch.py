# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — exact neural schema dispatch for the existing analysis command

"""Route public neural carriers through full verification before legacy analysis."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from .manifest_io import JsonInputRefusalError, parse_json_object
from .neural_event_stream import NeuralCaptureRefusalError
from .neural_run_api import NeuralRunError, build_neural_run_report, load_neural_run
from .neural_run_files import read_run_dispatch_bytes
from .neural_run_policy import REVIEWED_REGISTRY
from .neural_run_publication import write_neural_report

if TYPE_CHECKING:
    from pathlib import Path

    from .neural_run_policy import NeuralRegistry


def dispatch_analysis(
    manifest_path: Path,
    output_directory: Path,
    *,
    registry: NeuralRegistry = REVIEWED_REGISTRY,
) -> tuple[int | None, bytes]:
    """Dispatch a finite strict root snapshot without treating neural data as legacy.

    Parameters
    ----------
    manifest_path
        Original caller-selected root passed to the existing analysis command.
    output_directory
        Exclusive report destination for a fully verified neural analysis.
    registry
        The consumer's own reviewed source entries; acquisition data never selects it.

    Returns
    -------
    tuple[int | None, bytes]
        Neural status zero, one or two, or ``None`` plus the complete unchanged
        root snapshot for the existing CONTROL/COMPUTE analysis path.
    """
    try:
        raw = read_run_dispatch_bytes(manifest_path)
        manifest = parse_json_object(raw, "analysis manifest")
    except (NeuralCaptureRefusalError, JsonInputRefusalError) as exc:
        print(
            f"run analysis: FAIL: A finite regular strict JSON manifest is required. {exc}",
            file=sys.stderr,
        )
        return 1, b""
    if "schema_id" not in manifest:
        return None, raw
    try:
        inputs = load_neural_run(manifest_path, registry=registry)
        report = build_neural_run_report(inputs)
        write_neural_report(output_directory, report)
    except NeuralCaptureRefusalError as exc:
        print(f"run analysis: FAIL: {exc}", file=sys.stderr)
        return 1, raw
    except (NeuralRunError, OSError):
        print("run analysis: FAIL: Neural analysis or report publication failed.", file=sys.stderr)
        return 1, raw
    passed = report["verification"]["whole"]
    print(f"run analysis: {'PASS' if passed else 'INVALID'}: {output_directory}")
    return (0 if passed else 2), raw
