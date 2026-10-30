# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — static source-checker contract binding

"""Bind the reviewed checker closure and runtime without interpreting executable selectors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .manifest_io import parse_json_object
from .neural_event_stream import NeuralCaptureRefusalError
from .neural_run_files import read_neural_run_file

if TYPE_CHECKING:
    from .neural_run_binding import BoundNeuralRun


def bind_checker_contract(run: BoundNeuralRun) -> dict[str, Any]:
    """Bind the complete static checker policy and selected installation contract.

    Parameters
    ----------
    run
        Fully source-admitted original acquisition and consumer registry entry.

    Returns
    -------
    dict[str, Any]
        Closed reviewed checker declarations, retaining their original file roles.

    Raises
    ------
    NeuralCaptureRefusalError
        If the checker closure, fixed arguments or complete runtime contract differs.
    """
    contract = run.contract
    raw = read_neural_run_file(
        run.directory,
        contract.policy["checker_policy_ref"],
        65536,
        expected_bytes=contract.checker_policy_bytes,
        mismatch_message="Acquired checker policy differs from its reviewed consumer binding.",
    )
    checker = parse_json_object(raw, "reviewed checker policy")
    fields = {
        "schema_id",
        "entry_point",
        "source_files",
        "runtime_contract_ref",
        "generate_arguments",
        "check_arguments",
        "execution_contract",
    }
    if (
        set(checker) != fields
        or checker["schema_id"] != "loop-timing-witness.sc-checker-policy.v1"
        or checker["generate_arguments"] != ["--generate", "--steps", "1000", "--seed", "42"]
        or checker["check_arguments"] != ["--check", "--steps", "1000", "--seed", "42"]
        or not isinstance(checker["source_files"], list)
        or not checker["source_files"]
        or checker["entry_point"] not in checker["source_files"]
    ):
        message = "Selected checker requires its complete closed fixed-operation policy."
        raise NeuralCaptureRefusalError(message)
    names = []
    for reference in checker["source_files"]:
        body = read_neural_run_file(run.directory, reference, 1048576)
        name = reference["path"]
        if run.sources.get(name) != body:
            message = "Checker source closure differs from the admitted whole source population."
            raise NeuralCaptureRefusalError(message)
        names.append(name)
    if len(set(names)) != len(names):
        message = "Selected checker source closure contains duplicate roles."
        raise NeuralCaptureRefusalError(message)
    expected = contract.installation.contract_bytes()
    runtime = read_neural_run_file(
        run.directory,
        checker["runtime_contract_ref"],
        1048576,
        expected_bytes=expected,
        mismatch_message=(
            "Acquired checker runtime differs from the complete selected installation."
        ),
    )
    if (
        checker["execution_contract"]
        != parse_json_object(expected, "consumer checker runtime")["execution_contract"]
    ):
        message = "Acquired checker runtime differs from the complete selected installation."
        raise NeuralCaptureRefusalError(message)
    run.files["checker_policy"] = raw
    run.files["checker_runtime_contract"] = runtime
    contract.installation.verify()
    return checker
