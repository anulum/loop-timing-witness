# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — native simulation manifest construction

"""Bind actual native configuration, raw observations and simulation source files."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Any

from host_load_receipt import validate_host_load
from jsonschema import Draft202012Validator
from native_tracking import decode_tracking

from manifest_io import canonical_json_bytes, load_json_object, sha256_of_file

ROOT = Path(__file__).resolve().parents[1]


def file_reference(run: Path, path: Path) -> dict[str, str]:
    """Return a relative name and digest for a captured regular artifact.

    Parameters
    ----------
    run
        Exact run directory.
    path
        Artifact within it.

    Returns
    -------
    dict of str to str
        Versioned manifest file reference.
    """
    return {"path": path.relative_to(run).as_posix(), "sha256": sha256_of_file(path)}


def native_metadata(run: Path) -> dict[str, Any]:
    """Validate native-produced facts before constructing a simulation declaration.

    Parameters
    ----------
    run
        Directory containing native_metadata.json.

    Returns
    -------
    dict of str to Any
        Valid configuration and completion facts from the executed program.

    Raises
    ------
    ValueError
        If fields, source kind or observed counts disagree with a simulation run.
    """
    metadata = load_json_object(run / "native_metadata.json")
    validator = Draft202012Validator(load_json_object(ROOT / "native-run.schema.json"))
    errors = list(validator.iter_errors(metadata))
    if errors:
        message = f"native metadata invalid: {errors[0].message}"
        raise ValueError(message)
    if metadata["source_kind"] != "rtl_simulation":
        message = "native simulation capture requires an actual RTL source"
        raise ValueError(message)
    if metadata["result"]["samples"] > metadata["cycles"]:
        message = "native sample count exceeds configured cycles"
        raise ValueError(message)
    for role, name in [("events", "events.bin"), ("tracking_raw", "tracking_raw.csv")]:
        content = (run / name).read_bytes()
        if metadata["artifacts"][role] != {
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
        }:
            message = f"native artifact digest differs: {role}"
            raise ValueError(message)
    return metadata


def convert_tracking(run: Path, metadata: dict[str, Any]) -> None:
    """Convert every actual raw Q8.24 observation exactly, preserving missing cycles.

    Parameters
    ----------
    run
        Raw native capture directory.
    metadata
        Native configuration and actual sample count.
    """
    content = (run / "tracking_raw.csv").read_bytes()
    if metadata["artifacts"]["tracking_raw"] != {
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
    }:
        message = "native raw tracking digest differs"
        raise ValueError(message)
    converted = decode_tracking(content, metadata["cycles"], metadata["result"]["samples"])
    with (run / "tracking.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["cycle", "reference", "output"])
        writer.writerows(converted)


def write_native_manifest(run: Path, started_utc: str, sources: list[Path], version: str) -> Path:
    """Write one hash-bound simulation manifest using native-produced configuration.

    Parameters
    ----------
    run
        Captured run and source snapshot directory.
    started_utc
        Actual UTC timestamp immediately before native execution.
    sources
        Snapshotted sources, executable and provenance records within the run.
    version
        Actual build tools' version record.

    Returns
    -------
    Path
        Exclusive new manifest path.
    """
    metadata = native_metadata(run)
    references = [file_reference(run, path) for path in sources]
    configuration_receipt = metadata["artifacts"]["configuration"]
    if not any(
        reference["sha256"] == configuration_receipt["sha256"]
        and path.stat().st_size == configuration_receipt["bytes"]
        for reference, path in zip(references, sources, strict=True)
    ):
        message = "native configuration digest is absent from captured source artifacts"
        raise ValueError(message)
    convert_tracking(run, metadata)
    fault = metadata["fault"]
    schedule = (
        []
        if fault["kind"] == "none"
        else [
            {
                "cycle": fault["cycle"],
                "kind": fault["kind"],
                "delay_periods": fault["duration_periods"] if fault["kind"] == "delay" else 0,
            }
        ]
    )
    manifest = {
        "schema": "loop-timing-witness.run-manifest.v1",
        "run_id": "native-" + started_utc.replace("-", "").replace(":", "").replace("+", "_"),
        "started_utc": started_utc,
        "source": {
            "kind": "rtl_simulation",
            "tool": "Verilator native run controller",
            "version": version,
            "files": references,
        },
        "measurement_domain": file_reference(run, run / "measurement-domain.json"),
        "native_metadata": file_reference(run, run / "native_metadata.json"),
        "profile": "CONTROL",
        "placement": "linux_user_space",
        "sample_period_ticks": metadata["period_ticks"],
        "cycle_count": metadata["cycles"],
        "warmup_cycles": 0,
        "tracking_sampling": "observed",
        "load_case": "modeled_overload"
        if metadata["overload"]["modeled_nanoseconds"]
        else "native_simulation",
        "controller": {"name": metadata["controller"], "coefficients": metadata["coefficients"]},
        "plant": {
            "name": "first_order_thermal" if metadata["thermal"] else "second_order_mechanical",
            "fixed_point_format": "Q8.24",
            "tracking_unit": "model_output",
        },
        "fault_schedule": schedule,
        "files": {
            "events": file_reference(run, run / "events.bin"),
            "tracking": file_reference(run, run / "tracking.csv"),
            "power": None,
        },
        "hardware_artifacts": None,
        "instrument": {
            "fifo_overflow_count": metadata["result"]["overflow"],
            "floor_ticks": None,
            "known_period_pass": False,
            "injected_delay_pass": False,
            "overflow_pass": False,
            "bus_offset_pass": False,
        },
        "environment": {"room_temperature_c": None, "board_supply_only": False},
        "operator_notes": "Native controller over production RTL. "
        "Host calculation does not advance "
        "simulation time. Reference, fault duration and work/delay are in hash-bound "
        "native_metadata.json. Only captured sample reads have tracking rows. "
        "No physical CPU timing, power or board acceptance.",
    }
    load_path = run / "host_load.json"
    if load_path.exists():
        load_receipt = validate_host_load(load_path.read_bytes())
        manifest["host_load"] = file_reference(run, load_path)
        manifest["load_case"] = load_receipt["profile"]
    path = run / "manifest.json"
    with path.open("xb") as stream:
        stream.write(canonical_json_bytes(manifest))
    return path
