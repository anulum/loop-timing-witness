# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — fail-closed local gate orchestrator

"""Run every local gate of this repository and fail closed on any defect.

The gate plan mirrors ``VALIDATION.md``. Python tools and ``typos`` run from
the repository's own ``.venv``, installed from the hashed lock; ``typos`` must
also report its pinned version. Go-built tools (``actionlint``, ``gitleaks``)
must be the exact pinned module version with the pinned module checksum, read
from the binary's build information with ``go version -m``. A gate whose tool
is missing, cannot run or reports a different version fails: a missing gate
is never a pass.

The secret scan copies exactly the publishable files (tracked, or untracked
and not ignored) into a temporary directory and scans that copy, so ignored
content such as the virtual environment is neither scanned nor published.

With ``--only NAME`` a single gate runs; ``--list`` prints the plan.
"""

from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from repository_files import candidate_files

if TYPE_CHECKING:
    from collections.abc import Callable

REGISTRY_RELATIVE_TO_MONOREPO: Final = Path("agentic-shared/memory/projects/project_registry.json")
ACTIONLINT_MODULE: Final = (
    "github.com/rhysd/actionlint",
    "v1.7.12",
    "h1:vQ4GeJN86C0QH+gTUQcs8McmK62OLT3kmakPMtEWYnY=",
)
GITLEAKS_MODULE: Final = (
    "github.com/zricethezav/gitleaks/v8",
    "v8.30.1",
    "h1:PmEvCfVI7ti9dV3s5aMZUY7sS2GxRvG3yzih7E+cS3w=",
)
TYPOS_VERSION: Final = "typos-cli 1.50.3"


@dataclass(frozen=True, slots=True)
class GateResult:
    """Outcome of one gate.

    Attributes
    ----------
    name
        Gate identifier from the plan.
    passed
        Whether the gate succeeded.
    detail
        Tool output or failure context; empty when a command passed silently.
    """

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class Gate:
    """One named gate of the plan.

    Attributes
    ----------
    name
        Gate identifier.
    description
        The command line the gate runs, or a description of an internal gate.
    run
        Callable that executes the gate and returns its result.
    """

    name: str
    description: str
    run: Callable[[], GateResult]


def run_command(name: str, command: list[str], root: Path) -> GateResult:
    """Run one command with fail-closed semantics.

    Parameters
    ----------
    name
        Gate identifier.
    command
        Argument vector, executed without a shell.
    root
        Working directory.

    Returns
    -------
    GateResult
        Passed only when the command started and exited with status zero.
    """
    try:
        completed = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
    except OSError as exc:
        return GateResult(name, passed=False, detail=f"cannot execute {command[0]}: {exc}")
    output = (completed.stdout + completed.stderr).strip()
    if completed.returncode != 0:
        return GateResult(name, passed=False, detail=output or f"exit {completed.returncode}")
    return GateResult(name, passed=True, detail=output)


def go_module_finding(executable: str, module: tuple[str, str, str], root: Path) -> str | None:
    """Verify a Go-built executable against its pinned module build information.

    Parameters
    ----------
    executable
        Command name resolved on ``PATH``.
    module
        Module path, version and ``h1:`` checksum the binary must record.
    root
        Working directory for ``go version -m``.

    Returns
    -------
    str or None
        A failure description, or ``None`` when the binary records exactly
        the pinned module line.
    """
    resolved = shutil.which(executable)
    if resolved is None:
        return f"{executable} is not on PATH"
    report = run_command("go-version", ["go", "version", "-m", resolved], root)
    if not report.passed:
        return f"cannot read build information of {resolved}: {report.detail}"
    expected = "\t".join(("mod", *module))
    if expected not in (line.strip() for line in report.detail.splitlines()):
        return f"{resolved} is not {module[0]} {module[1]} with checksum {module[2]}"
    return None


def pinned_go_tool_gate(
    name: str, module: tuple[str, str, str], command: list[str], root: Path
) -> GateResult:
    """Run a Go-built tool after proving its pinned build.

    Parameters
    ----------
    name
        Gate identifier.
    module
        Pinned module path, version and checksum.
    command
        Tool invocation; ``command[0]`` is the executable name.
    root
        Working directory.

    Returns
    -------
    GateResult
        Failure when the provenance check or the tool fails.
    """
    finding = go_module_finding(command[0], module, root)
    if finding is not None:
        return GateResult(name, passed=False, detail=finding)
    return run_command(name, command, root)


def typos_gate(root: Path) -> GateResult:
    """Run the typographical checker after proving its pinned version.

    Parameters
    ----------
    root
        Repository root.

    Returns
    -------
    GateResult
        Failure when the version differs or the checker reports a typo.
    """
    typos = str(root / ".venv" / "bin" / "typos")
    version = run_command("typos", [typos, "--version"], root)
    if not version.passed or version.detail != TYPOS_VERSION:
        return GateResult(
            "typos", passed=False, detail=f"expected {TYPOS_VERSION!r}, got {version.detail!r}"
        )
    return run_command("typos", [typos], root)


