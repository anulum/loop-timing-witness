# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — completed native metadata public API custody

"""Validate metadata refusal and real artifact receipts after an actual RTL run."""

from __future__ import annotations

import hashlib
import json
import subprocess
from typing import TYPE_CHECKING

import pytest
from jsonschema import Draft202012Validator
from test_native_lifecycle_api import lifecycle_program
from test_native_run import configuration

from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["lifecycle_program"]


@pytest.mark.parametrize("scenario", ["zero", "fault"])
def test_completed_metadata_api(lifecycle_program: Path, tmp_path: Path, scenario: str) -> None:
    """Refuse invalid public configuration before creating a receipt and retain actual data.

    Parameters
    ----------
    lifecycle_program
        Public API corpus linked to the production RTL and native controller.
    tmp_path
        Exclusive configuration, event, trace and metadata allocation.
    scenario
        Zero cycle count or out-of-range fault enum in the metadata configuration.
    """
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none").replace("pid 32", "pid 2"), encoding="utf-8")
    events, raw = tmp_path / "events.bin", tmp_path / "raw.csv"
    result = subprocess.run(
        [str(lifecycle_program), f"metadata_{scenario}", str(config), str(events), str(raw)],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == f"verified metadata_{scenario}\n"
    assert result.stderr == ""
    receipt = json.loads(tmp_path.joinpath("events.bin.metadata.json").read_text())
    Draft202012Validator(
        json.loads((REPOSITORY_ROOT / "native-run.schema.json").read_text())
    ).validate(receipt)
    assert receipt["source_kind"] == "rtl_simulation"
    assert receipt["cycles"] == 2
    assert receipt["result"]["samples"] == 2
    assert receipt["result"]["records"] == 8
    assert receipt["result"]["misses"] == 0
    assert receipt["fault"]["kind"] == "none"
    assert events.stat().st_size == 8 * 16
    assert len(raw.read_text().splitlines()) == 3
    for role, path in {"configuration": config, "events": events, "tracking_raw": raw}.items():
        data = path.read_bytes()
        assert receipt["artifacts"][role] == {
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        }
