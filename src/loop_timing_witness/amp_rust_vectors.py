# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — explicit original RV64 Rust compiler argument vectors

"""Construct fixed RV64 compiler vectors independently of ambient Cargo configuration."""

from pathlib import Path

TARGET = "riscv64imac-unknown-none-elf"
LIBRARY = "objects/rust/libwitness_amp_rust_kernel.a"
CORE = "controllers/rust"
ADAPTER = "runtime/bare_metal/rust_kernel"


def rust_vectors(compiler: str, *, metadata: bool) -> list[list[str]]:
    """Construct complete literal Rust compiler vectors without ambient Cargo configuration.

    Parameters
    ----------
    compiler
        Original absolute compiler executable from the admitted sysroot.
    metadata
        Type-check metadata before any object, or compile the actual original libraries.

    Returns
    -------
    list of list of str
        Ordered core-library and adapter vectors, with explicit target, sysroot and release flags.
    """
    prefix = [
        compiler,
        "--edition=2024",
        "--target",
        TARGET,
        "--sysroot",
        str(Path(compiler).parent.parent),
        "-C",
        "panic=abort",
        "-C",
        "opt-level=3",
        "-C",
        "overflow-checks=yes",
        "-C",
        "codegen-units=1",
        "-D",
        "warnings",
        "-D",
        "missing_docs",
        "-D",
        "improper_ctypes",
        "-D",
        "improper_ctypes_definitions",
    ]
    output = "rust_metadata" if metadata else "objects/rust"
    suffix = "rmeta" if metadata else "rlib"
    core = f"{output}/libwitness_controller.{suffix}"
    emit = "metadata" if metadata else "link"
    first = [
        *prefix,
        "--crate-name",
        "witness_controller",
        "--crate-type",
        "rlib",
        "-D",
        "unsafe_code",
        "--emit",
        f"{emit},dep-info={output}/core.d",
        f"source/{CORE}/src/lib.rs",
        "-o",
        core,
    ]
    second = [
        *prefix,
        "--crate-name",
        "witness_amp_rust_kernel",
        "--crate-type",
        "staticlib",
        "-D",
        "unsafe_op_in_unsafe_fn",
        "--extern",
        f"witness_controller={core}",
        "--emit",
        f"{emit},dep-info={output}/adapter.d",
        f"source/{ADAPTER}/src/lib.rs",
        "-o",
        f"{output}/libwitness_amp_rust_kernel.{'rmeta' if metadata else 'a'}",
    ]
    return [first, second]
