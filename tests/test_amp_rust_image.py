# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — public original Rust arithmetic image compilation and receipt

"""Build actual RV64 Rust firmware through the public preparation and verification CLIs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from amp_image_options import verification_arguments
from amp_image_receipt import validate_image_receipt
from prepare_amp_image import main as prepare_main
from test_amp_image_flow import CONFIGURATION, REQUEST
from test_amp_platform import SOURCE
from verify_amp_image import main as verify_main

from loop_timing_witness.amp_rust_receipt import (
    validate_rust_image_receipt,
    validate_rust_preparation_snapshot,
)


@pytest.fixture(scope="module")
def rust_image(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Compile real original Rust firmware once through the public CLI and generated Makefile.

    Parameters
    ----------
    tmp_path_factory
        Exclusive actual platform and source-bound image allocation.

    Returns
    -------
    Path
        Actual compiled RV64 Rust image with complete original receipt and captured inputs.
    """
    tmp_path = tmp_path_factory.mktemp("public-rust-image")
    dtc = shutil.which("dtc")
    assert dtc is not None, "actual original device-tree compiler is required"
    source = tmp_path / "platform.dts"
    source.write_text(SOURCE, encoding="ascii")
    subprocess.run(
        [dtc, "-I", "dts", "-O", "dtb", "-o", str(tmp_path / "platform.dtb"), str(source)],
        capture_output=True,
        check=True,
        timeout=10,
    )
    configuration = tmp_path / "configuration.txt"
    configuration.write_bytes(CONFIGURATION)
    compiler = os.environ.get("WITNESS_RV64_CC") or shutil.which("riscv64-linux-gnu-gcc")
    assert compiler is not None, "actual RV64 compiler is required"
    output = tmp_path / "image"
    arguments = verification_arguments(REQUEST)
    arguments[arguments.index("platform.dtb")] = str(tmp_path / "platform.dtb")
    arguments[arguments.index("configuration.txt")] = str(configuration)
    assert (
        prepare_main(
            [
                *arguments,
                "--output",
                str(output),
                "--compiler",
                compiler,
                "--isa",
                "--rust-compiler",
                "rustc",
            ]
        )
        == 0
    )
    with (tmp_path / "make.log").open("wb") as log:
        subprocess.run(
            ["make", "-C", str(output), "-j2"],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=90,
        )
    return output


def test_public_rust_image_build(rust_image: Path) -> None:
    """Admit the linked actual Rust image through public live and portable receipt verification.

    Parameters
    ----------
    rust_image
        Actual original linked RV64 image and source/runtime snapshots.
    """
    output = rust_image
    receipt = json.loads((output / "image.json").read_bytes())
    preparation = json.loads((output / "preparation.json").read_bytes())
    assert receipt["kernel_backend"] == preparation["kernel_backend"] == "rust"
    assert len(preparation["dependency_records"]) == 4
    assert len(receipt["rust_kernel"]["outputs"]) == 4
    assert len(receipt["rust_kernel"]["preparation"]["dependencies"]) == 2
    assert "source/controllers/c/witness_controller.c" not in receipt["compiler_dependencies"]
    assert (output / "firmware.elf").read_bytes().startswith(b"\x7fELF")
    validate_image_receipt(output, receipt, preparation)
    arguments = verification_arguments(REQUEST)
    arguments[arguments.index("platform.dtb")] = str(output / "platform.dtb")
    arguments[arguments.index("configuration.txt")] = str(output / "configuration.txt")
    assert verify_main(["--directory", str(output), *arguments]) == 0


@pytest.mark.parametrize("fault", ["c-selection", "backend", "receipt", "outputs"])
def test_offline_rust_image_declaration_drift_refused(rust_image: Path, fault: str) -> None:
    """Alter original decoded declarations and require portable Rust/C custody refusal.

    Parameters
    ----------
    rust_image
        Actual original source-bound RV64 image.
    fault
        Backend, nested preparation or output hash declaration to contradict.
    """
    image = json.loads((rust_image / "image.json").read_bytes())
    preparation = json.loads((rust_image / "preparation.json").read_bytes())
    if fault == "c-selection":
        preparation.pop("kernel_backend")
    elif fault == "backend":
        image["kernel_backend"] = "other"
    elif fault == "receipt":
        image["rust_kernel"]["preparation"] = {}
    else:
        image["rust_kernel"]["outputs"] = {}
    with pytest.raises(ValueError, match="Rust"):
        validate_rust_image_receipt(rust_image, image, preparation)


@pytest.mark.parametrize("fault", ["schema", "identity", "vectors", "records", "closure"])
def test_offline_original_rust_preparation_drift_refused(rust_image: Path, fault: str) -> None:
    """Refuse malformed original portable Rust identity and dependency declarations.

    Parameters
    ----------
    rust_image
        Actual captured original source/library bytes and metadata records.
    fault
        Original captured preparation declaration to corrupt.
    """
    data = json.loads((rust_image / "rust_preparation.json").read_bytes())
    if fault == "schema":
        data["schema"] = "other"
    elif fault == "identity":
        data["toolchain"]["compiler"]["sha256"] = "invalid"
    elif fault == "vectors":
        data["metadata_commands"] = []
    elif fault == "records":
        data["dependency_records"] = {}
    else:
        data["dependencies"] = {}
    with pytest.raises(ValueError, match="Rust"):
        validate_rust_preparation_snapshot(rust_image, data)


def test_portable_original_c_image_has_no_rust_archive() -> None:
    """Preserve the actual C default backend when checking the portable image receipt."""
    directory = Path(os.environ["WITNESS_AMP_IMAGE"])
    image = json.loads((directory / "image.json").read_bytes())
    preparation = json.loads((directory / "preparation.json").read_bytes())
    assert "kernel_backend" not in image
    assert "kernel_backend" not in preparation
    validate_rust_image_receipt(directory, image, preparation)


@pytest.mark.parametrize("fault", ["closure", "archive"])
def test_portable_rust_final_compiler_artifact_drift_refused(rust_image: Path, fault: str) -> None:
    """Refuse an altered actual final Rust graph or archive, then restore original bytes.

    Parameters
    ----------
    rust_image
        Publicly compiled and verified RV64 Rust image.
    fault
        Changed original final dependency graph or malformed archive framing.
    """
    image = json.loads((rust_image / "image.json").read_bytes())
    preparation = json.loads((rust_image / "preparation.json").read_bytes())
    name = (
        "objects/rust/adapter.d"
        if fault == "closure"
        else "objects/rust/libwitness_amp_rust_kernel.a"
    )
    path = rust_image / name
    original = path.read_bytes()
    if fault == "closure":
        adapter = b"source/runtime/bare_metal/rust_kernel/src/lib.rs"
        core = b"source/controllers/rust/src/lib.rs"
        assert adapter in original
        altered = original.replace(adapter, core)
    else:
        assert original.startswith(b"!<arch>\n")
        altered = b"not a compiler archive\n"
    try:
        path.write_bytes(altered)
        with pytest.raises(ValueError, match="Rust"):
            validate_rust_image_receipt(rust_image, image, preparation)
    finally:
        path.write_bytes(original)
