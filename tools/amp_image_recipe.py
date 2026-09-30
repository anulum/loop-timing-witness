# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — literal firmware compiler vectors and Make recipes

"""Generate literal build vectors for original admitted C and Rust arithmetic sources."""

import shlex

from amp_rust_vectors import ADAPTER, CORE, LIBRARY, rust_vectors

FLAGS = [
    "-std=gnu11",
    "-O2",
    "-ffreestanding",
    "-fno-builtin",
    "-fno-pie",
    "-march=rv64imac_zicsr_zifencei",
    "-mabi=lp64",
    "-mcmodel=medany",
    "-Wall",
    "-Wextra",
    "-Werror",
    "-Wconversion",
    "-Wshadow",
    "-Wstrict-prototypes",
    "-Wmissing-prototypes",
]


def quote_recipe(arguments: list[str]) -> str:
    """Quote literal build arguments for the shell and escape Make expansion separately.

    Parameters
    ----------
    arguments
        Exact executable and argument vector.

    Returns
    -------
    str
        Literal shell command preserved through Make dollar expansion.

    Raises
    ------
    ValueError
        If an argument contains a line separator that cannot occur in one Make recipe.
    """
    if any("\n" in value or "\r" in value for value in arguments):
        message = "firmware build arguments cannot contain line separators"
        raise ValueError(message)
    return shlex.join(arguments).replace("$", "$$")


def c_compile_rules(
    compiler: str, sources: list[str]
) -> tuple[list[str], list[str], list[list[str]]]:
    """Create strict original C/assembly object recipes and complete compiler vectors.

    Parameters
    ----------
    compiler
        Absolute original admitted GCC executable.
    sources
        Complete original image translation-unit names, including generated contract.c.

    Returns
    -------
    tuple of list of str, list of str, list of list of str
        Make rules, link object names and complete ordered actual compilation vectors.
    """
    rules: list[str] = []
    objects = []
    commands = []
    for index, source in enumerate(sources):
        obj = f"objects/input_{index}.o"
        objects.append(obj)
        path = source if source == "contract.c" else "source/" + source
        command = [
            compiler,
            *FLAGS,
            "-Isource",
            "-MD",
            "-MF",
            obj + ".d",
            "-c",
            path,
            "-o",
            obj,
        ]
        commands.append(command)
        rules.extend(
            [
                f"{obj}: {path} | verify-inputs",
                "\t" + quote_recipe(command) + f" > objects/input_{index}.log 2>&1",
                "",
            ]
        )
    return rules, objects, commands


def rust_compile_rules(compiler: str) -> tuple[list[str], str]:
    """Create the safe-core and C ABI archive recipes using fixed actual Rust vectors.

    Parameters
    ----------
    compiler
        Absolute original admitted Rust compiler executable.

    Returns
    -------
    tuple of list of str and str
        Ordered Make rules and the actual archive to link after C/assembly objects.
    """
    commands = rust_vectors(compiler, metadata=False)
    core = "objects/rust/libwitness_controller.rlib"
    rules = [
        f"{core}: source/{CORE}/src/lib.rs | verify-inputs",
        "\t+" + quote_recipe(commands[0]) + " > objects/rust/core.log 2>&1",
        "",
        f"{LIBRARY}: source/{ADAPTER}/src/lib.rs {core} | verify-inputs",
        "\t+" + quote_recipe(commands[1]) + " > objects/rust/adapter.log 2>&1",
        "",
    ]
    return rules, LIBRARY
