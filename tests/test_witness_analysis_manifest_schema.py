# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — compiled native manifest schema identity

"""Refuse changed schema data in a copy of the actual compiled native analysis CLI."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CRATE = ROOT / "analysis/rust"


def _native(
    arguments: list[str], environment: dict[str, str], expected: int = 0
) -> subprocess.CompletedProcess[str]:
    """Run a real build or CLI process under a whole-process-group deadline.

    Parameters
    ----------
    arguments
        Fixed Cargo or compiled native CLI argument vector, without a shell.
    environment
        Owned temporary allocation, exact project toolchain and shared dependency cache.
    expected
        Native success or deliberately authored schema-refusal exit status.

    Returns
    -------
    subprocess.CompletedProcess of str
        Reaped native status and actual standard output and error.
    """
    result = subprocess.run(
        ["timeout", "--signal=TERM", "--kill-after=5s", "240s", *arguments],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == expected, (result.stdout, result.stderr)
    return result


def _build_environment(directory: Path) -> dict[str, str]:
    """Return the process environment of the project toolchain's single-job debug build.

    Parameters
    ----------
    directory
        Owned temporary allocation.

    Returns
    -------
    dict[str, str]
        This process's environment with the build settings and toolchain pin.
    """
    toolchain = tomllib.loads((ROOT / "rust-toolchain.toml").read_text(encoding="utf-8"))[
        "toolchain"
    ]["channel"]
    assert isinstance(toolchain, str)
    environment = dict(os.environ)
    environment.update(
        TMPDIR=str(directory),
        CARGO_BUILD_JOBS="1",
        CARGO_INCREMENTAL="0",
        CARGO_PROFILE_DEV_DEBUG="0",
        RUSTUP_TOOLCHAIN=toolchain,
    )
    return environment


def _source_pins() -> dict[str, str]:
    """Return the SHA-256 of every crate source file.

    Returns
    -------
    dict[str, str]
        Digest by crate-relative path.
    """
    return {
        path.relative_to(CRATE).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (CRATE / "src").rglob("*.rs")
    }


def _build(
    environment: dict[str, str], target: Path
) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Build the native analysis executable into an owned target directory.

    Parameters
    ----------
    environment
        Build environment.
    target
        Owned Cargo target directory.

    Returns
    -------
    tuple[subprocess.CompletedProcess[str], Path]
        Build process and the built executable.
    """
    built = _native(
        [
            "cargo",
            "build",
            "--offline",
            "--locked",
            "--manifest-path",
            str(CRATE / "Cargo.toml"),
            "--target-dir",
            str(target),
            "--bin",
            "loop-timing-witness-analyze-native",
        ],
        environment,
    )
    return built, target / "debug/loop-timing-witness-analyze-native"


