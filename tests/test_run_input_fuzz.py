# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — differential mutation fuzzing of the run input readers

"""Mutate real run inputs and require one outcome from the Python and Rust analyses.

Each case starts from a real Icarus capture, changes one bound input (the binary events, the
tracking or power series, the measurement domain or the manifest itself) with seeded byte and
text mutations, declares the changed bytes' digest so they reach the readers, and loads the run
through both analyses. Both must give the same inputs, events, summary and report, or the same
refusal; any other exception or a native failure fails the case. ``WITNESS_FUZZ_CASES`` and
``WITNESS_FUZZ_SEED`` set the number of cases per profile and the seed (defaults 40 and
``20261120``); ``WITNESS_FUZZ_ARTIFACTS`` names a directory that receives the inputs of a case
whose outcomes differ.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest
from control_rust_support import canonical, python_outcome, rust_outcome
from test_control_run_parity import _bind
from test_control_series_corpus import _Values

if TYPE_CHECKING:
    from collections.abc import Callable

    MakeRtlRun = Callable[..., tuple[Path, dict[str, Any]]]

CASES: Final = int(os.environ.get("WITNESS_FUZZ_CASES", "40"))
SEED: Final = os.environ.get("WITNESS_FUZZ_SEED", "20261120")
TOKENS: Final = (
    b"\x00",
    b"\xff",
    b"\xc3",
    b",",
    b"\n",
    b"\r\n",
    b'"',
    b"-",
    b"-0",
    b"e999",
    b"1e-999",
    b"NaN",
    b"Infinity",
    b"\xc2\xa0",
    b"1" * 400,
    b"0" * 5000 + b"1",
    b"18446744073709551616",
    b"{}",
    b"[]",
    b"null",
    b'"a":1,',
)
NUMBER: Final = re.compile(rb"-?\d+(?:\.\d+)?")


def _mutate(data: bytes, generator: _Values) -> bytes:
    """Apply one to three seeded mutations to a byte string.

    Parameters
    ----------
    data
        Original bytes.
    generator
        Seeded value source.

    Returns
    -------
    bytes
        Mutated bytes.
    """
    for _ in range(generator.randint(1, 3)):
        kind = generator.choice(
            ["flip", "delete", "duplicate", "insert", "truncate", "lines", "number"]
            if data
            else ["insert"]
        )
        start = generator.randint(0, len(data))
        span = generator.randint(1, 32)
        if kind == "flip" and start < len(data):
            changed = bytearray(data)
            changed[start] ^= 1 << generator.randint(0, 7)
            data = bytes(changed)
        elif kind == "delete":
            data = data[:start] + data[start + span :]
        elif kind == "duplicate":
            data = data[: start + span] + data[start : start + span] + data[start + span :]
        elif kind == "truncate":
            data = data[:start]
        elif kind == "lines" and data.count(b"\n") > 1:
            lines = data.split(b"\n")
            first = generator.randint(0, len(lines) - 1)
            second = (first + generator.randint(1, len(lines) - 1)) % len(lines)
            lines[first], lines[second] = lines[second], lines[first]
            data = b"\n".join(lines)
        elif kind == "number" and (numbers := list(NUMBER.finditer(data))):
            match = generator.choice(numbers)
            data = data[: match.start()] + generator.choice(TOKENS) + data[match.end() :]
        else:
            data = data[:start] + generator.choice(TOKENS) + data[start:]
    return data


def _targets(manifest: dict[str, Any]) -> list[str]:
    """Return the inputs a case may change.

    Parameters
    ----------
    manifest
        Run declaration.

    Returns
    -------
    list[str]
        ``manifest``, ``measurement_domain`` and every file role the run declares.
    """
    declared = [role for role, item in manifest["files"].items() if item is not None]
    return ["manifest", "measurement_domain", *sorted(declared)]


def _keep(run: Path, label: str) -> None:
    """Copy a failing case's inputs to ``WITNESS_FUZZ_ARTIFACTS`` when it is set.

    Parameters
    ----------
    run
        Run directory with the mutated inputs.
    label
        Profile, seed, case and target of the case.
    """
    artifacts = os.environ.get("WITNESS_FUZZ_ARTIFACTS")
    if artifacts:
        name = re.sub(r"[^A-Za-z0-9_-]+", "-", label).strip("-")
        shutil.copytree(run, Path(artifacts) / name)


@pytest.mark.parametrize("profile", ["CONTROL", "COMPUTE"])
def test_mutated_run_inputs_have_one_outcome(
    profile: str, make_rtl_run: MakeRtlRun, tmp_path: Path
) -> None:
    """Every mutated run loads to the same outcome in Python and Rust.

    Parameters
    ----------
    profile
        Event profile of the capture.
    make_rtl_run
        Real Icarus capture with its manifest.
    tmp_path
        Owned outcome directories.
    """
    run, manifest = make_rtl_run(profile)
    pristine = {path: path.read_bytes() for path in run.iterdir() if path.is_file()}
    targets = _targets(manifest)
    refused = 0
    for case in range(CASES):
        generator = _Values(f"{SEED}-{profile}-{case}")
        for path, content in pristine.items():
            path.write_bytes(content)
        changed = json.loads(json.dumps(manifest))
        target = generator.choice(targets)
        manifest_path = run / "manifest.json"
        if target == "manifest":
            manifest_path.write_bytes(_mutate(json.dumps(changed).encode(), generator))
        else:
            item = changed[target] if target == "measurement_domain" else changed["files"][target]
            _bind(run, changed, target, _mutate((run / item["path"]).read_bytes(), generator))
            manifest_path.write_text(json.dumps(changed), encoding="utf-8")
        label = f"{profile} seed {SEED} case {case} ({target})"
        try:
            python = python_outcome(manifest_path)
            native = rust_outcome(manifest_path, tmp_path / f"outcome-{case}")
        except BaseException:
            _keep(run, label)
            raise
        if canonical(native) != canonical(python):
            _keep(run, label)
            pytest.fail(f"{label}: outcomes differ")
        refused += "refusal" in python or python.get("report_refusal") is not None
    assert 0 < refused < CASES or CASES == 0
