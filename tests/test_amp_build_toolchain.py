# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original ISA logger completion and corruption regression tests

"""Introspect actual installed compilers and refuse unavailable selected subprograms."""

from __future__ import annotations

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

    Parameters
    ----------
    tmp_path
        Owned nonexistent selection.
    """
    with pytest.raises(ValueError, match="actual executable"):
        executable_path(str(tmp_path / "absent-gcc"))
    with pytest.raises(ValueError, match="unavailable executable"):
        compiler_identity("gcc", str(tmp_path / "absent-frontend"))


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
    with pytest.raises(ValueError, match="available absolute library"):
        library_identities(interpreter, listing)


@pytest.mark.parametrize("kind", ["position-dependent", "position-independent", "no-load"])
def test_own_load_record_of_owned_compiler_copy(tmp_path: Path, kind: str) -> None:
    """Name the fixed load address of a position-dependent executable and nothing otherwise.

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
    if kind == "no-load":
        offset = struct.unpack_from("<Q", content, 32)[0]
        for index, header in enumerate(headers):
            if header[0] == PT_LOAD:
                struct.pack_into("<I", content, offset + 56 * index, 0)
    selected = tmp_path / "original-gcc-copy"
    selected.write_bytes(content)
    expected = f"(0x{min(loads) & ~0xFFF:016x})" if kind == "position-dependent" else None
    assert own_load_record(selected) == expected


@pytest.mark.parametrize("own_record", ["(0x0000000000400000)", "(0x0000000000401000)", None])
def test_loader_record_of_the_listed_executable(own_record: str | None) -> None:
    """Skip only the listed executable's own nameless record; refuse any other nameless record.

    Parameters
    ----------
    own_record
        Record the caller derived from the listed executable, or none. Only the first equals
        the nameless record at 0x400000 added to the actual listing.
    """
    compiler = executable_path("gcc")
    interpreter = elf_interpreter(compiler)
    original = subprocess.check_output(
        [str(interpreter), "--list", str(compiler)], text=True, timeout=scaled(10)
    )
    listing = original + "\t(0x0000000000400000)\n"
    if own_record == "(0x0000000000400000)":
        data = library_identities(interpreter, listing, own_record)
        assert data == library_identities(interpreter, original)
        return
    records = " | ".join(record.strip() for record in listing.splitlines())
    with pytest.raises(ValueError, match="complete listing") as refused:
        library_identities(interpreter, listing, own_record)
    assert str(refused.value) == (
        "AMP loader did not resolve an available absolute library: (0x0000000000400000); "
        f"complete listing: {records}"
    )