def _analyse(
    binary: Path, manifest: Path, output: Path, environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """Run one native analysis that must refuse without printing or publishing.

    Parameters
    ----------
    binary
        Native analysis executable.
    manifest
        Declaration to analyse.
    output
        Report directory that must stay absent.
    environment
        Process environment.

    Returns
    -------
    subprocess.CompletedProcess[str]
        The refused process.
    """
    result = _native(
        [str(binary), str(manifest), "--output-dir", str(output)], environment, expected=1
    )
    assert result.stdout == ""
    assert not output.exists()
    return result


def _change_schema_byte(image: bytes, schema: bytes) -> tuple[bytes, bytes, int]:
    """Change the embedded schema's final newline into a space, keeping everything else.

    Parameters
    ----------
    image
        Executable bytes holding the schema exactly once.
    schema
        Installed schema bytes.

    Returns
    -------
    tuple[bytes, bytes, int]
        Changed schema, which decodes to the same document, the changed image and
        the offset of its one changed byte.
    """
    assert schema.endswith(b"\n")
    altered = schema[:-1] + b" "
    assert json.loads(altered) == json.loads(schema)
    assert image.count(schema) == 1
    changed_image = image.replace(schema, altered, 1)
    assert len(changed_image) == len(image)
    changed_offset = image.index(schema) + len(schema) - 1
    assert changed_image[:changed_offset] == image[:changed_offset]
    assert changed_image[changed_offset] != image[changed_offset]
    assert changed_image[changed_offset + 1 :] == image[changed_offset + 1 :]
    return altered, changed_image, changed_offset


def _write_changed_copy(binary: Path, schema: bytes, copy: Path) -> tuple[bytes, bytes, bytes, int]:
    """Copy the executable with its embedded schema's final byte changed.

    Parameters
    ----------
    binary
        Built native analysis executable, left unchanged.
    schema
        Installed schema bytes.
    copy
        Changed copy to write, keeping the original's mode.

    Returns
    -------
    tuple[bytes, bytes, bytes, int]
        Original image, changed schema, changed image and the changed byte's offset.
    """
    image = binary.read_bytes()
    altered, changed_image, changed_offset = _change_schema_byte(image, schema)
    shutil.copy2(binary, copy)
    copy.write_bytes(changed_image)
    return image, altered, changed_image, changed_offset


def _check_sources_unchanged(schema: bytes, source_pins: dict[str, str]) -> None:
    """Require the installed schema and every crate source to be unchanged.

    Parameters
    ----------
    schema
        Installed schema bytes read before the change.
    source_pins
        Crate source digests taken before the build.
    """
    assert (CRATE / "neural-step-run.schema.json").read_bytes() == schema
    for relative_name, digest in source_pins.items():
        assert hashlib.sha256((CRATE / relative_name).read_bytes()).hexdigest() == digest


def _write_result(path: Path, record: dict[str, object]) -> None:
    """Retain the result record as indented JSON with a final newline.

    Parameters
    ----------
    path
        Result file.
    record
        Result fields in their written order.
    """
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def test_native_binary_manifest_schema_identity_is_enforced(tmp_path: Path) -> None:
    """Change one embedded data byte while preserving the complete compiled program code.

    Parameters
    ----------
    tmp_path
        Owned native build, bounded manifest input and one changed executable copy.
        The executable copy is necessary to exercise installed-artifact refusal;
        caller input and checksum records cannot change embedded schema bytes.
    """
    environment = _build_environment(tmp_path)
    source_pins = _source_pins()
    built, binary = _build(environment, tmp_path / "target")
    manifest = tmp_path / "declaration.json"
    manifest.write_bytes((CRATE / "tests/data/neural-selected-original.run.json").read_bytes())
    output = tmp_path / "report"
    baseline = _analyse(binary, manifest, output, environment)
    # The declaration passes the schema check and reaches the registry entry factory.
    assert "No reviewed checker installation descriptor is selected" in baseline.stderr
    assert "Installed neural manifest schema differs" not in baseline.stderr
    schema = (CRATE / "neural-step-run.schema.json").read_bytes()
    changed_binary = tmp_path / "schema-changed-analysis"
    image, altered, changed_image, changed_offset = _write_changed_copy(
        binary, schema, changed_binary
    )
    refusal = _analyse(changed_binary, manifest, output, environment)
    assert refusal.stderr == (
        "run analysis: FAIL: Installed neural manifest schema differs from its admitted body.\n"
    )
    assert binary.read_bytes() == image
    _check_sources_unchanged(schema, source_pins)
    _write_result(
        tmp_path / "native-schema-result.json",
        {
            "canonical_crate": str(CRATE),
            "source_pins": source_pins,
            "schema_before_sha256": hashlib.sha256(schema).hexdigest(),
            "schema_after_sha256": hashlib.sha256(altered).hexdigest(),
            "binary": str(binary),
            "binary_sha256": hashlib.sha256(image).hexdigest(),
            "altered_binary": str(changed_binary),
            "altered_binary_sha256": hashlib.sha256(changed_image).hexdigest(),
            "one_changed_data_byte_offset": changed_offset,
            "build_status": built.returncode,
            "baseline_status": baseline.returncode,
            "native_refusal_status": refusal.returncode,
            "stderr": refusal.stderr,
            "report_published": output.exists(),
        },
    )
