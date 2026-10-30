# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — public neural manifest input controls

"""Exercise carrier grammar on declarations from an actual private native acquisition."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from loop_timing_witness import load_neural_run
from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError
from loop_timing_witness.neural_run_manifest import decode_neural_manifest, load_neural_manifest

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_SHA256 = "c5397e9146741b23a9e85f686d0e47b5bbc1dafb8e0f1c70df92c999e6c13315"


def _declaration() -> dict[str, Any]:
    """Derive prospective declarations without adopting or rewriting acquired data.

    Returns
    -------
    dict[str, Any]
        Actual private acquisition declarations with prospective carrier identity
        and its still-private source-policy reference. No public run is acquired.
    """
    raw = (ROOT / "tests/data/neural-native-original.run.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == ORIGINAL_SHA256
    value: dict[str, Any] = json.loads(raw)
    value["schema_id"] = "loop-timing-witness.neural-step-run.v1"
    value["native_source_cohort"] = "sc-neurocore-neural-step-1n1b16t.v1"
    value["source_contract_ref"] = {
        "path": "native_cohort_policy.json",
        "sha256": "f1e44f86fee1a20c75e8990acb65e66652138e09cd6c4dc545815431d50127dc",
        "byte_length": 10570,
    }
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    """Write one input control without changing the retained acquisition fixture.

    Parameters
    ----------
    path
        Task-owned input control.
    value
        Prospective declarations or one deliberately invalid variant.
    """
    path.write_text(json.dumps(value), encoding="utf-8")


def test_actual_private_identity_is_refused_and_shape_does_not_bind_sources(tmp_path: Path) -> None:
    """Keep actual private acquisition distinct from prospective public declarations.

    Parameters
    ----------
    tmp_path
        Empty directory without any acquired source, trace or runtime bodies.
    """
    path = tmp_path / "run.json"
    original = (ROOT / "tests/data/neural-native-original.run.json").read_bytes()
    path.write_bytes(original)
    with pytest.raises(NeuralCaptureRefusalError, match="closed schema"):
        load_neural_manifest(path)
    value = _declaration()
    _write(path, value)
    assert load_neural_manifest(path) == value
    assert not (tmp_path / "native_cohort_policy.json").exists()
    assert path.read_bytes() != original
    assert hashlib.sha256(original).hexdigest() == ORIGINAL_SHA256
    assert (ROOT / "neural-step-run.schema.json").read_bytes() == (
        ROOT / "src/loop_timing_witness/data/neural-step-run.schema.json"
    ).read_bytes()


@pytest.mark.parametrize("field", ["step_count", "encoder_id_width", "epoch", "extra"])
def test_exact_numbers_and_closed_root_are_required(tmp_path: Path, field: str) -> None:
    """Refuse decimal numeric encodings, bool counts and unknown root members.

    Parameters
    ----------
    tmp_path
        Input allocation containing a derived actual acquisition declaration.
    field
        Numeric or additional field whose grammar is deliberately contradicted.
    """
    path = tmp_path / "run.json"
    value = _declaration()
    value[field] = True if field == "encoder_id_width" else 0 if field == "extra" else 1.0
    _write(path, value)
    with pytest.raises(NeuralCaptureRefusalError, match="closed schema or exact integer"):
        load_neural_manifest(path)
    value = _declaration()
    value["event_codes"]["input_step_applied"] = 14.0
    _write(path, value)
    with pytest.raises(NeuralCaptureRefusalError, match="exact integer"):
        load_neural_manifest(path)


@pytest.mark.parametrize(
    "location",
    [
        (),
        ("sc_body_pins",),
        ("event_codes",),
        ("completion",),
        ("tool_receipt",),
        ("input_trace",),
        ("numerical_trace",),
        ("numerical_projection",),
        ("reference_projection",),
        ("service_trace",),
        ("clock_schedule_ref",),
        ("source_contract_ref",),
        ("source_files", 0),
        *(("channels", index) for index in range(3)),
        *(
            ("channels", index, role)
            for index in range(3)
            for role in ("capture", "payload", "markers")
        ),
    ],
)
def test_positional_arrays_cannot_replace_schema_objects(
    tmp_path: Path, location: tuple[str | int, ...]
) -> None:
    """Retain object-kind parity with the native positional-structure regression.

    Parameters
    ----------
    tmp_path
        Owned JSON input derived from the actual acquisition declaration.
    location
        Root or nested schema object replaced with its positional values.
    """
    declaration = _declaration()
    control: object
    if location:
        parent: Any = declaration
        for component in location[:-1]:
            parent = parent[component]
        selected = parent[location[-1]]
        parent[location[-1]] = list(selected.values())
        control = declaration
    else:
        control = list(declaration.values())
    raw = json.dumps(control).encode("utf-8")
    path = tmp_path / "positional.json"
    path.write_bytes(raw)
    message = "closed schema" if location else "strict UTF-8 JSON object"
    with pytest.raises(NeuralCaptureRefusalError, match=message):
        decode_neural_manifest(raw)
    with pytest.raises(NeuralCaptureRefusalError, match=message):
        load_neural_manifest(path)


@pytest.mark.parametrize("content", [b"[]", b"{", b"\xff", b'{"x":0,"x":1}', b'{"x":NaN}'])
def test_malformed_input_uses_authored_refusal(tmp_path: Path, content: bytes) -> None:
    """Refuse actual malformed input without exposing decoder exception text.

    Parameters
    ----------
    tmp_path
        Task-owned malformed input directory.
    content
        Complete invalid JSON bytes supplied through the real reader.
    """
    path = tmp_path / "run.json"
    path.write_bytes(content)
    with pytest.raises(NeuralCaptureRefusalError, match=r"^Neural manifest must contain"):
        load_neural_manifest(path)


@pytest.mark.parametrize("kind", ["absent", "directory", "symlink", "fifo", "oversized"])
def test_manifest_file_kind_and_size_are_bounded(tmp_path: Path, kind: str) -> None:
    """Refuse filesystem inputs before reading an unbounded or blocking stream.

    Parameters
    ----------
    tmp_path
        Real Linux files, symlink, directory and FIFO control allocation.
    kind
        Unsupported filesystem object or excessive complete byte population.
    """
    path = tmp_path / "run.json"
    if kind == "directory":
        path.mkdir()
    elif kind == "symlink":
        target = tmp_path / "original.json"
        _write(target, _declaration())
        path.symlink_to(target)
    elif kind == "fifo":
        os.mkfifo(path)
    elif kind == "oversized":
        path.write_bytes(b" " * 65537)
    with pytest.raises(NeuralCaptureRefusalError):
        load_neural_manifest(path)


@pytest.mark.parametrize(
    "name", ["/absolute", "../escape", "a//b", "a/./b", "a\\b", "a:b", ".", "a" * 4097]
)
def test_portable_paths_and_reference_allocations_are_required(tmp_path: Path, name: str) -> None:
    """Refuse escaped or ambiguous source paths and excessive referenced lengths.

    Parameters
    ----------
    tmp_path
        Derived acquisition declarations supplied through the real loader.
    name
        Invalid source reference path, tested without opening the named target.
    """
    path = tmp_path / "run.json"
    value = _declaration()
    value["source_files"][0]["path"] = name
    _write(path, value)
    with pytest.raises(NeuralCaptureRefusalError, match="portable within-run"):
        load_neural_manifest(path)
    value = _declaration()
    value["tool_receipt"]["byte_length"] = 65537
    _write(path, value)
    with pytest.raises(NeuralCaptureRefusalError, match="bounded portable"):
        load_neural_manifest(path)


def test_source_population_duplicates_and_nested_exact_lengths(tmp_path: Path) -> None:
    """Refuse repeated sources and decimal reference lengths within bounded input bytes.

    Parameters
    ----------
    tmp_path
        Complete original declarations with one controlled contradiction each.
    """
    path = tmp_path / "run.json"
    value = _declaration()
    value["source_files"].append(value["source_files"][0])
    _write(path, value)
    with pytest.raises(NeuralCaptureRefusalError, match="duplicate path"):
        load_neural_manifest(path)
    value["source_files"] *= 3
    _write(path, value)
    with pytest.raises(NeuralCaptureRefusalError, match="duplicate path"):
        load_neural_manifest(path)
    value = _declaration()
    value["channels"][0]["capture"]["byte_length"] = 1.0
    _write(path, value)
    with pytest.raises(NeuralCaptureRefusalError, match="exact integer"):
        load_neural_manifest(path)


def test_complete_source_population_uses_byte_bounds_and_separate_admission(tmp_path: Path) -> None:
    """Read more than 64 distinct declarations without admitting their source policy.

    Parameters
    ----------
    tmp_path
        Declaration-only controls without acquired source bodies or a reviewed policy.
    """
    value = _declaration()
    original = value["source_files"][0]
    value["source_files"] = [
        {**original, "path": f"source/component-{index}.py"} for index in range(65)
    ]
    path = tmp_path / "run.json"
    _write(path, value)
    assert len(path.read_bytes()) < 65536
    assert load_neural_manifest(path) == value
    with pytest.raises(NeuralCaptureRefusalError, match="No reviewed source contract"):
        load_neural_run(path)
    command = Path(sys.executable).with_name("loop-timing-witness-analyze")
    result = subprocess.run(
        [str(command), str(path), "--output-dir", str(tmp_path / "report")],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert "No reviewed source contract" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (tmp_path / "report").exists()
    value["source_files"] *= 10
    _write(path, value)
    assert len(path.read_bytes()) > 65536
    with pytest.raises(NeuralCaptureRefusalError, match="byte allocation"):
        load_neural_manifest(path)
    with pytest.raises(NeuralCaptureRefusalError, match="byte allocation"):
        decode_neural_manifest(path.read_bytes())


@pytest.mark.parametrize("kind", ["changed", "absent"])
def test_actual_package_schema_damage_is_refused(tmp_path: Path, kind: str) -> None:
    """Exercise missing and changed installed schema bodies in an independent consumer.

    Parameters
    ----------
    tmp_path
        Actual complete package copy and independent input directory.
    kind
        Real schema byte mutation or removal, without changing production source.
    """
    package_root = tmp_path / "consumer"
    package = package_root / "loop_timing_witness"
    shutil.copytree(ROOT / "src/loop_timing_witness", package)
    schema = package / "data/neural-step-run.schema.json"
    if kind == "changed":
        schema.write_bytes(schema.read_bytes() + b" ")
    else:
        schema.unlink()
    path = tmp_path / "run.json"
    _write(path, _declaration())
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; import sys; "
                "from loop_timing_witness.neural_run_manifest import load_neural_manifest; "
                "from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError\n"
                "try: load_neural_manifest(Path(sys.argv[1]))\n"
                "except NeuralCaptureRefusalError as exc: print(str(exc)); sys.exit(1)\n"
            ),
            str(path),
        ],
        cwd=package_root,
        env={**os.environ, "PYTHONPATH": str(package_root), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.startswith("Installed neural manifest schema ")
    assert result.stderr == ""


@pytest.mark.parametrize("field", ["run_id", "source_pin", "reference_sha"])
def test_final_newline_cannot_alias_an_identity_or_digest(tmp_path: Path, field: str) -> None:
    """Refuse real declarations whose final newline can satisfy a schema dollar anchor.

    Parameters
    ----------
    tmp_path
        One complete input control derived from the retained real acquisition.
    field
        Original run identity, source pin or file digest with one added newline.
    """
    value = _declaration()
    if field == "run_id":
        value["run_id"] += "\n"
    elif field == "source_pin":
        value["sc_body_pins"]["hdl/sc_lif_neuron.v"] += "\n"
    else:
        value["source_files"][0]["sha256"] += "\n"
    path = tmp_path / "run.json"
    _write(path, value)
    with pytest.raises(NeuralCaptureRefusalError, match="exact"):
        load_neural_manifest(path)


def test_nul_manifest_path_uses_authored_refusal(tmp_path: Path) -> None:
    """Refuse an actual invalid Path before the OS argument decoder exposes ValueError.

    Parameters
    ----------
    tmp_path
        Parent allocation for the deliberately invalid manifest path.
    """
    with pytest.raises(NeuralCaptureRefusalError, match="invalid NUL"):
        load_neural_manifest(tmp_path / "invalid\0manifest")


def _package_copy(tmp_path: Path) -> Path:
    """Copy the maintained package into an isolated installation.

    Parameters
    ----------
    tmp_path
        Owned directory.

    Returns
    -------
    Path
        Copied package directory.
    """
    source = Path(__file__).resolve().parents[1] / "src/loop_timing_witness"
    installed = tmp_path / "installation/loop_timing_witness"
    shutil.copytree(source, installed, ignore=shutil.ignore_patterns("__pycache__"))
    return installed


@pytest.mark.parametrize(
    ("damage", "message"),
    [("absent", "schema is unavailable"), ("changed", "schema differs from its admitted body")],
)
def test_installed_schema_must_be_present_and_admitted(
    tmp_path: Path, damage: str, message: str
) -> None:
    """Refuse every manifest when the installed carrier schema is absent or changed.

    Parameters
    ----------
    tmp_path
        Owned package copy.
    damage
        Removal or a one-byte change of the installed schema.
    message
        Expected refusal fragment.
    """
    installed = _package_copy(tmp_path)
    schema = installed / "data/neural-step-run.schema.json"
    if damage == "absent":
        schema.unlink()
    else:
        schema.write_bytes(schema.read_bytes() + b" ")
    client = (
        "import sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError\n"
        "from loop_timing_witness.neural_run_manifest import decode_neural_manifest\n"
        "try:\n"
        "    decode_neural_manifest(b'{}')\n"
        "except NeuralCaptureRefusalError as error:\n"
        "    print(error)\n"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", client, str(installed.parent)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert message in result.stdout
