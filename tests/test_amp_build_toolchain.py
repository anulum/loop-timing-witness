# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original ISA logger completion and corruption regression tests

"""Introspect actual installed compilers and refuse unavailable selected subprograms."""

from __future__ import annotations

import re
import struct
import subprocess
from pathlib import Path

import pytest
from amp_build_toolchain import compiler_identity, executable_path, runtime_libraries
from amp_tool_runtime import (
    PT_LOAD,
    elf_interpreter,
    library_identities,
    own_load_record,
    program_headers,
)

from loop_timing_witness.host_profile import scaled
from manifest_io import sha256_of_file


@pytest.mark.parametrize(("name", "frontend"), [("gcc", "cc1"), ("g++", "cc1plus")])
def test_actual_complete_toolchain(name: str, frontend: str) -> None:
    """Require driver, frontend, collect2, assembler and linker identity from the real GCC driver.

    Parameters
    ----------
    name
        Actual installed language driver.
    frontend
        Native compiler frontend selected by that driver.
    """
    data = compiler_identity(name, frontend)
    assert data["version"]
    assert set(data["programs"]) == {frontend, "collect2", "as", "ld"}
    for item in [data["driver"], *data["programs"].values()]:
        path = Path(item["path"])
        assert path.is_absolute()
        assert sha256_of_file(path) == item["sha256"]


def test_absent_actual_program_refused(tmp_path: Path) -> None:
    """Refuse an absent actual selected executable through public toolchain admission.

    The driver answers ``-print-prog-name`` for a program it cannot find with the name itself,
    which the build ``PATH`` must then resolve. GCC 13 answers so for the assembler and the
    linker too; GCC 15 names them absolutely, so the relative path is exercised here.

    Parameters
    ----------
    tmp_path
        Owned nonexistent selection.
    """
    with pytest.raises(ValueError, match="actual executable"):
        executable_path(str(tmp_path / "absent-gcc"))
    with pytest.raises(ValueError, match="unavailable executable"):
        compiler_identity("gcc", str(tmp_path / "absent-frontend"))
    with pytest.raises(ValueError, match=r"actual executable: absent-frontend$"):
        compiler_identity("gcc", "absent-frontend")


@pytest.mark.parametrize("name", ["gcc", "g++", "/usr/bin/perl", "/usr/bin/verilator_bin"])
def test_actual_loaded_tool_libraries(name: str) -> None:
    """Require actual loader and libc bytes selected by real native build tools.

    Parameters
    ----------
    name
        Original actual native build executable.
    """
    data = runtime_libraries([executable_path(name)])
    assert any("ld-linux" in path for path in data)
    assert any("libc.so" in path for path in data)
    for path, digest in data.items():
        assert sha256_of_file(Path(path)) == digest


@pytest.mark.parametrize(
    "fault",
    [
        "short",
        "magic",
        "table-size",
        "table-end",
        "no-interpreter",
        "record-end",
        "terminator",
        "embedded-null",
        "relative",
        "missing",
    ],
)
def test_corrupted_actual_tool_refused(tmp_path: Path, fault: str) -> None:
    """Refuse corrupted owned copies of the actual compiler before any selected loader runs.

    Parameters
    ----------
    tmp_path
        Exclusive owned compiler copy; the installed compiler remains intact.
    fault
        Damaged executable header, interpreter record or interpreter path.
    """
    content = bytearray(executable_path("gcc").read_bytes())
    offset = struct.unpack_from("<Q", content, 32)[0]
    size, count = struct.unpack_from("<HH", content, 54)
    header = next(
        offset + size * index
        for index in range(count)
        if struct.unpack_from("<I", content, offset + size * index)[0] == 3
    )
    start, length = (
        struct.unpack_from("<Q", content, header + 8)[0],
        struct.unpack_from("<Q", content, header + 32)[0],
    )
    if fault == "short":
        content = content[:32]
    elif fault == "magic":
        content[5] = 2
    elif fault == "table-size":
        struct.pack_into("<H", content, 54, size - 1)
    elif fault == "table-end":
        struct.pack_into("<Q", content, 32, len(content))
    elif fault == "no-interpreter":
        struct.pack_into("<I", content, header, 0)
    elif fault == "record-end":
        struct.pack_into("<Q", content, header + 32, len(content))
    elif fault == "terminator":
        content[start + length - 1] = 1
    elif fault == "embedded-null":
        content[start + 1] = 0
    elif fault == "relative":
        content[start] = ord(".")
    else:
        content[start + 1] = ord("z")
    selected = tmp_path / "original-gcc-copy"
    selected.write_bytes(content)
    with pytest.raises(ValueError, match="AMP native"):
        runtime_libraries([selected])


