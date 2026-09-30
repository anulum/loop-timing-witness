# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — tests of the fail-closed gate runner

"""Contract tests for the preflight runner and its tool-provenance checks.

The provenance and scan tests use the real pinned ``actionlint``, ``gitleaks``
and ``go`` executables from the search path and the ``typos`` executable of
the repository environment, exactly as the gates do.
"""

from __future__ import annotations

import secrets
import shutil
import string
import sys
from typing import TYPE_CHECKING

from conftest import REPOSITORY_ROOT, MakeGitTree, RunTool
from preflight import (
    ACTIONLINT_MODULE,
    GITLEAKS_MODULE,
    REGISTRY_RELATIVE_TO_MONOREPO,
    build_plan,
    go_module_finding,
    main,
    monorepo_registry,
    pinned_go_tool_gate,
    run_command,
    run_gates,
    secret_scan_gate,
    typos_gate,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

PLAN = [
    "ruff-check",
    "ruff-format",
    "mypy",
    "controller-build",
    "controller-tests",
    "tests",
    "measurement-domain",
    "capability-inventory",
    "provenance-headers",
    "documentation",
    "dependency-licences",
    "workflows",
    "reuse",
    "zizmor",
    "actionlint",
    "typos",
    "secrets",
]


def path_with_only(directory: Path, *executables: str) -> str:
    """Build a search path holding links to selected real executables.

    Parameters
    ----------
    directory
        Directory to hold the links.
    *executables
        Command names resolved on the current search path.

    Returns
    -------
    str
        The directory, for use as ``PATH``.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for name in executables:
        resolved = shutil.which(name)
        assert resolved is not None, name
        (directory / name).symlink_to(resolved)
    return str(directory)


def test_run_command_reports_success_and_output(tmp_path: Path) -> None:
    """A zero exit passes and keeps the combined output."""
    result = run_command("ok", [sys.executable, "-c", "print('done')"], tmp_path)
    assert (result.passed, result.detail) == (True, "done")


def test_run_command_reports_failure_output_and_silent_exit(tmp_path: Path) -> None:
    """A non-zero exit fails with its output, or with the status when silent."""
    loud = run_command(
        "loud", [sys.executable, "-c", "import sys; print('broken'); sys.exit(3)"], tmp_path
    )
    silent = run_command("silent", [sys.executable, "-c", "raise SystemExit(4)"], tmp_path)
    assert (loud.passed, loud.detail) == (False, "broken")
    assert (silent.passed, silent.detail) == (False, "exit 4")


def test_run_command_fails_closed_on_a_missing_tool(tmp_path: Path) -> None:
    """A tool that cannot be started is a failed gate."""
    result = run_command("absent", [str(tmp_path / "no-such-tool")], tmp_path)
    assert not result.passed
    assert result.detail.startswith(f"cannot execute {tmp_path / 'no-such-tool'}:")


def test_pinned_actionlint_build_is_accepted_and_runs() -> None:
    """The installed actionlint records the pinned module and passes on this repository."""
    assert go_module_finding("actionlint", ACTIONLINT_MODULE, REPOSITORY_ROOT) is None
    result = pinned_go_tool_gate("actionlint", ACTIONLINT_MODULE, ["actionlint"], REPOSITORY_ROOT)
    assert result.passed, result.detail


def test_build_of_another_module_is_refused() -> None:
    """A binary whose recorded module differs from the pin is refused."""
    finding = go_module_finding("actionlint", GITLEAKS_MODULE, REPOSITORY_ROOT)
    assert finding is not None
    assert finding.endswith(
        f"is not {GITLEAKS_MODULE[0]} {GITLEAKS_MODULE[1]} with checksum {GITLEAKS_MODULE[2]}"
    )


def test_missing_tool_or_go_toolchain_fails_the_provenance_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the tool, or without Go to read its build record, the gate fails."""
    monkeypatch.setenv("PATH", path_with_only(tmp_path / "only-actionlint", "actionlint"))
    finding = go_module_finding("actionlint", ACTIONLINT_MODULE, tmp_path)
    assert finding is not None
    assert finding.startswith("cannot read build information of")
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    result = pinned_go_tool_gate("actionlint", ACTIONLINT_MODULE, ["actionlint"], tmp_path)
    assert (result.passed, result.detail) == (False, "actionlint is not on PATH")


def test_typos_gate_passes_on_this_repository() -> None:
    """The pinned spelling checker finds nothing in the repository."""
    result = typos_gate(REPOSITORY_ROOT)
    assert result.passed, result.detail


def test_typos_gate_reports_a_misspelling_and_a_wrong_version(tmp_path: Path) -> None:
    """A misspelt word fails the gate; a different executable fails the version check."""
    root = tmp_path / "spelling"
    (root / ".venv" / "bin").mkdir(parents=True)
    (root / ".venv" / "bin" / "typos").symlink_to(REPOSITORY_ROOT / ".venv" / "bin" / "typos")
    (root / "notes.txt").write_text("the event " + "t" + "eh buffer\n", encoding="utf-8")
    misspelt = typos_gate(root)
    assert not misspelt.passed
    assert "notes.txt" in misspelt.detail
    impostor = tmp_path / "impostor"
    (impostor / ".venv" / "bin").mkdir(parents=True)
    (impostor / ".venv" / "bin" / "typos").symlink_to(sys.executable)
    wrong = typos_gate(impostor)
    assert not wrong.passed
    assert wrong.detail.startswith("expected 'typos-cli 1.50.3', got")


def test_secret_scan_passes_clean_files_and_fails_a_token(make_git_tree: MakeGitTree) -> None:
    """The scan passes a clean tree and fails when a publishable file holds a token."""
    clean = secret_scan_gate(make_git_tree({"README.md": "no secrets here\n"}))
    assert clean.passed, clean.detail
    assert clean.detail.startswith("1 files scanned;")
    token = "ghp_" + "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(36)
    )
    leaked = secret_scan_gate(make_git_tree({"config.txt": f"token = {token}\n"}))
    assert not leaked.passed
    assert token not in leaked.detail


