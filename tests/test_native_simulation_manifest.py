# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — native metadata and raw trace validation

"""Validate actual native-produced metadata and refuse corrupted imports."""

from __future__ import annotations

import hashlib
import json
import subprocess
from typing import TYPE_CHECKING

import pytest
from native_simulation_manifest import convert_tracking, native_metadata, write_native_manifest
from test_native_run import configuration, native_run

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["native_run"]


@pytest.fixture
def native_capture(native_run: Path, tmp_path: Path) -> Path:
    """Capture an actual native run before any deliberate corruption.

    Parameters
    ----------
    native_run
        Production binary linked to the actual plant.
    tmp_path
        Exclusive configuration and output storage.

    Returns
    -------
    Path
        Completed native capture directory.
    """
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none"), encoding="utf-8")
    result = subprocess.run(
        [
            str(native_run),
            str(config),
            str(tmp_path / "events.bin"),
            str(tmp_path / "tracking_raw.csv"),
            "--metadata",
            str(tmp_path / "native_metadata.json"),
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return tmp_path


@pytest.mark.parametrize(
    "corruption", ["source", "samples", "schema", "event_digest", "power_source"]
)
def test_native_receipt_refusal(native_capture: Path, corruption: str) -> None:
    """Refuse inconsistent source claims, schema values and changed actual event bytes.

    Parameters
    ----------
    native_capture
        Completed actual native capture.
    corruption
        Deliberate negative-case mutation of the capture.
    """
    metadata_path = native_capture / "native_metadata.json"
    facts = json.loads(metadata_path.read_text())
    mutations = {
        "source": {"source_kind": "uio_unqualified"},
        "samples": {"result": {**facts["result"], "samples": 33}},
        "schema": {"result": {**facts["result"], "overflow": -1}},
        "power_source": {
            "artifacts": {
                **facts["artifacts"],
                "power_configuration": facts["artifacts"]["configuration"],
                "power_journal": facts["artifacts"]["tracking_raw"],
            }
        },
    }
    if corruption == "event_digest":
        events = native_capture / "events.bin"
        content = events.read_bytes()
        events.write_bytes(content[:-1] + bytes([content[-1] ^ 1]))
    else:
        facts.update(mutations[corruption])
    metadata_path.write_text(json.dumps(facts), encoding="utf-8")
    with pytest.raises(ValueError, match="native"):
        native_metadata(native_capture)


@pytest.mark.parametrize(
    "corruption", ["none", "raw_count", "raw_bound", "raw_header", "raw_digest"]
)
def test_native_import(native_capture: Path, corruption: str) -> None:
    """Import actual raw rows and reject corruption even when malformed rows are rehashed.

    Parameters
    ----------
    native_capture
        Completed actual native capture.
    corruption
        Deliberate negative-case mutation or none.
    """
    metadata = native_metadata(native_capture)
    raw = native_capture / "tracking_raw.csv"
    lines = raw.read_text().splitlines()
    if corruption == "raw_count":
        raw.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    elif corruption == "raw_bound":
        fields = lines[1].split(",")
        fields[1] = str(1 << 31)
        lines[1] = ",".join(fields)
        raw.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif corruption == "raw_header":
        raw.write_text("wrong\n", encoding="utf-8")
    elif corruption == "raw_digest":
        raw.write_text(raw.read_text() + "\n", encoding="utf-8")
    if corruption in {"raw_count", "raw_bound", "raw_header"}:
        content = raw.read_bytes()
        metadata["artifacts"]["tracking_raw"] = {
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
        }
    if corruption != "none":
        expected = "native raw tracking digest" if corruption == "raw_digest" else "native"
        with pytest.raises(ValueError, match=expected):
            convert_tracking(native_capture, metadata)
        assert not (native_capture / "tracking.csv").exists()
    else:
        convert_tracking(native_capture, metadata)
        assert len((native_capture / "tracking.csv").read_text().splitlines()) == 33
        with pytest.raises(FileExistsError):
            convert_tracking(native_capture, metadata)


@pytest.mark.parametrize("field", ["sha256", "bytes"])
def test_configuration_receipt_refusal(native_capture: Path, field: str) -> None:
    """Refuse a receipt whose original configuration is absent from captured artifacts.

    Parameters
    ----------
    native_capture
        Completed actual native capture.
    field
        Deliberately corrupted configuration receipt field.
    """
    metadata_path = native_capture / "native_metadata.json"
    facts = json.loads(metadata_path.read_text())
    receipt = facts["artifacts"]["configuration"]
    receipt[field] = "0" * 64 if field == "sha256" else receipt["bytes"] + 1
    metadata_path.write_text(json.dumps(facts), encoding="utf-8")
    version = subprocess.run(
        ["verilator", "--version"], capture_output=True, text=True, timeout=10, check=True
    ).stdout.strip()
    with pytest.raises(ValueError, match="native configuration digest is absent"):
        write_native_manifest(
            native_capture, "2026-09-27T00:00:00Z", [native_capture / "run.conf"], version
        )
    assert not (native_capture / "manifest.json").exists()
    assert not (native_capture / "tracking.csv").exists()
