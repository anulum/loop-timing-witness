# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — public source enrolment and drift controls

"""Exercise source enrolment with original repository paths and configuration."""

from __future__ import annotations

import shutil
import tomllib
from typing import TYPE_CHECKING

import pytest
from check_source_gates import main

from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import MakeGitTree, RunTool


@pytest.fixture
def source_tree(make_git_tree: MakeGitTree) -> Path:
    """Copy the original enrolled native cohort and actual Python gate inputs.

    Parameters
    ----------
    make_git_tree
        Factory for an actual Git candidate work tree.

    Returns
    -------
    Path
        Candidate containing the original catalogue, Python configuration,
        each native file and original Python files in every registered scope.
    """
    catalogue = (REPOSITORY_ROOT / "source-gates.toml").read_text(encoding="utf-8")
    profiles = tomllib.loads(catalogue)["profiles"]
    paths = {
        "source-gates.toml",
        ".clang-format",
        "pyproject.toml",
        "rust-toolchain.toml",
        "controllers/rust/Cargo.toml",
        "runtime/bare_metal/rust_kernel/Cargo.toml",
    }
    for profile in profiles.values():
        paths.update(profile["paths"])
    paths.update(
        {"src/loop_timing_witness/__init__.py", "tools/preflight.py", "tests/test_preflight.py"}
    )
    return make_git_tree(
        {relative: (REPOSITORY_ROOT / relative).read_bytes() for relative in paths}
    )


def test_original_source_catalogue_passes_the_public_cli(
    source_tree: Path, run_tool: RunTool
) -> None:
    """The original enrolled paths match real gates and strict Python scopes."""
    result = run_tool("check_source_gates", "--root", str(source_tree))
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "source-gates: PASS"