def test_secret_scan_ignores_ignored_files(make_git_tree: MakeGitTree) -> None:
    """Content ignored by Git is neither copied nor scanned."""
    token = "ghp_" + "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(36)
    )
    root = make_git_tree({".gitignore": "local/\n", "local/env.txt": f"token = {token}\n"})
    result = secret_scan_gate(root)
    assert result.passed, result.detail


def test_secret_scan_fails_without_gitleaks_or_work_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing scanner and a directory outside Git both fail the gate."""
    outside = secret_scan_gate(tmp_path)
    assert not outside.passed
    assert "git ls-files failed" in outside.detail
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    missing = secret_scan_gate(tmp_path)
    assert (missing.passed, missing.detail) == (False, "gitleaks is not on PATH")


def test_registry_is_found_only_in_an_ancestor(tmp_path: Path) -> None:
    """The canonical registry is found above a nested repository and absent otherwise."""
    registry = tmp_path / "workspace" / REGISTRY_RELATIVE_TO_MONOREPO
    registry.parent.mkdir(parents=True)
    registry.write_text("{}", encoding="utf-8")
    nested = tmp_path / "workspace" / "03_CODE" / "GROUP" / "repositories" / "REPOSITORY"
    nested.mkdir(parents=True)
    # The temporary directory may itself be inside the canonical monorepo.
    # Its filesystem root has no ancestors and cannot inherit that registry.
    standalone = tmp_path.parents[-1]
    assert monorepo_registry(nested) == registry
    assert monorepo_registry(standalone) is None
    nested_plan = {gate.name: gate.description for gate in build_plan(nested)}
    standalone_plan = {gate.name: gate.description for gate in build_plan(standalone)}
    assert nested_plan["measurement-domain"].endswith(f"--registry {registry}")
    assert "--registry" not in standalone_plan["measurement-domain"]


def test_plan_names_every_gate_in_order(tmp_path: Path) -> None:
    """The plan matches VALIDATION.md and uses the repository's own environment."""
    plan = build_plan(tmp_path)
    assert [gate.name for gate in plan] == PLAN
    descriptions = {gate.name: gate.description for gate in plan}
    assert descriptions["ruff-check"] == f"{tmp_path / '.venv/bin/ruff'} check ."
    assert descriptions["tests"].endswith(
        "--cov --cov-branch --cov-report=term-missing --cov-fail-under=100"
    )
    assert descriptions["secrets"].startswith("gitleaks dir on a copy of the publishable files")


def test_single_gate_runs_pass_and_fail(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A selected gate passes on the repository and fails where its environment is missing."""
    assert run_gates(REPOSITORY_ROOT, "documentation") == 0
    assert capsys.readouterr().out.splitlines() == [
        "preflight: PASS documentation",
        "preflight: PASS gates=1",
    ]
    assert run_gates(tmp_path, "documentation") == 1
    output = capsys.readouterr().out
    assert "preflight: FAIL documentation" in output
    assert "cannot execute" in output
    assert output.rstrip().endswith("preflight: FAIL gates_failed=1 of 1")


def test_unknown_gate_is_a_usage_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Naming a gate that does not exist returns 2 and lists the gates."""
    assert run_gates(tmp_path, "coverage") == 2
    assert capsys.readouterr().out.startswith(
        "preflight: unknown gate 'coverage'; gates: ruff-check, "
    )


def test_full_plan_fails_closed_without_an_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every gate fails in a directory with no environment and no tools on the path."""
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert main(["--root", str(tmp_path)]) == 1
    output = capsys.readouterr().out
    assert output.count("preflight: FAIL ") == len(PLAN) + 1
    assert output.rstrip().endswith(f"preflight: FAIL gates_failed={len(PLAN)} of {len(PLAN)}")


def test_list_prints_the_plan_in_a_subprocess(run_tool: RunTool) -> None:
    """The script entry point prints one line per gate with its command."""
    completed = run_tool("preflight", "--list")
    assert completed.returncode == 0, completed.stderr
    lines = completed.stdout.splitlines()
    assert [line.split(":", 1)[0] for line in lines] == PLAN
