# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — observed dedicated-hart capture to run-analysis manifest

"""Bind original AMP inputs and observed raw streams to the public run-analysis contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker

from .amp_capture_observations import fault_schedule, tracking_csv
from .amp_completion import completion_receipt, decode_completion, validate_capture
from .amp_image_dependencies import (
    image_dependency_record_count,
    validate_image_dependency_snapshot,
)
from .amp_image_receipt import validate_image_receipt
from .amp_plugin_snapshot import validate_plugin_snapshot
from .amp_run_input import read_amp_run
from .amp_runtime_snapshot import validate_runtime_snapshot
from .manifest_io import canonical_json_bytes, load_json_object, parse_json_object, sha256_of_file
from .run_manifest import load_run

ROOT = Path(__file__).resolve().parent / "data"
COEFFICIENT_NAMES = (
    "kp",
    "ki_period",
    "derivative_decay",
    "derivative_gain",
    "position_gain",
    "velocity_gain",
    "reference_gain",
    "output_min",
    "output_max",
    "integral_min",
    "integral_max",
)


def compiler_libraries(identity: object) -> dict[str, str]:
    """Require complete original C compiler metadata before admitting captured runtime libraries.

    Parameters
    ----------
    identity
        Original compiler identity retained by firmware preparation and verification.

    Returns
    -------
    dict of str to str
        Original absolute runtime library paths and hashes after closed compiler-schema admission.

    Raises
    ------
    ValueError
        If the original driver, subprograms, version or library identity is incomplete or invalid.
    """
    schema = load_json_object(ROOT / "amp-plugin-build.schema.json")
    compiler = {
        "$defs": schema["$defs"],
        **schema["properties"]["compilers"]["properties"]["c"],
    }
    if not Draft202012Validator(compiler).is_valid(identity):
        message = "AMP captured original compiler identity is invalid"
        raise ValueError(message)
    data = cast("dict[str, Any]", identity)
    return cast("dict[str, str]", data["runtime_libraries"])


def admitted_capture(output: Path, content: bytes) -> dict[str, Any]:
    """Validate the original logger receipt schema and every captured artifact identity.

    Parameters
    ----------
    output
        Original exclusive capture directory containing capture.json.
    content
        Original capture bytes, already hash-bound when called from the public run loader.

    Returns
    -------
    dict of str to Any
        Capture receipt after schema, complete artifact and actual logger cross-checks.

    Raises
    ------
    OSError
        If a captured original artifact is unavailable.
    ValueError
        If original receipt shape, paths, byte hashes or actual logger counters disagree.
    """
    capture = parse_json_object(content, "AMP capture")
    schema = load_json_object(ROOT / "amp-capture.schema.json")
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(capture))
    if errors:
        message = f"AMP capture receipt invalid: {errors[0].message}"
        raise ValueError(message)
    preparation = load_json_object(output / "image/preparation.json")
    record_count = image_dependency_record_count(preparation)
    required = {
        "image/firmware.elf",
        "image/platform.dtb",
        "image/configuration.txt",
        "image/image.json",
        "events.bin",
        "tracking_raw.csv",
        "spike.log",
        "measurement-domain.json",
        "command.json",
        "plugin_build.json",
        "plugin_source_index.json",
        "runtime_source_index.json",
        "image/runtime_source_index.json",
        "image/preparation.json",
        "image/compiler_source_index.json",
        "image/build_commands.json",
        *(f"image/precompile/input_{index}.d" for index in range(record_count)),
    }
    if not required.issubset(capture["files"]):
        message = "AMP capture lacks required original artifact identities"
        raise ValueError(message)
    root = output.resolve()
    for name, digest in capture["files"].items():
        path = output / name
        if (
            Path(name).is_absolute()
            or ".." in Path(name).parts
            or not path.resolve().is_relative_to(root)
            or sha256_of_file(path) != digest
        ):
            message = "AMP capture artifact bytes or paths changed"
            raise ValueError(message)
    command = load_json_object(output / "command.json")
    image = load_json_object(output / "image/image.json")
    libraries = compiler_libraries(preparation.get("toolchain"))
    records = {
        f"precompile/input_{index}.d": sha256_of_file(
            output / "image/precompile" / f"input_{index}.d"
        )
        for index in range(record_count)
    }
    if preparation.get("dependency_records") != records:
        message = "AMP original firmware preprocessing record identities disagree"
        raise ValueError(message)
    inputs = preparation.get("inputs")
    if (
        not isinstance(inputs, dict)
        or not inputs
        or any(capture["files"].get("image/" + name) != digest for name, digest in inputs.items())
    ):
        message = "AMP original firmware preparation input identities disagree"
        raise ValueError(message)
    if (
        command.get("tools") != capture["tools"]
        or command.get("runtime") != capture["runtime"]
        or capture["runtime"]["sha256"] != capture["tools"]["spike"]
        or image.get("toolchain") != preparation.get("toolchain")
        or image.get("compiler_dependencies") != preparation.get("compiler_dependencies")
        or any(
            image.get(field) != capture["files"]["image/" + name]
            for field, name in (
                ("firmware_sha256", "firmware.elf"),
                ("dtb_sha256", "platform.dtb"),
                ("configuration_sha256", "configuration.txt"),
                ("preparation_sha256", "preparation.json"),
            )
        )
    ):
        message = "AMP capture tool or verified image identities disagree"
        raise ValueError(message)
    validate_runtime_snapshot(output, capture["runtime"]["runtime_libraries"])
    validate_runtime_snapshot(output / "image", libraries)
    validate_image_dependency_snapshot(output / "image", preparation.get("compiler_dependencies"))
    validate_image_receipt(output / "image", image, preparation)
    completion = completion_receipt((output / "spike.log").read_bytes())
    declared = decode_completion(canonical_json_bytes(capture["completion"]))
    if completion != declared:
        message = "AMP capture completion differs from the actual logger"
        raise ValueError(message)
    validate_plugin_snapshot(output, capture["tools"]["plugin"], thermal=completion.thermal)
    run = read_amp_run((output / "image/configuration.txt").read_bytes())
    validate_capture(
        completion,
        (output / "events.bin").read_bytes(),
        (output / "tracking_raw.csv").read_bytes(),
        (output / "measurement-domain.json").read_bytes(),
        run.cycles,
    )
    return capture


def write_amp_manifest(output: Path) -> Path:
    """Generate observed tracking and one source-bound public manifest from an actual ISA run.

    Parameters
    ----------
    output
        Complete original capture with admitted source and logger receipt.

    Returns
    -------
    Path
        New public run manifest accepted by the normal hash-bound run loader.

    Raises
    ------
    OSError
        If captured inputs or exclusive new analysis inputs cannot be accessed.
    ValueError
        If actual receipt, input configuration or resulting run declaration contradicts admission.
    """
    capture = admitted_capture(output, (output / "capture.json").read_bytes())
    completion = completion_receipt((output / "spike.log").read_bytes())
    configuration = (output / "image/configuration.txt").read_bytes()
    run = read_amp_run(configuration)
    observations = tracking_csv(
        (output / "tracking_raw.csv").read_bytes(), run.cycles, completion.samples
    )
    with (output / "tracking.csv").open("xb") as stream:
        stream.write(observations)
    references = [{"path": name, "sha256": digest} for name, digest in capture["files"].items()]
    receipt = {"path": "capture.json", "sha256": sha256_of_file(output / "capture.json")}
    manifest = {
        "schema": "loop-timing-witness.run-manifest.v1",
        "run_id": "amp-"
        + capture["started_utc"].replace("-", "").replace(":", "").replace("+", "_"),
        "started_utc": capture["started_utc"],
        "source": {
            "kind": "rtl_simulation",
            "tool": "Spike dedicated-hart controller over production RTL",
            "version": "spike-sha256="
            + capture["tools"]["spike"]
            + ";plugin-sha256="
            + capture["tools"]["plugin"],
            "files": references,
        },
        "measurement_domain": {
            "path": "measurement-domain.json",
            "sha256": capture["files"]["measurement-domain.json"],
        },
        "amp_capture": receipt,
        "profile": "CONTROL",
        "placement": "bare_metal_amp",
        "sample_period_ticks": run.period_ticks,
        "cycle_count": run.cycles,
        "warmup_cycles": 0,
        "tracking_sampling": "observed",
        "load_case": "isa_simulation",
        "controller": {
            "name": "lqr" if run.lqr else "pid",
            "coefficients": dict(zip(COEFFICIENT_NAMES, run.coefficients, strict=True)),
        },
        "plant": {
            "name": "first_order_thermal" if completion.thermal else "second_order_mechanical",
            "fixed_point_format": "Q8.24",
            "tracking_unit": "model_output",
        },
        "fault_schedule": fault_schedule(configuration),
        "files": {
            "events": {"path": "events.bin", "sha256": capture["files"]["events.bin"]},
            "tracking": {"path": "tracking.csv", "sha256": sha256_of_file(output / "tracking.csv")},
            "power": None,
        },
        "hardware_artifacts": None,
        "instrument": {
            "fifo_overflow_count": completion.overflow,
            "floor_ticks": None,
            "known_period_pass": False,
            "injected_delay_pass": False,
            "overflow_pass": False,
            "bus_offset_pass": False,
        },
        "environment": {"room_temperature_c": None, "board_supply_only": False},
        "operator_notes": "Actual RV64 target execution and logger drain against production RTL. "
        "Explicit functional clock map; observed samples only. "
        "No physical U54 timing, power or board acceptance.",
    }
    path = output / "manifest.json"
    with path.open("xb") as stream:
        stream.write(canonical_json_bytes(manifest))
    load_run(path)
    return path