def test_public_api_reports_the_same_admitted_candidate(
    source_tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The public entry function admits the same original source cohort."""
    assert main(["--root", str(source_tree)]) == 0
    assert capsys.readouterr().out.strip() == "source-gates: PASS"


@pytest.mark.parametrize(
    ("relative", "original", "finding"),
    [
        ("alternate_package/analysis.py", "src/loop_timing_witness/__init__.py", "python profile"),
        (
            "src/alternate_package/analysis.py",
            "src/loop_timing_witness/__init__.py",
            "python profile",
        ),
        ("runtime/linux/alternate.cpp", "runtime/linux/run_uio.cpp", "cxx profile"),
        ("rtl/alternate.sv", "rtl/control_cycle.sv", "rtl profile"),
        ("rtl/alternate.vhd", "rtl/control_cycle.sv", "vhdl profile"),
        ("tests/formal/alternate.ys", "rtl/check_witness_equivalence.ys", "yosys profile"),
        ("runtime/alternate.mk", "runtime/isa/spike_plugin.mk", "make profile"),
        ("runtime/alternate.js", "runtime/linux/run_uio.cpp", "javascript profile"),
    ],
)
def test_new_untracked_source_outside_enrolment_fails(
    source_tree: Path, run_tool: RunTool, relative: str, original: str, finding: str
) -> None:
    """A real additional original source copy is seen before it is staged."""
    path = source_tree / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPOSITORY_ROOT / original, path)
    result = run_tool("check_source_gates", "--root", str(source_tree))
    assert result.returncode == 1
    assert f"{relative}: source must belong to exactly one {finding}" in result.stdout


def test_new_python_inside_the_existing_gate_scopes_is_admitted(
    source_tree: Path, run_tool: RunTool
) -> None:
    """An additional source in tools is already inside lint, typing and coverage."""
    shutil.copyfile(REPOSITORY_ROOT / "tools/check_source_gates.py", source_tree / "tools/extra.py")
    result = run_tool("check_source_gates", "--root", str(source_tree))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("schema_version = 1", "schema_version = true"),
        (
            'checks = ["controller-build", "controller-tests", "tests", "native-format"]',
            'checks = ["controller-build", "controller-tests", "tests"]',
        ),
        (
            'checks = ["controller-build", "tests", "native-format"]',
            'checks = ["controller-build", "tests"]',
        ),
        ('checks = ["tests", "native-format"]', 'checks = ["tests"]'),
        ("schema_version = 1", "schema_version = 2"),
        ('checks = ["controller-build", "controller-tests", "tests"]', 'checks = ["source-gates"]'),
        (
            'checks = ["ruff-check", "ruff-format", "mypy", "tests"]',
            'checks = ["ruff-check", "ruff-format", "mypy", "tests", "documentation"]',
        ),
        ("[profiles.python]", "[profiles.vhdl]"),
        ('checks = ["ruff-check", "ruff-format", "mypy", "tests"]', 'checks = ["mypy"]'),
        ('roots = ["src/loop_timing_witness", "tools", "tests"]', 'roots = ["."]'),
        ('paths = [\n    "runtime/bare_metal/entry.S",\n]', "paths = []"),
        ("schema_version = 1", 'schema_version = 1\nextra = "unexpected"'),
        ("[profiles.python]", "[profiles.unknown]"),
        ("[profiles.python]", 'profiles = "invalid"\n[other.python]'),
        ('checks = ["ruff-check", "ruff-format", "mypy", "tests"]', 'checks = ["absent"]'),
        ('checks = ["ruff-check", "ruff-format", "mypy", "tests"]', 'checks = "mypy"'),
        ('checks = ["ruff-check", "ruff-format", "mypy", "tests"]', "checks = [1]"),
        ('checks = ["ruff-check", "ruff-format", "mypy", "tests"]', 'checks = [""]'),
        ('checks = ["ruff-check", "ruff-format", "mypy", "tests"]', "checks = []"),
        ('checks = ["ruff-check", "ruff-format", "mypy", "tests"]', 'checks = ["mypy", "mypy"]'),
        ('roots = ["src/loop_timing_witness", "tools", "tests"]', 'roots = ["../outside"]'),
        ('roots = ["src/loop_timing_witness", "tools", "tests"]', 'roots = ["/outside"]'),
        ('roots = ["src/loop_timing_witness", "tools", "tests"]', 'roots = ["./tools"]'),
        ('roots = ["src/loop_timing_witness", "tools", "tests"]', 'roots = [""]'),
        ('roots = ["src/loop_timing_witness", "tools", "tests"]', "roots = []"),
        ('paths = ["conftest.py", "controller_test_support.py"]', "paths = []"),
        ('checks = ["ruff-check", "ruff-format", "mypy", "tests"]', "unexpected = true"),
    ],
)
def test_invalid_catalogue_is_refused_by_the_cli(
    source_tree: Path, run_tool: RunTool, before: str, after: str
) -> None:
    """Schema, field types, check identities and canonical path errors fail closed."""
    catalogue = source_tree / "source-gates.toml"
    text = catalogue.read_text(encoding="utf-8")
    assert before in text
    catalogue.write_text(text.replace(before, after, 1), encoding="utf-8")
    result = run_tool("check_source_gates", "--root", str(source_tree))
    assert result.returncode == 1
    assert "source-gates: FAIL" in result.stdout


@pytest.mark.parametrize(
    ("before", "after", "finding"),
    [
        ('"tools", "tests", "conftest.py"', '"tests", "conftest.py"', "strict typing"),
        ("strict = true", "strict = false", "strict typing"),
        ('select = ["ALL"]', 'select = ["E"]', "all lint groups"),
        ('convention = "numpy"', 'convention = "google"', "NumPy public docstrings"),
        (
            'extend-exclude = ["docs/internal"]',
            'extend-exclude = ["docs/internal", "tools"]',
            "excluded",
        ),
        ('extend-exclude = ["docs/internal"]', 'exclude = ["tools"]', "excluded"),
        (
            'source = ["src/loop_timing_witness", "tools", "controller_test_support"]',
            'source = ["tools"]',
            "coverage must include",
        ),
        ("branch = true", "branch = false", "threshold must remain 100"),
        ("fail_under = 100", "fail_under = 99", "threshold must remain 100"),
        *[
            (section, section + "\n" + option + ' = [".*"]', "threshold must remain 100")
            for section, option in (
                ("[tool.coverage.run]", "omit"),
                ("[tool.coverage.report]", "omit"),
                ("[tool.coverage.run]", "include"),
                ("[tool.coverage.report]", "include"),
                ("[tool.coverage.report]", "exclude_lines"),
                ("[tool.coverage.report]", "exclude_also"),
            )
        ],
    ],
)
def test_actual_python_configuration_scope_or_threshold_drift_fails(
    source_tree: Path, run_tool: RunTool, before: str, after: str, finding: str
) -> None:
    """Removing actual typing, lint, format or coverage enforcement is refused."""
    config = source_tree / "pyproject.toml"
    text = config.read_text(encoding="utf-8")
    assert before in text
    config.write_text(text.replace(before, after, 1), encoding="utf-8")
    result = run_tool("check_source_gates", "--root", str(source_tree))
    assert result.returncode == 1
    assert finding in result.stdout


@pytest.mark.parametrize(
    "change",
    [
        ("rust-toolchain.toml", 'channel = "1.99.0"', 'channel = "stable"', "compiler"),
        ("rust-toolchain.toml", 'profile = "minimal"', 'profile = "complete"', "minimal"),
        ("rust-toolchain.toml", '["rustfmt", "clippy"]', '["rustfmt"]', "static checks"),
        (
            "controllers/rust/Cargo.toml",
            'rust-version = "1.99.0"',
            'rust-version = "1.98.1"',
            "Rust version differs",
        ),
        (
            "runtime/bare_metal/rust_kernel/Cargo.toml",
            'rust-version = "1.99.0"',
            'rust-version = "1.98.1"',
            "Rust version differs",
        ),
    ],
)
def test_actual_rust_compiler_or_crate_pin_drift_fails(
    source_tree: Path, run_tool: RunTool, change: tuple[str, str, str, str]
) -> None:
    """A floating compiler or mismatch with either real crate cannot be admitted."""
    relative, before, after, finding = change
    path = source_tree / relative
    text = path.read_text(encoding="utf-8")
    assert before in text
    path.write_text(text.replace(before, after, 1), encoding="utf-8")
    result = run_tool("check_source_gates", "--root", str(source_tree))
    assert result.returncode == 1
    assert finding in result.stdout


@pytest.mark.parametrize(
    "relative",
    [
        "rust-toolchain.toml",
        "controllers/rust/Cargo.toml",
        "runtime/bare_metal/rust_kernel/Cargo.toml",
    ],
)
def test_missing_actual_rust_toolchain_or_crate_input_fails(
    source_tree: Path, run_tool: RunTool, relative: str
) -> None:
    """Missing compiler custody or crate requirements fail the actual public gate."""
    (source_tree / relative).unlink()
    result = run_tool("check_source_gates", "--root", str(source_tree))
    assert result.returncode == 1
    assert "language configuration is missing or invalid" in result.stdout


@pytest.mark.parametrize(
    "fault", ["missing-catalogue", "invalid-toml", "invalid-utf8", "missing-config", "not-git"]
)
def test_missing_or_unreadable_gate_inputs_fail(
    source_tree: Path, run_tool: RunTool, fault: str
) -> None:
    """Unavailable real files, malformed bytes and absent Git custody cannot pass."""
    catalogue = source_tree / "source-gates.toml"
    if fault == "missing-catalogue":
        catalogue.unlink()
    elif fault == "invalid-toml":
        catalogue.write_text("[broken", encoding="utf-8")
    elif fault == "invalid-utf8":
        catalogue.write_bytes(b"\xff")
    elif fault == "missing-config":
        (source_tree / "pyproject.toml").unlink()
    else:
        shutil.rmtree(source_tree / ".git")
    result = run_tool("check_source_gates", "--root", str(source_tree))
    assert result.returncode == 1
    assert "missing or invalid" in result.stdout


def test_deleted_enrolled_source_or_directory_fails(source_tree: Path, run_tool: RunTool) -> None:
    """An individually enrolled native source and a Python root must still exist."""
    (source_tree / "controllers/c/controller_cli.c").unlink()
    shutil.rmtree(source_tree / "tools")
    result = run_tool("check_source_gates", "--root", str(source_tree))
    assert result.returncode == 1
    assert "controllers/c/controller_cli.c: enrolled path is absent" in result.stdout
    assert "tools: enrolled source root is absent" in result.stdout


def test_wrong_language_and_overlapping_roots_fail(source_tree: Path, run_tool: RunTool) -> None:
    """An enrolled native file cannot be relabelled or accepted through two scopes."""
    catalogue = source_tree / "source-gates.toml"
    text = catalogue.read_text(encoding="utf-8")
    text = text.replace(
        '"controllers/c/witness_controller.c",', '"controllers/c/witness_controller.h",'
    )
    text = text.replace(
        '[profiles.headers]\nchecks = ["controller-build", "tests"]\nroots = []',
        '[profiles.headers]\nchecks = ["controller-build", "tests"]\nroots = ["controllers"]',
    )
    catalogue.write_text(text, encoding="utf-8")
    result = run_tool("check_source_gates", "--root", str(source_tree))
    assert result.returncode == 1
    assert "enrolled path is absent or has the wrong language" in result.stdout
    assert "source must belong to exactly one c profile" in result.stdout


@pytest.mark.parametrize("profile", ["python = 1", ""])
def test_invalid_or_empty_profile_table_fails(
    source_tree: Path, run_tool: RunTool, profile: str
) -> None:
    """A malformed language table or absence of all language scopes is refused."""
    catalogue = source_tree / "source-gates.toml"
    text = catalogue.read_text(encoding="utf-8")
    prefix, rest = text.split("[profiles.python]", 1)
    _, native = rest.split("[profiles.assembly]", 1)
    catalogue.write_text(
        prefix
        + "[profiles]\n"
        + profile
        + "\n"
        + ("[profiles.assembly]" + native if profile else ""),
        encoding="utf-8",
    )
    result = run_tool("check_source_gates", "--root", str(source_tree))
    assert result.returncode == 1
    assert "missing or invalid" in result.stdout
