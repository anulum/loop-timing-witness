# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — public source-bound dedicated firmware build preparation

"""Prepare original admitted firmware inputs and a real RV64 compiler Makefile."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from amp_build_toolchain import compiler_identity, preprocess_image
from amp_contract import render_contract
from amp_image_dependencies import image_dependency_hashes, snapshot_image_dependencies
from amp_image_options import (
    ImageRequest,
    add_image_arguments,
    image_request,
    verification_arguments,
)
from amp_image_recipe import FLAGS, c_compile_rules, quote_recipe, rust_compile_rules
from amp_package_snapshot import snapshot_verifier_package
from amp_platform import bind_platform
from amp_run_input import read_amp_run
from amp_runtime_snapshot import snapshot_runtime
from amp_rust_build import prepare_rust_sources
from device_tree_blob import decode_device_tree

from manifest_io import canonical_json_bytes, sha256_of_file

if TYPE_CHECKING:
    from device_tree_resources import Region

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class BuildInputs:
    """Explicit original files and compiler used for one exclusive firmware preparation.

    Parameters
    ----------
    root
        Canonical source checkout.
    dtb
        Original complete platform binary.
    configuration
        Original complete native run configuration.
    compiler
        Actual installed cross-compiler executable.
    isa
        Whether target completion uses ISA HTIF instead of parking.
    rust_compiler
        Explicit original Rust selector for arithmetic; absent selects the original C kernel.
    """

    root: Path
    dtb: Path
    configuration: Path
    compiler: Path
    isa: bool
    rust_compiler: str | None = None


@dataclass(frozen=True)
class _ImagePlan:
    """Resolved compiler, compiled sources and target of one image build.

    Attributes
    ----------
    compiler
        Resolved executable compiler driver.
    sources
        Repository-relative sources compiled into the firmware.
    firmware
        Admitted firmware reservation.
    request
        Explicit original resource and stack selection.
    build
        Original build inputs, for the source root and target mode.
    """

    compiler: Path
    sources: list[str]
    firmware: Region
    request: ImageRequest
    build: BuildInputs


def _checked_compiler(compiler: Path) -> Path:
    """Resolve the firmware compiler and require an executable file.

    Parameters
    ----------
    compiler
        Selected compiler driver.

    Returns
    -------
    Path
        The resolved driver.

    Raises
    ------
    ValueError
        If the resolved path is not an executable file.
    """
    resolved = compiler.resolve()
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        message = "firmware compiler must be an actual executable file"
        raise ValueError(message)
    return resolved


def _image_sources(exit_path: str, build: BuildInputs) -> list[str]:
    """Return the sources compiled into the firmware, in compile order.

    Parameters
    ----------
    exit_path
        Exit channel source of the target mode.
    build
        Original build inputs; a Rust kernel replaces the C controller.

    Returns
    -------
    list[str]
        Entry, controller runtime, exit channel, C controller unless the Rust
        kernel is built, and the rendered contract.
    """
    sources = [
        "runtime/bare_metal/entry.S",
        "runtime/bare_metal/amp_controller.c",
        exit_path,
        "controllers/c/witness_controller.c",
        "contract.c",
    ]
    if build.rust_compiler is not None:
        sources.remove("controllers/c/witness_controller.c")
    return sources


def _copy_originals(root: Path, output: Path, exit_path: str) -> None:
    """Copy every original build, runtime and verifier file into the image source.

    Parameters
    ----------
    root
        Source checkout.
    output
        Image build directory.
    exit_path
        Exit channel source of the target mode.
    """
    originals = [
        "Makefile",
        "controllers/c/witness_controller.c",
        "controllers/c/witness_controller.h",
        "runtime/bare_metal/entry.S",
        "runtime/bare_metal/amp_controller.c",
        "runtime/bare_metal/amp_contract.h",
        "runtime/bare_metal/firmware.ld",
        exit_path,
        "tools/verify_amp_image.py",
        "tools/verify_amp_preparation.py",
        "tools/prepare_amp_image.py",
        "tools/manifest_io.py",
    ]
    originals.extend(
        str(path.relative_to(root))
        for pattern in ("amp_*.py", "device_tree_*.py")
        for path in (root / "tools").glob(pattern)
    )
    for name in sorted(set(originals)):
        destination = output / "source" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, destination)


def _write_target(output: Path, dtb_bytes: bytes, run_bytes: bytes, contract: str) -> None:
    """Write the original topology and run configuration and the rendered contract.

    Parameters
    ----------
    output
        Image build directory.
    dtb_bytes, run_bytes
        Original device tree and run configuration.
    contract
        C contract rendered from the admitted platform and run.
    """
    (output / "platform.dtb").write_bytes(dtb_bytes)
    (output / "configuration.txt").write_bytes(run_bytes)
    (output / "contract.c").write_text(contract, encoding="utf-8")


def _link_vector(plan: _ImagePlan, objects: list[str]) -> list[str]:
    """Return the static link of the firmware into its reserved RAM.

    Parameters
    ----------
    plan
        Compiler, firmware reservation and stack request.
    objects
        Compiled objects and libraries.

    Returns
    -------
    list[str]
        Link vector producing ``firmware.elf``.
    """
    return [
        str(plan.compiler),
        *FLAGS,
        "-nostdlib",
        "-nostartfiles",
        "-static",
        "-no-pie",
        "-Wl,--build-id=none",
        f"-Wl,--defsym=__witness_ram_origin={plan.firmware.address}",
        f"-Wl,--defsym=__witness_ram_length={plan.firmware.size}",
        f"-Wl,--defsym=__witness_stack_size={plan.request.memory.stack_bytes}",
        "-T",
        "source/runtime/bare_metal/firmware.ld",
        *objects,
        "-o",
        "firmware.elf",
    ]


def _write_build(
    output: Path, plan: _ImagePlan, rust: dict[str, Any] | None
) -> tuple[Path, list[list[str]]]:
    """Write the image Makefile and the recorded build commands.

    Parameters
    ----------
    output
        Image build directory.
    plan
        Compiler, sources, reservation, request and build inputs.
    rust
        Prepared Rust kernel sources, if the Rust kernel is built.

    Returns
    -------
    tuple[Path, list[list[str]]]
        The Makefile and the compile commands.
    """
    rules = [
        *(plan.build.root / "Makefile").read_text(encoding="utf-8").splitlines()[:7],
        ".PHONY: all verify verify-inputs",
        "all: verify",
        "",
    ]
    compile_rules, objects, commands = c_compile_rules(str(plan.compiler), plan.sources)
    rules.extend(compile_rules)
    if rust is not None:
        rust_rules, library = rust_compile_rules(rust["toolchain"]["compiler"]["path"])
        rules.extend(rust_rules)
        objects.append(library)
    link = _link_vector(plan, objects)
    python = str(Path(sys.executable).absolute())
    verify = [
        python,
        "source/tools/verify_amp_image.py",
        "--directory",
        ".",
        *verification_arguments(plan.request),
    ]
    precheck = [python, "source/tools/verify_amp_preparation.py", "--directory", "."]
    rules.extend(_final_rules(objects, link, verify, precheck))
    makefile = output / "Makefile"
    makefile.write_text("\n".join(rules), encoding="utf-8")
    (output / "build_commands.json").write_bytes(
        canonical_json_bytes(
            {"compile": commands, "link": link, "verify": verify, "precheck": precheck}
        )
    )
    return makefile, commands


def _final_rules(
    objects: list[str], link: list[str], verify: list[str], precheck: list[str]
) -> list[str]:
    """Return the input check, link and verification rules of the Makefile.

    Parameters
    ----------
    objects
        Compiled objects and libraries.
    link, verify, precheck
        Link, image verification and preparation check vectors.

    Returns
    -------
    list[str]
        Makefile lines of the three final rules.
    """
    return [
        "verify-inputs:",
        "\t" + quote_recipe(precheck),
        "",
        "firmware.elf: " + " ".join(objects) + " | verify-inputs",
        "\t" + quote_recipe(link) + " > link.log 2>&1",
        "",
        "verify: firmware.elf",
        "\t" + quote_recipe(verify),
        "",
    ]


def _write_preparation(
    output: Path,
    plan: _ImagePlan,
    toolchain: dict[str, Any],
    commands: list[list[str]],
    *,
    rust_kernel: bool,
) -> None:
    """Preprocess the image, snapshot its dependencies and write ``preparation.json``.

    Parameters
    ----------
    output
        Image build directory.
    plan
        Compiler and build inputs of the image.
    toolchain
        Admitted compiler identity.
    commands
        Compile commands to preprocess.
    rust_kernel
        Whether the Rust kernel replaces the C controller.
    """
    records = preprocess_image(output, commands)
    dependencies = image_dependency_hashes(records, output)
    snapshot_image_dependencies(output, dependencies)
    inputs = [path for path in output.rglob("*") if path.is_file()]
    (output / "preparation.json").write_bytes(
        canonical_json_bytes(
            {
                "schema": "loop-timing-witness.amp-image-preparation.v1",
                "isa": plan.build.isa,
                **({"kernel_backend": "rust"} if rust_kernel else {}),
                "compiler": str(plan.compiler),
                "compiler_sha256": sha256_of_file(plan.compiler),
                "toolchain": toolchain,
                "compiler_dependencies": dependencies,
                "dependency_records": {
                    str(path.relative_to(output)): sha256_of_file(path) for path in records
                },
                "inputs": {
                    str(path.relative_to(output)): sha256_of_file(path) for path in sorted(inputs)
                },
            }
        )
    )


def prepare_image(build: BuildInputs, output: Path, request: ImageRequest) -> Path:
    """Freeze original inputs and create the actual strict compiler and validation build.

    Parameters
    ----------
    build
        Explicit original files, source checkout, compiler and target exit mode.
    output
        New exclusive image build directory.
    request
        Explicit original resource and stack selection.

    Returns
    -------
    Path
        Generated Makefile; running make in its directory compiles and verifies the image.

    Raises
    ------
    OSError
        If original inputs, executable or exclusive output cannot be accessed.
    ValueError
        If topology, run, executable or literal build arguments violate admission.
    """
    compiler = _checked_compiler(build.compiler)
    dtb_bytes, run_bytes = build.dtb.read_bytes(), build.configuration.read_bytes()
    platform = bind_platform(
        decode_device_tree(dtb_bytes), request.memory, request.device_path, request.plic
    )
    run = read_amp_run(run_bytes)
    exit_path = "runtime/isa/amp_exit.c" if build.isa else "runtime/bare_metal/amp_exit.c"
    plan = _ImagePlan(
        compiler, _image_sources(exit_path, build), platform.memory.firmware, request, build
    )
    quote_recipe([str(compiler)])
    toolchain = compiler_identity(str(compiler), "cc1")
    output.mkdir()
    snapshot_runtime(output, toolchain["runtime_libraries"])
    (output / "objects").mkdir()
    _copy_originals(build.root, output, exit_path)
    snapshot_verifier_package(build.root, output)
    _write_target(output, dtb_bytes, run_bytes, render_contract(platform, run))
    rust = (
        prepare_rust_sources(build.root, output, build.rust_compiler)
        if build.rust_compiler is not None
        else None
    )
    makefile, commands = _write_build(output, plan, rust)
    _write_preparation(output, plan, toolchain, commands, rust_kernel=rust is not None)
    return makefile


def main(argv: list[str] | None = None) -> int:
    """Prepare one admitted firmware image build through the public command line.

    Parameters
    ----------
    argv
        Explicit arguments or process arguments.

    Returns
    -------
    int
        Zero after source preparation, one after a retained input/preparation refusal.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    add_image_arguments(parser)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--compiler", required=True, type=Path)
    parser.add_argument("--isa", action="store_true")
    parser.add_argument("--rust-compiler", help="original Rust selector for the arithmetic kernel")
    args = parser.parse_args(argv)
    try:
        path = prepare_image(
            BuildInputs(
                ROOT, args.dtb, args.configuration, args.compiler, args.isa, args.rust_compiler
            ),
            args.output,
            image_request(args),
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"AMP image preparation: FAIL: {error}", file=sys.stderr)
        return 1
    print(f"AMP image preparation: PASS: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
