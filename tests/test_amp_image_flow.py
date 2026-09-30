# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — public actual image preparation compilation and drift refusal

"""Exercise public prepared Make builds and actual original firmware admission."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from amp_image_options import ImageRequest, verification_arguments
from prepare_amp_image import BuildInputs, prepare_image
from prepare_amp_image import main as prepare_main
from test_amp_contract import COEFFICIENTS
from test_amp_device import PATH
from test_amp_device import SELECTION as PLIC_SELECTION
from test_amp_memory import SELECTION as MEMORY_SELECTION
from test_amp_platform import SOURCE
from test_device_tree_resources import CompileTree, compile_tree
from verify_amp_image import main as verify_main
from verify_amp_image import verify_image

__all__ = ["compile_tree"]
ROOT = Path(__file__).resolve().parents[1]
REQUEST = ImageRequest(MEMORY_SELECTION, PLIC_SELECTION, PATH)
CONFIGURATION = (
    "pid 10 32768 " + " ".join(map(str, COEFFICIENTS)) + " 0 16777216 0 0 0 none 0 0 0 0\n"
).encode("ascii")


@pytest.fixture
def prepared_image(compile_tree: CompileTree, tmp_path: Path) -> Path:
    """Compile a public original image through preparation CLI and its generated Makefile.

    Parameters
    ----------
    compile_tree
        Actual dtc compiler and public decoder.
    tmp_path
        Exact owned original inputs and image outputs.

    Returns
    -------
    Path
        Actual compiled and verified public image directory.
    """
    compile_tree(SOURCE)
    configuration = tmp_path / "configuration.txt"
    configuration.write_bytes(CONFIGURATION)
    compiler = os.environ.get("WITNESS_RV64_CC") or shutil.which("riscv64-linux-gnu-gcc")
    assert compiler is not None, "actual RV64 compiler is required"
    output = tmp_path / "image"
    arguments = verification_arguments(REQUEST)
    arguments[arguments.index("platform.dtb")] = str(tmp_path / "platform.dtb")
    arguments[arguments.index("configuration.txt")] = str(configuration)
    assert prepare_main([*arguments, "--output", str(output), "--compiler", compiler, "--isa"]) == 0
    with (tmp_path / "make.log").open("wb") as log:
        subprocess.run(
            ["make", "-C", str(output), "-j2"],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=60,
        )
    return output


def test_public_original_image_flow(prepared_image: Path) -> None:
    """Verify public image manifests and byte-stable repeat admission after a real build.

    Parameters
    ----------
    prepared_image
        Actual original public build output.
    """
    (prepared_image / "image.json").unlink()
    manifest = verify_image(
        prepared_image,
        prepared_image / "platform.dtb",
        prepared_image / "configuration.txt",
        REQUEST,
    )
    assert len(json.loads(manifest.read_bytes())["segments"]) == 2
    assert (prepared_image / "source/runtime/bare_metal/entry.S").exists()
    assert (prepared_image / "source/runtime/bare_metal/firmware.ld").exists()
    assert "compiler_dependencies" in json.loads(manifest.read_bytes())
    arguments = verification_arguments(REQUEST)
    arguments[arguments.index("platform.dtb")] = str(prepared_image / "platform.dtb")
    arguments[arguments.index("configuration.txt")] = str(prepared_image / "configuration.txt")
    assert verify_main(["--directory", str(prepared_image), *arguments]) == 0


@pytest.mark.parametrize(
    ("field", "value", "finding"),
    [
        ("schema", "other", "schema"),
        ("isa", 1, "mode"),
        ("compiler", 1, "identity"),
        ("compiler_sha256", 1, "identity"),
        ("compiler_sha256", "0" * 64, "compiler bytes"),
        ("toolchain", {}, "compiler subprograms"),
        ("compiler", "relative", "compiler bytes"),
        ("inputs", {}, "identity"),
        ("inputs", [], "identity"),
        ("inputs", {"contract.c": "0" * 64}, "required original"),
    ],
)
def test_preparation_identity_refusal(
    prepared_image: Path, field: str, value: object, finding: str
) -> None:
    """Reject corrupt original preparation identity before trusting compiled output.

    Parameters
    ----------
    prepared_image
        Actual real build output.
    field
        Original preparation field to corrupt.
    value
        Invalid identity or shape.
    finding
        Required verification refusal.
    """
    path = prepared_image / "preparation.json"
    data = json.loads(path.read_bytes())
    data[field] = value
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match=finding):
        verify_image(
            prepared_image,
            prepared_image / "platform.dtb",
            prepared_image / "configuration.txt",
            REQUEST,
        )


@pytest.mark.parametrize(
    "corruption",
    [
        "hash-type",
        "escape",
        "source",
        "dependency-count",
        "dependency-shape",
        "dependency-empty",
        "manifest",
    ],
)
def test_original_build_drift(prepared_image: Path, corruption: str) -> None:
    """Refuse changed source bytes, escaped inputs and malformed real compiler receipts.

    Parameters
    ----------
    prepared_image
        Actual original image and preparation.
    corruption
        Exact original input or compiler receipt to corrupt.
    """
    preparation = prepared_image / "preparation.json"
    data = json.loads(preparation.read_bytes())
    if corruption == "hash-type":
        data["inputs"]["contract.c"] = 1
        preparation.write_text(json.dumps(data), encoding="utf-8")
        finding = "must be strings"
    elif corruption == "escape":
        data["inputs"]["../escape"] = "0" * 64
        preparation.write_text(json.dumps(data), encoding="utf-8")
        finding = "paths changed"
    elif corruption == "source":
        (prepared_image / "contract.c").write_text("changed", encoding="ascii")
        finding = "bytes or paths changed"
    elif corruption == "dependency-count":
        (prepared_image / "objects/input_0.o.d").unlink()
        finding = "all five"
    elif corruption == "dependency-shape":
        (prepared_image / "objects/input_0.o.d").write_text("malformed", encoding="ascii")
        finding = "record is malformed"
    elif corruption == "dependency-empty":
        (prepared_image / "objects/input_0.o.d").write_text("target:", encoding="ascii")
        finding = "record is empty"
    else:
        (prepared_image / "image.json").write_text("{}", encoding="ascii")
        finding = "different bytes"
    with pytest.raises(ValueError, match=finding):
        verify_image(
            prepared_image,
            prepared_image / "platform.dtb",
            prepared_image / "configuration.txt",
            REQUEST,
        )


def test_alternate_configuration_refused(prepared_image: Path) -> None:
    """Reject another fabric reference despite matching compiled controller constants.

    Parameters
    ----------
    prepared_image
        Original real image build.
    """
    configuration = prepared_image / "other.txt"
    configuration.write_bytes(
        CONFIGURATION.replace(b" 16777216 0 0 0 none", b" 16777217 0 0 0 none")
    )
    arguments = verification_arguments(REQUEST)
    arguments[arguments.index("platform.dtb")] = str(prepared_image / "platform.dtb")
    arguments[arguments.index("configuration.txt")] = str(configuration)
    assert verify_main(["--directory", str(prepared_image), *arguments]) == 1


def test_nonexecutable_compiler_refused(compile_tree: CompileTree, tmp_path: Path) -> None:
    """Refuse nonexecutable original compiler selections before output allocation.

    Parameters
    ----------
    compile_tree
        Actual original dtc compiler.
    tmp_path
        Exact owned input staging.
    """
    compile_tree(SOURCE)
    config = tmp_path / "config.txt"
    config.write_bytes(CONFIGURATION)
    compiler = tmp_path / "not-executable"
    compiler.write_bytes(b"not executable")
    output = tmp_path / "image"
    build = BuildInputs(ROOT, tmp_path / "platform.dtb", config, compiler, isa=False)
    with pytest.raises(ValueError, match="actual executable"):
        prepare_image(build, output, REQUEST)
    assert not output.exists()


def test_actual_parked_exit_build(prepared_image: Path) -> None:
    """Build and admit the original parked exit without an ISA completion channel.

    Parameters
    ----------
    prepared_image
        Actual first prepared image with retained original inputs.
    """
    compiler = os.environ.get("WITNESS_RV64_CC")
    assert compiler is not None
    output = prepared_image.parent / "parked-image"
    build = BuildInputs(
        ROOT,
        prepared_image / "platform.dtb",
        prepared_image / "configuration.txt",
        Path(compiler),
        isa=False,
    )
    prepare_image(build, output, REQUEST)
    with (prepared_image.parent / "parked-make.log").open("wb") as log:
        subprocess.run(
            ["make", "-C", str(output), "-j2"],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=60,
        )
    manifest = verify_image(output, output / "platform.dtb", output / "configuration.txt", REQUEST)
    assert json.loads(manifest.read_bytes())["exit_mode"] == "parked"
    assert (output / "source/Makefile").read_bytes() == (ROOT / "Makefile").read_bytes()
