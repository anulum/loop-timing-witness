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
    root, dtb, configuration = build.root, build.dtb, build.configuration
    compiler = build.compiler.resolve()
    if not compiler.is_file() or not os.access(compiler, os.X_OK):
        message = "firmware compiler must be an actual executable file"
        raise ValueError(message)
    dtb_bytes, run_bytes = dtb.read_bytes(), configuration.read_bytes()
    platform = bind_platform(
        decode_device_tree(dtb_bytes), request.memory, request.device_path, request.plic
    )
    run = read_amp_run(run_bytes)
    exit_path = "runtime/isa/amp_exit.c" if build.isa else "runtime/bare_metal/amp_exit.c"
    sources = [
        "runtime/bare_metal/entry.S",
        "runtime/bare_metal/amp_controller.c",
        exit_path,
        "controllers/c/witness_controller.c",
        "contract.c",
    ]
    if build.rust_compiler is not None:
        sources.remove("controllers/c/witness_controller.c")
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
    quote_recipe([str(compiler)])
    toolchain = compiler_identity(str(compiler), "cc1")
    output.mkdir()
    snapshot_runtime(output, toolchain["runtime_libraries"])
    (output / "objects").mkdir()
    for name in sorted(set(originals)):
        destination = output / "source" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, destination)
    snapshot_verifier_package(root, output)
    (output / "platform.dtb").write_bytes(dtb_bytes)
    (output / "configuration.txt").write_bytes(run_bytes)
    (output / "contract.c").write_text(render_contract(platform, run), encoding="utf-8")
    rust = (
        prepare_rust_sources(root, output, build.rust_compiler)
        if build.rust_compiler is not None
        else None
    )
    rules = [
        *(root / "Makefile").read_text(encoding="utf-8").splitlines()[:7],
        ".PHONY: all verify verify-inputs",
        "all: verify",
        "",
    ]
    compile_rules, objects, commands = c_compile_rules(str(compiler), sources)
    rules.extend(compile_rules)
    if rust is not None:
        rust_rules, library = rust_compile_rules(rust["toolchain"]["compiler"]["path"])
        rules.extend(rust_rules)
        objects.append(library)
    firmware = platform.memory.firmware
    link = [
        str(compiler),
        *FLAGS,
        "-nostdlib",
        "-nostartfiles",
        "-static",
        "-no-pie",
        "-Wl,--build-id=none",
        f"-Wl,--defsym=__witness_ram_origin={firmware.address}",
        f"-Wl,--defsym=__witness_ram_length={firmware.size}",
        f"-Wl,--defsym=__witness_stack_size={request.memory.stack_bytes}",
        "-T",
        "source/runtime/bare_metal/firmware.ld",
        *objects,
        "-o",
        "firmware.elf",
    ]
    verify = [
        str(Path(sys.executable).absolute()),
        "source/tools/verify_amp_image.py",
        "--directory",
        ".",
        *verification_arguments(request),
    ]
    precheck = [
        str(Path(sys.executable).absolute()),
        "source/tools/verify_amp_preparation.py",
        "--directory",
        ".",
    ]
    rules.extend(
        [
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
    )
    makefile = output / "Makefile"
    makefile.write_text("\n".join(rules), encoding="utf-8")
    (output / "build_commands.json").write_bytes(
        canonical_json_bytes(
            {"compile": commands, "link": link, "verify": verify, "precheck": precheck}
        )
    )
    records = preprocess_image(output, commands)
    dependencies = image_dependency_hashes(records, output)
    snapshot_image_dependencies(output, dependencies)
    inputs = [path for path in output.rglob("*") if path.is_file()]
    (output / "preparation.json").write_bytes(
        canonical_json_bytes(
            {
                "schema": "loop-timing-witness.amp-image-preparation.v1",
                "isa": build.isa,
                **({"kernel_backend": "rust"} if rust is not None else {}),
                "compiler": str(compiler),
                "compiler_sha256": sha256_of_file(compiler),
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
