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
from typing import TYPE_CHECKING, Any, cast

from jsonschema import Draft202012Validator

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
from .manifest_io import (
    canonical_json_bytes,
    load_bounded_json_object,
    load_json_object,
    parse_bounded_json_object,
    sha256_of_file,
)
from .run_manifest import load_run, utc_timestamp
from .validate_measurement_domain import schema_locations

if TYPE_CHECKING:
    from .amp_completion import AmpCompletion
    from .amp_contract import AmpRun

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
_REQUIRED_FILES = frozenset(
    {
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
    }
)
_IMAGE_DIGESTS = (
    ("firmware_sha256", "firmware.elf"),
    ("dtb_sha256", "platform.dtb"),
    ("configuration_sha256", "configuration.txt"),
    ("preparation_sha256", "preparation.json"),
)
_INSTRUMENT_FLAGS = {
    "floor_ticks": None,
    "known_period_pass": False,
    "injected_delay_pass": False,
    "overflow_pass": False,
    "bus_offset_pass": False,
}
_FIXED_RUN_FIELDS = {
    "profile": "CONTROL",
    "placement": "bare_metal_amp",
    "warmup_cycles": 0,
    "tracking_sampling": "observed",
    "load_case": "isa_simulation",
    "hardware_artifacts": None,
    "operator_notes": "Actual RV64 target execution and logger drain against production RTL. "
    "Explicit functional clock map; observed samples only. "
    "No physical U54 timing, power or board acceptance.",
}


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


def _capture_receipt(content: bytes) -> dict[str, Any]:
    """Decode a capture receipt and check its schema and its two UTC timestamps.

    Parameters
    ----------
    content
        Original capture bytes.

    Returns
    -------
    dict of str to Any
        Receipt whose shape and timestamps are valid; its artifacts are not checked yet.

    Raises
    ------
    ValueError
        If the bytes break the bounded JSON rules, the receipt breaks its schema, or a
        timestamp is not one RFC 3339 date-time in UTC.
    """
    capture = parse_bounded_json_object(content, "AMP capture")
    locations = schema_locations(capture, load_json_object(ROOT / "amp-capture.schema.json"))
    if locations:
        message = f"AMP capture receipt {locations[0]}: does not satisfy the AMP capture schema"
        raise ValueError(message)
    for field in ("started_utc", "completed_utc"):
        if not utc_timestamp(capture[field]):
            message = f"AMP capture receipt {field} must be an RFC 3339 date-time in UTC"
            raise ValueError(message)
    return capture


def _check_artifacts(output: Path, files: dict[str, str], record_count: int) -> None:
    """Require every original artifact identity and verify each listed file.

    Parameters
    ----------
    output
        Original exclusive capture directory.
    files
        Captured artifact digests keyed by capture-relative path.
    record_count
        Number of firmware preprocessing dependency records.

    Raises
    ------
    OSError
        If a captured original artifact is unavailable.
    ValueError
        If a required identity is absent, or a path leaves the capture or its
        bytes changed.
    """
    required = _REQUIRED_FILES | {
        f"image/precompile/input_{index}.d" for index in range(record_count)
    }
    if not required.issubset(files):
        message = "AMP capture lacks required original artifact identities"
        raise ValueError(message)
    root = output.resolve()
    for name, digest in files.items():
        path = output / name
        if (
            Path(name).is_absolute()
            or ".." in Path(name).parts
            or not path.resolve().is_relative_to(root)
            or sha256_of_file(path) != digest
        ):
            message = "AMP capture artifact bytes or paths changed"
            raise ValueError(message)


def _check_preparation(
    output: Path, files: dict[str, str], preparation: dict[str, Any], record_count: int
) -> None:
    """Compare the firmware preparation record with its preprocessing and input files.

    Parameters
    ----------
    output
        Original exclusive capture directory.
    files
        Captured artifact digests keyed by capture-relative path.
    preparation
        Original firmware preparation record.
    record_count
        Number of firmware preprocessing dependency records.

    Raises
    ------
    OSError
        If a preprocessing record is unavailable.
    ValueError
        If the dependency records or the preparation inputs disagree.
    """
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
        or any(files.get("image/" + name) != digest for name, digest in inputs.items())
    ):
        message = "AMP original firmware preparation input identities disagree"
        raise ValueError(message)


