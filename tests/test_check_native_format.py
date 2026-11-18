# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — real formatter and complete original native source controls

"""Exercise the pinned formatter through original source candidates and public entry points."""

from __future__ import annotations

import re
import shutil
import sys
import tomllib
from typing import TYPE_CHECKING

import pytest
from check_native_format import default_formatter, main
from test_check_source_gates import source_tree

from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import RunTool

__all__ = ["source_tree"]


@pytest.fixture
def formatter() -> str:
    """Select the actual installed pinned formatter; missing tools fail the test.

    Returns
    -------
    str
        The formatter the checker selects by default: the environment's choice or the
        hash-locked wheel installed beside this interpreter.
    """
    executable = shutil.which(default_formatter())
    assert executable is not None, "actual pinned clang-format 21.1.8 is required"
    return executable


def test_whole_original_native_source_on_public_cli(
    source_tree: Path, run_tool: RunTool, formatter: str
) -> None:
    """The real formatter accepts the complete original maintained native cohort."""
    result = run_tool("check_native_format", "--root", str(source_tree), "--formatter", formatter)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "native-format: PASS files=60"


def test_environment_selected_formatter_on_public_api(
    source_tree: Path,
    formatter: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The public environment selects the same real driver for preflight and hooks."""
    monkeypatch.setenv("WITNESS_CLANG_FORMAT", formatter)
    assert main(["--root", str(source_tree)]) == 0
    assert capsys.readouterr().out.strip() == "native-format: PASS files=60"


@pytest.mark.parametrize(
    "relative",
    [
        "controllers/c/witness_controller.c",
        "runtime/isa/spike_axi_device.cpp",
        "runtime/amp_logger.h",
    ],
)
def test_actual_native_whitespace_violation_is_refused(
    source_tree: Path, run_tool: RunTool, formatter: str, relative: str
) -> None:
    """Whitespace drift in each real C/C++/header category fails without rewriting it."""
    source = source_tree / relative
    original = source.read_text()
    assert "#include " in original
    changed = original.replace("#include ", " #include ", 1)
    source.write_text(changed)
    result = run_tool("check_native_format", "--root", str(source_tree), "--formatter", formatter)
    assert result.returncode == 1
    assert "native-format: FAIL files=60" in result.stdout
    assert "clang-format-violations" in result.stderr
    assert source.read_text() == changed


def test_missing_actual_style_cannot_use_a_fallback(
    source_tree: Path, run_tool: RunTool, formatter: str
) -> None:
    """Removing the original style fails before the formatter can choose a fallback."""
    (source_tree / ".clang-format").unlink()
    result = run_tool("check_native_format", "--root", str(source_tree), "--formatter", formatter)
    assert result.returncode == 1
    assert "repository .clang-format is missing" in result.stdout


def test_invalid_actual_style_is_refused_by_the_real_formatter(
    source_tree: Path, run_tool: RunTool, formatter: str
) -> None:
    """An unsupported style value fails the actual LLVM configuration parser."""
    style = source_tree / ".clang-format"
    original = style.read_text()
    assert "BasedOnStyle: LLVM" in original
    style.write_text(original.replace("BasedOnStyle: LLVM", "BasedOnStyle: unsupported"))
    result = run_tool("check_native_format", "--root", str(source_tree), "--formatter", formatter)
    assert result.returncode == 1
    assert "native-format: FAIL files=60" in result.stdout
    assert "Unknown value for BasedOnStyle" in result.stderr


def test_unavailable_actual_formatter_is_refused(source_tree: Path, run_tool: RunTool) -> None:
    """An absent executable fails without accepting unformatted source."""
    result = run_tool(
        "check_native_format",
        "--root",
        str(source_tree),
        "--formatter",
        str(source_tree / "absent"),
    )
    assert result.returncode == 1
    assert "native-format: FAIL" in result.stdout
    assert "No such file or directory" in result.stdout


def test_wrong_real_driver_is_refused(source_tree: Path, run_tool: RunTool) -> None:
    """The real Python version response cannot masquerade as the pinned formatter."""
    result = run_tool(
        "check_native_format", "--root", str(source_tree), "--formatter", sys.executable
    )
    assert result.returncode == 1
    assert "expected clang-format 21.1.8; received Python" in result.stdout


def test_default_formatter_is_the_locked_wheel_or_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a selection, the wheel beside the interpreter wins over ``PATH``.

    Parameters
    ----------
    tmp_path
        Directory standing in for an environment's ``bin``.
    monkeypatch
        Interpreter path and environment of this process.
    """
    monkeypatch.delenv("WITNESS_CLANG_FORMAT", raising=False)
    interpreter = tmp_path / "python"
    monkeypatch.setattr(sys, "executable", str(interpreter))
    assert default_formatter() == "clang-format"
    (tmp_path / "clang-format").write_bytes(b"")
    assert default_formatter() == str(tmp_path / "clang-format")
    monkeypatch.setenv("WITNESS_CLANG_FORMAT", "chosen-format")
    assert default_formatter() == "chosen-format"


def test_missing_enrolled_original_native_file_is_refused(
    source_tree: Path, run_tool: RunTool, formatter: str
) -> None:
    """Deleting one original enrolled header cannot shrink the formatting cohort."""
    relative = "runtime/amp_logger.h"
    (source_tree / relative).unlink()
    result = run_tool("check_native_format", "--root", str(source_tree), "--formatter", formatter)
    assert result.returncode == 1
    assert f"{relative}: enrolled path is absent" in result.stdout


def test_unenrolled_original_native_copy_is_refused(
    source_tree: Path, run_tool: RunTool, formatter: str
) -> None:
    """A new actual source copy is detected before staging and cannot escape enrollment."""
    shutil.copyfile(
        REPOSITORY_ROOT / "controllers/c/witness_controller.c", source_tree / "--dry-run.c"
    )
    result = run_tool("check_native_format", "--root", str(source_tree), "--formatter", formatter)
    assert result.returncode == 1
    assert "--dry-run.c: source must belong to exactly one c profile" in result.stdout


def test_removing_the_complete_native_cohort_is_refused(
    source_tree: Path, run_tool: RunTool, formatter: str
) -> None:
    """Removing all native profiles and their actual sources cannot produce an empty pass."""
    catalogue = source_tree / "source-gates.toml"
    original = catalogue.read_text()
    profiles = tomllib.loads(original)["profiles"]
    for language in ("c", "cxx", "headers"):
        assert not profiles[language]["roots"]
        for relative in profiles[language]["paths"]:
            (source_tree / relative).unlink()
    changed, count = re.subn(
        r"\[profiles\.(?:c|cxx|headers)\]\n.*?(?=\n\[|\Z)", "", original, flags=re.DOTALL
    )
    assert count == 3
    catalogue.write_text(changed)
    result = run_tool("check_native_format", "--root", str(source_tree), "--formatter", formatter)
    assert result.returncode == 1
    assert "no maintained C/C++ sources or headers" in result.stdout


def test_original_candidate_inside_a_path_with_spaces_is_formatted(
    source_tree: Path, tmp_path: Path, run_tool: RunTool, formatter: str
) -> None:
    """Actual Git, explicit style and native arguments retain a root containing spaces."""
    directory = tmp_path / "original source with spaces"
    source_tree.rename(directory)
    result = run_tool("check_native_format", "--root", str(directory), "--formatter", formatter)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "native-format: PASS files=60"
