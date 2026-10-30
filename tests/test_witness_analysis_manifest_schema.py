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


def test_native_binary_manifest_schema_identity_is_enforced(tmp_path: Path) -> None:
    """Change one embedded data byte while preserving the complete compiled program code.

    Parameters
    ----------
    tmp_path
        Owned native build, bounded manifest input and one changed executable copy.
        The executable copy is necessary to exercise installed-artifact refusal;
        caller input and checksum records cannot change embedded schema bytes.
    """
    toolchain = tomllib.loads((ROOT / "rust-toolchain.toml").read_text(encoding="utf-8"))[
        "toolchain"
    ]["channel"]
    assert isinstance(toolchain, str)
    environment = dict(os.environ)
    environment.update(
        TMPDIR=str(tmp_path),
        CARGO_BUILD_JOBS="1",
        CARGO_INCREMENTAL="0",
        CARGO_PROFILE_DEV_DEBUG="0",
        RUSTUP_TOOLCHAIN=toolchain,
    )
    target = tmp_path / "target"
    source_pins = {
        path.relative_to(CRATE).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (CRATE / "src").rglob("*.rs")
    }
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
    binary = target / "debug/loop-timing-witness-analyze-native"
    manifest = tmp_path / "declaration.json"
    manifest.write_bytes((CRATE / "tests/data/neural-selected-original.run.json").read_bytes())
    output = tmp_path / "report"
    baseline = _native(
        [str(binary), str(manifest), "--output-dir", str(output)], environment, expected=1
    )
    assert baseline.stdout == ""
    # The declaration passes the schema check and reaches the registry entry factory.
    assert "No reviewed checker installation descriptor is selected" in baseline.stderr
    assert "Installed neural manifest schema differs" not in baseline.stderr
    assert not output.exists()
    schema = (CRATE / "neural-step-run.schema.json").read_bytes()
    assert schema.endswith(b"\n")
    altered = schema[:-1] + b" "
    assert json.loads(altered) == json.loads(schema)
    image = binary.read_bytes()
    assert image.count(schema) == 1
    changed_image = image.replace(schema, altered, 1)
    assert len(changed_image) == len(image)
    changed_offset = image.index(schema) + len(schema) - 1
    assert changed_image[:changed_offset] == image[:changed_offset]
    assert changed_image[changed_offset] != image[changed_offset]
    assert changed_image[changed_offset + 1 :] == image[changed_offset + 1 :]
    changed_binary = tmp_path / "schema-changed-analysis"
    shutil.copy2(binary, changed_binary)
    changed_binary.write_bytes(changed_image)
    refusal = _native(
        [str(changed_binary), str(manifest), "--output-dir", str(output)],
        environment,
        expected=1,
    )
    assert refusal.stdout == ""
    assert refusal.stderr == (
        "run analysis: FAIL: Installed neural manifest schema differs from its admitted body.\n"
    )
    assert not output.exists()
    assert binary.read_bytes() == image
    assert (CRATE / "neural-step-run.schema.json").read_bytes() == schema
    for relative_name, digest in source_pins.items():
        assert hashlib.sha256((CRATE / relative_name).read_bytes()).hexdigest() == digest
    (tmp_path / "native-schema-result.json").write_text(
        json.dumps(
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
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