def test_disappearing_actual_loaded_library(tmp_path: Path) -> None:
    """Refuse an actual loader record if its owned interpreter disappears before hashing.

    Parameters
    ----------
    tmp_path
        Owned copy of the actual selected compiler loader.
    """
    compiler = executable_path("gcc")
    interpreter = elf_interpreter(compiler)
    owned = tmp_path / "original-loader"
    owned.write_bytes(interpreter.read_bytes())
    owned.chmod(0o700)
    listing = subprocess.check_output(
        [str(owned), "--list", str(compiler)], text=True, timeout=scaled(10)
    )
    assert str(owned) in listing
    owned.unlink()
    with pytest.raises(ValueError, match="available absolute library") as refused:
        library_identities(interpreter, listing, own_load_record(compiler))
    assert str(owned) in str(refused.value).partition("; complete listing")[0]


PIE_RECORD = "(0x00007dbb3efad000)"


@pytest.mark.parametrize("kind", ["position-dependent", "position-independent", "no-load"])
def test_own_load_record_of_owned_compiler_copy(tmp_path: Path, kind: str) -> None:
    """Require the fixed load page of a position-dependent executable, else any page.

    Parameters
    ----------
    tmp_path
        Exclusive owned compiler copy with its ELF type or segment types changed.
    kind
        Position-dependent executable, position-independent file, or one without a
        loadable segment.
    """
    content = bytearray(executable_path("gcc").read_bytes())
    headers = program_headers(bytes(content))
    loads = [header[3] for header in headers if header[0] == PT_LOAD]
    struct.pack_into("<H", content, 16, 3 if kind == "position-independent" else 2)
    offset = struct.unpack_from("<Q", content, 32)[0]
    for index, header in enumerate(headers):
        if kind == "no-load" and header[0] == PT_LOAD:
            struct.pack_into("<I", content, offset + 56 * index, 0)
    selected = tmp_path / "original-gcc-copy"
    selected.write_bytes(content)
    pattern = own_load_record(selected)
    fixed = f"(0x{min(loads) & ~0xFFF:016x})"
    assert pattern.fullmatch(fixed)
    assert bool(pattern.fullmatch(PIE_RECORD)) is (kind != "position-dependent")
    assert not pattern.fullmatch("(0x00007dbb3efad010)")


@pytest.mark.parametrize(
    ("record", "position", "pattern"),
    [
        ("(0x0000000000400000)", "first", "(0x0000000000400000)"),
        (PIE_RECORD, "first", None),
        (PIE_RECORD, "last", None),
        ("(0x0000000000400000)", "first", "(0x0000000000401000)"),
        ("(0x00007dbb3efad010)", "first", None),
        (PIE_RECORD, "absent", None),
    ],
)
def test_loader_record_of_the_listed_executable(
    tmp_path: Path, record: str, position: str, pattern: str | None
) -> None:
    """Skip the listed executable's own nameless record only first; refuse any other.

    Parameters
    ----------
    tmp_path
        Owned position-independent compiler copy whose pattern admits any page.
    record
        Nameless record added to the actual listing.
    position
        Whether the record leads or ends the listing, or no pattern is supplied at all.
    pattern
        Fixed record of a position-dependent executable, or ``None`` for the
        position-independent copy's pattern.
    """
    compiler = executable_path("gcc")
    interpreter = elf_interpreter(compiler)
    actual = subprocess.check_output(
        [str(interpreter), "--list", str(compiler)], text=True, timeout=scaled(10)
    ).splitlines(keepends=True)
    own = own_load_record(compiler)
    body = "".join(
        line for index, line in enumerate(actual) if index or not own.fullmatch(line.strip())
    )
    content = bytearray(compiler.read_bytes())
    struct.pack_into("<H", content, 16, 3)
    copy = tmp_path / "original-gcc-copy"
    copy.write_bytes(content)
    expected = re.compile(re.escape(pattern)) if pattern else own_load_record(copy)
    listing = f"\t{record}\n{body}" if position == "first" else f"{body}\t{record}\n"
    supplied = None if position == "absent" else expected
    admitted = {
        ("(0x0000000000400000)", "first", "(0x0000000000400000)"),
        (PIE_RECORD, "first", None),
    }
    if (record, position, pattern) in admitted:
        assert library_identities(interpreter, listing, supplied) == library_identities(
            interpreter, body
        )
        return
    records = " | ".join(line.strip() for line in listing.splitlines())
    with pytest.raises(ValueError, match="complete listing") as refused:
        library_identities(interpreter, listing, supplied)
    assert str(refused.value) == (
        f"AMP loader did not resolve an available absolute library: {record}; "
        f"complete listing: {records}"
    )