def secret_scan_gate(root: Path) -> GateResult:
    """Scan a copy of exactly the publishable files for secrets.

    Parameters
    ----------
    root
        Repository root.

    Returns
    -------
    GateResult
        Failure when the file listing, the provenance check or the scan fails.
    """
    finding = go_module_finding("gitleaks", GITLEAKS_MODULE, root)
    if finding is not None:
        return GateResult("secrets", passed=False, detail=finding)
    try:
        files = candidate_files(root)
    except RuntimeError as exc:
        return GateResult("secrets", passed=False, detail=str(exc))
    with tempfile.TemporaryDirectory(prefix="publishable-") as scratch:
        copy_root = Path(scratch)
        for relative in files:
            destination = copy_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / relative, destination)
        result = run_command(
            "secrets",
            ["gitleaks", "dir", "--no-banner", "--redact", "--exit-code", "1", str(copy_root)],
            root,
        )
    return GateResult(
        "secrets", passed=result.passed, detail=f"{len(files)} files scanned; {result.detail}"
    )


def monorepo_registry(root: Path) -> Path | None:
    """Locate the canonical project registry above a repository root.

    Parameters
    ----------
    root
        Repository root to search upward from.

    Returns
    -------
    Path or None
        The first registry file found walking the parent chain, or ``None``
        in a standalone checkout.
    """
    for parent in root.resolve().parents:
        candidate = parent / REGISTRY_RELATIVE_TO_MONOREPO
        if candidate.is_file():
            return candidate
    return None


def build_plan(root: Path) -> list[Gate]:
    """Build the ordered gate plan for one repository root.

    Parameters
    ----------
    root
        Repository root the gates run against.

    Returns
    -------
    list[Gate]
        Gates in execution order.
    """
    venv = root / ".venv" / "bin"
    python = str(venv / "python")

    def command(name: str, argv: list[str]) -> Gate:
        return Gate(name, shlex.join(argv), lambda: run_command(name, argv, root))

    validator = [python, "tools/validate_measurement_domain.py"]
    registry = monorepo_registry(root)
    if registry is not None:
        validator += ["--registry", str(registry)]
    return [
        command("ruff-check", [str(venv / "ruff"), "check", "."]),
        command("ruff-format", [str(venv / "ruff"), "format", "--check", "."]),
        command("mypy", [str(venv / "mypy")]),
        command("controller-build", ["make", "controller-build"]),
        command("controller-tests", ["make", "controller-tests"]),
        command(
            "tests",
            [
                str(venv / "pytest"),
                "--cov",
                "--cov-branch",
                "--cov-report=term-missing",
                "--cov-fail-under=100",
            ],
        ),
        command("measurement-domain", validator),
        command(
            "capability-inventory", [python, "tools/generate_capability_inventory.py", "--check"]
        ),
        command("provenance-headers", [python, "tools/check_provenance_headers.py"]),
        command("documentation", [python, "tools/check_documentation.py"]),
        command("dependency-licences", [python, "tools/check_dependency_licences.py"]),
        command("workflows", [python, "tools/audit_workflows.py"]),
        command("reuse", [str(venv / "reuse"), "lint"]),
        command(
            "zizmor",
            [
                str(venv / "zizmor"),
                "--offline",
                "--persona",
                "pedantic",
                "--strict-collection",
                ".",
            ],
        ),
        Gate(
            "actionlint",
            f"actionlint (build {ACTIONLINT_MODULE[0]} {ACTIONLINT_MODULE[1]} verified)",
            lambda: pinned_go_tool_gate("actionlint", ACTIONLINT_MODULE, ["actionlint"], root),
        ),
        Gate(
            "typos",
            f"{venv / 'typos'} (version {TYPOS_VERSION!r} verified)",
            lambda: typos_gate(root),
        ),
        Gate(
            "secrets",
            f"gitleaks dir on a copy of the publishable files (build {GITLEAKS_MODULE[1]} "
            "verified)",
            lambda: secret_scan_gate(root),
        ),
    ]


def run_gates(root: Path, only: str | None) -> int:
    """Run the plan, or one gate of it, and report a fail-closed aggregate.

    Parameters
    ----------
    root
        Repository root.
    only
        Optional single gate name.

    Returns
    -------
    int
        ``0`` when every selected gate passes, ``1`` when any fails, ``2``
        when ``only`` names no gate.
    """
    plan = build_plan(root)
    selected = [gate for gate in plan if only is None or gate.name == only]
    if not selected:
        print(f"preflight: unknown gate {only!r}; gates: {', '.join(gate.name for gate in plan)}")
        return 2
    failures = 0
    for gate in selected:
        result = gate.run()
        print(f"preflight: {'PASS' if result.passed else 'FAIL'} {gate.name}")
        if not result.passed:
            failures += 1
            print(f"  {result.detail}")
    if failures:
        print(f"preflight: FAIL gates_failed={failures} of {len(selected)}")
        return 1
    print(f"preflight: PASS gates={len(selected)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the preflight command-line interface.

    Parameters
    ----------
    argv
        Argument vector without the program name; ``None`` reads
        ``sys.argv``.

    Returns
    -------
    int
        Aggregate status from :func:`run_gates`, or ``0`` after ``--list``.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--only", default=None, help="run a single gate")
    selection.add_argument("--list", action="store_true", help="print the gate plan")
    args = parser.parse_args(argv)
    if args.list:
        for gate in build_plan(args.root):
            print(f"{gate.name}: {gate.description}")
        return 0
    return run_gates(args.root, args.only)


if __name__ == "__main__":
    sys.exit(main())