def _identities_agree(
    capture: dict[str, Any],
    command: dict[str, Any],
    image: dict[str, Any],
    preparation: dict[str, Any],
) -> bool:
    """Tell whether the command, runtime, toolchain and image digests all agree.

    Parameters
    ----------
    capture, command, image, preparation
        Original capture receipt, command record, image record and preparation record.

    Returns
    -------
    bool
        Whether tools and runtime match the command, the runtime is the captured
        simulator, the image keeps the preparation toolchain and dependencies, and
        every image digest is the captured one.
    """
    return not (
        command.get("tools") != capture["tools"]
        or command.get("runtime") != capture["runtime"]
        or capture["runtime"]["sha256"] != capture["tools"]["spike"]
        or image.get("toolchain") != preparation.get("toolchain")
        or image.get("compiler_dependencies") != preparation.get("compiler_dependencies")
        or any(
            image.get(field) != capture["files"]["image/" + name] for field, name in _IMAGE_DIGESTS
        )
    )


def _check_logged_run(
    output: Path,
    capture: dict[str, Any],
    image: dict[str, Any],
    preparation: dict[str, Any],
    libraries: dict[str, str],
) -> None:
    """Verify the runtime, image and plugin snapshots and the logger's own completion.

    Parameters
    ----------
    output
        Original exclusive capture directory.
    capture, image, preparation
        Original capture receipt, image record and preparation record.
    libraries
        Admitted compiler runtime libraries.

    Raises
    ------
    OSError
        If a captured original artifact is unavailable.
    ValueError
        If a snapshot differs, the declared completion differs from the logger, or
        the captured events and tracking contradict the completion.
    """
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
        If original receipt shape, UTC timestamps, paths, byte hashes or actual logger
        counters disagree.
    """
    capture = _capture_receipt(content)
    preparation = load_bounded_json_object(output / "image/preparation.json")
    record_count = image_dependency_record_count(preparation)
    _check_artifacts(output, capture["files"], record_count)
    command = load_bounded_json_object(output / "command.json")
    image = load_bounded_json_object(output / "image/image.json")
    libraries = compiler_libraries(preparation.get("toolchain"))
    _check_preparation(output, capture["files"], preparation, record_count)
    if not _identities_agree(capture, command, image, preparation):
        message = "AMP capture tool or verified image identities disagree"
        raise ValueError(message)
    _check_logged_run(output, capture, image, preparation, libraries)
    return capture


def _identity_fields(capture: dict[str, Any], receipt_sha256: str) -> dict[str, Any]:
    """Return the manifest fields naming the run and its bound source files.

    Parameters
    ----------
    capture
        Admitted capture receipt.
    receipt_sha256
        Digest of the original capture receipt file.

    Returns
    -------
    dict[str, Any]
        Schema, run identity, start time, source, measurement domain and receipt.
    """
    return {
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
            "files": [
                {"path": name, "sha256": digest} for name, digest in capture["files"].items()
            ],
        },
        "measurement_domain": {
            "path": "measurement-domain.json",
            "sha256": capture["files"]["measurement-domain.json"],
        },
        "amp_capture": {"path": "capture.json", "sha256": receipt_sha256},
    }


def _run_fields(
    capture: dict[str, Any],
    completion: AmpCompletion,
    run: AmpRun,
    configuration: bytes,
    tracking_sha256: str,
) -> dict[str, Any]:
    """Return the manifest fields describing the run's control, plant and files.

    Parameters
    ----------
    capture
        Admitted capture receipt.
    completion, run
        Logger completion receipt and decoded run configuration.
    configuration
        Original run configuration bytes.
    tracking_sha256
        Digest of the generated observed tracking file.

    Returns
    -------
    dict[str, Any]
        Profile, placement, timing, controller, plant, faults, files, instrument,
        environment and operator notes.
    """
    return {
        **_FIXED_RUN_FIELDS,
        "sample_period_ticks": run.period_ticks,
        "cycle_count": run.cycles,
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
            "tracking": {"path": "tracking.csv", "sha256": tracking_sha256},
            "power": None,
        },
        "instrument": {"fifo_overflow_count": completion.overflow, **_INSTRUMENT_FLAGS},
        "environment": {"room_temperature_c": None, "board_supply_only": False},
    }


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
    receipt_sha256 = sha256_of_file(output / "capture.json")
    tracking_sha256 = sha256_of_file(output / "tracking.csv")
    manifest = {
        **_identity_fields(capture, receipt_sha256),
        **_run_fields(capture, completion, run, configuration, tracking_sha256),
    }
    path = output / "manifest.json"
    with path.open("xb") as stream:
        stream.write(canonical_json_bytes(manifest))
    load_run(path)
    return path
