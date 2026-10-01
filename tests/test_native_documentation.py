# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — strict real C and Rust documentation builds

"""Verify native documentation and refuse omissions in actual public interfaces."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import TYPE_CHECKING

from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from pathlib import Path


def test_doxygen_refuses_an_undocumented_actual_mailbox_member(tmp_path: Path) -> None:
    """Removing one real field description fails the same strict Doxygen configuration."""
    original = (REPOSITORY_ROOT / "runtime/bare_metal/amp_contract.h").read_text()
    documented = (
        "/** @var witness_amp_mailbox::status\n"
        " * Monotonic firmware lifecycle state from witness_amp_status.\n */"
    )
    assert documented in original
    header = tmp_path / "amp_contract.h"
    header.write_text(original.replace(documented, ""))
    configuration = (REPOSITORY_ROOT / "Doxyfile").read_text()
    configuration += f'\nINPUT = "{header}"\nOUTPUT_DIRECTORY = "{tmp_path / "reference"}"\n'
    config = tmp_path / "Doxyfile"
    config.write_text(configuration)
    binary = REPOSITORY_ROOT / ".venv/native/doxygen/doxygen-1.18.0/bin/doxygen"
    result = subprocess.run(
        [str(binary), str(config)], capture_output=True, text=True, check=False, timeout=30
    )
    assert result.returncode != 0
    assert "Member status" in result.stderr
    assert "warning treated as error" in result.stderr


def test_rustdoc_refuses_an_undocumented_actual_command_member(tmp_path: Path) -> None:
    """The actual packaged arithmetic interface denies missing public documentation."""
    source = REPOSITORY_ROOT / "controllers/rust"
    crate = tmp_path / "controller"
    shutil.copytree(source, crate, ignore=shutil.ignore_patterns("target"))
    library = crate / "src/lib.rs"
    text = library.read_text()
    documented = "    /// Saturated actuator command.\n"
    assert documented in text
    library.write_text(text.replace(documented, ""))
    environment = dict(os.environ, RUSTDOCFLAGS="-D warnings -D rustdoc::broken_intra_doc_links")
    result = subprocess.run(
        [
            "cargo",
            "doc",
            "--offline",
            "--locked",
            "--no-deps",
            "--manifest-path",
            str(crate / "Cargo.toml"),
            "--target-dir",
            str(tmp_path / "rustdoc"),
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode != 0
    assert "missing documentation for a struct field" in result.stderr


def test_actual_native_reference_includes_members_and_enum_values() -> None:
    """The complete strict build publishes real mailbox fields and controller states."""
    native = REPOSITORY_ROOT / "build/native-api"
    pages = list((native / "c/html").glob("*.html"))
    assert pages
    rendered = "\n".join(page.read_text() for page in pages)
    assert "Monotonic firmware lifecycle state" in rendered
    assert "Terminal refusal" in rendered
    assert (native / "rust/doc/witness_controller/struct.Command.html").is_file()
    assert (native / "rust/doc/witness_amp_rust_kernel/index.html").is_file()
