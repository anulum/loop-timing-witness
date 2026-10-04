# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — source enrolment in executable repository checks

"""Refuse publishable source that falls outside the registered check scopes.

The catalogue binds maintained paths to existing preflight gates. It does not
measure native coverage or replace compilation, tests or domain validation.
Python scopes must also match the strict typing and coverage configuration.
Tracked and new non-ignored files are checked before staging.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

from preflight import build_plan
from repository_files import candidate_files

LANGUAGES: Final = {
    ".py": "python",
    ".c": "c",
    ".h": "headers",
    ".hpp": "headers",
    ".hh": "headers",
    ".cpp": "cxx",
    ".cc": "cxx",
    ".cxx": "cxx",
    ".rs": "rust",
    ".sv": "rtl",
    ".svh": "rtl",
    ".v": "rtl",
    ".vhd": "vhdl",
    ".vhdl": "vhdl",
    ".sh": "shell",
    ".tcl": "tcl",
    ".S": "assembly",
    ".s": "assembly",
    ".ld": "linker",
    ".dts": "device_tree",
    ".dtsi": "device_tree",
    ".ys": "yosys",
    ".mk": "make",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".java": "java",
    ".jl": "julia",
    ".lean": "lean",
    ".cu": "cuda",
    ".cuh": "cuda",
    ".f": "fortran",
    ".f90": "fortran",
    ".rb": "ruby",
    ".lua": "lua",
}
SOURCE_NAMES: Final = {"Makefile": "make", "Doxyfile": "doxygen"}
COVERAGE_THRESHOLD: Final = 100
PYTHON_CHECKS: Final = frozenset({"ruff-check", "ruff-format", "mypy", "tests"})
LANGUAGE_CHECKS: Final = {
    "python": PYTHON_CHECKS,
    "c": frozenset({"controller-build", "controller-tests", "tests", "native-format"}),
    "headers": frozenset({"controller-build", "tests", "native-format"}),
    "rust": frozenset({"controller-build", "controller-tests", "tests"}),
    "cxx": frozenset({"tests", "native-format"}),
    "rtl": frozenset({"tests"}),
    "shell": frozenset({"tests"}),
    "tcl": frozenset({"tests"}),
    "assembly": frozenset({"tests"}),
    "linker": frozenset({"tests"}),
    "device_tree": frozenset({"tests"}),
    "yosys": frozenset({"tests"}),
    "make": frozenset({"controller-build", "tests"}),
    "doxygen": frozenset({"controller-build", "documentation", "tests"}),
}
PYTHON_ROOTS: Final = ("src/loop_timing_witness", "tools", "tests")
PYTHON_PATHS: Final = ("conftest.py", "controller_test_support.py")
RUST_CHANNEL: Final = "1.99.0"
RUST_MANIFESTS: Final = (
    "controllers/rust/Cargo.toml",
    "runtime/bare_metal/rust_kernel/Cargo.toml",
)


@dataclass(frozen=True, slots=True)
class SourceProfile:
    """Paths enrolled in the executable gates for one source language.

    Attributes
    ----------
    checks
        Actual preflight gate identifiers.
    roots
        Enrolled source directories, relative to the repository root.
    paths
        Individually enrolled source files.
    """

    checks: tuple[str, ...]
    roots: tuple[str, ...]
    paths: tuple[str, ...]


def _strings(value: object, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        message = f"{label}: must be an array of non-empty strings"
        raise ValueError(message)
    result = tuple(item for item in value if isinstance(item, str))
    if (not result and not allow_empty) or len(set(result)) != len(result):
        message = f"{label}: empty or repeated entries are not allowed"
        raise ValueError(message)
    return result


def _language(relative: str) -> str | None:
    path = PurePosixPath(relative)
    return LANGUAGES.get(path.suffix, SOURCE_NAMES.get(path.name))


def _relative(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        bool(path.parts)
        and not path.is_absolute()
        and ".." not in path.parts
        and str(path) == value
    )


def _profile(language: str, value: object, known_gates: set[str]) -> SourceProfile:
    if language not in LANGUAGE_CHECKS or not isinstance(value, dict):
        message = f"{language}: unknown language or invalid profile"
        raise ValueError(message)
    if set(value) != {"checks", "roots", "paths"}:
        message = f"{language}: expected checks, roots and paths"
        raise ValueError(message)
    checks = _strings(value["checks"], f"{language}.checks")
    roots = _strings(value["roots"], f"{language}.roots", allow_empty=True)
    paths = _strings(value["paths"], f"{language}.paths", allow_empty=True)
    if set(checks) - known_gates:
        message = f"{language}: unknown checks {sorted(set(checks) - known_gates)}"
        raise ValueError(message)
    if not LANGUAGE_CHECKS[language].issubset(checks):
        message = f"{language}: required executable checks cannot be removed"
        raise ValueError(message)
    if not roots and not paths:
        message = f"{language}: no source paths enrolled"
        raise ValueError(message)
    if not all(_relative(path) for path in (*roots, *paths)):
        message = f"{language}: paths must be canonical repository-relative paths"
        raise ValueError(message)
    return SourceProfile(checks, roots, paths)


def load_profiles(root: Path) -> dict[str, SourceProfile]:
    """Read and validate the source catalogue against the actual gate plan.

    Parameters
    ----------
    root
        Repository containing ``source-gates.toml``.

    Returns
    -------
    dict[str, SourceProfile]
        Validated language profiles.

    Raises
    ------
    OSError
        If the catalogue cannot be read.
    ValueError
        If TOML, schema, paths or gate identifiers are invalid.
    """
    document = tomllib.loads((root / "source-gates.toml").read_text(encoding="utf-8"))
    if (
        set(document) != {"schema_version", "profiles"}
        or type(document["schema_version"]) is not int
    ):
        message = "catalogue: expected schema_version and profiles"
        raise ValueError(message)
    if document["schema_version"] != 1 or not isinstance(document["profiles"], dict):
        message = "catalogue: unsupported schema or invalid profiles"
        raise ValueError(message)
    known_gates = {gate.name for gate in build_plan(root)}
    profiles: dict[str, SourceProfile] = {}
    for language, value in document["profiles"].items():
        profiles[language] = _profile(language, value, known_gates)
    if "python" not in profiles:
        message = "python: required profile is missing"
        raise ValueError(message)
    return profiles


def _python_findings(root: Path, profile: SourceProfile) -> list[str]:
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["tool"]
    findings = []
    if profile.roots != PYTHON_ROOTS or profile.paths != PYTHON_PATHS:
        findings.append(
            "python: enrolment must include the maintained package, tools, tests and support"
        )
    if set(profile.checks) != PYTHON_CHECKS:
        findings.append("python: lint, formatting, strict typing and tests are all required")
    mypy = config["mypy"]
    if mypy["strict"] is not True or mypy["files"] != ["src", "tools", "tests", *PYTHON_PATHS]:
        findings.append("python: strict typing must cover every enrolled source")
    ruff = config["ruff"]
    if ruff["lint"]["select"] != ["ALL"] or ruff["lint"]["pydocstyle"]["convention"] != "numpy":
        findings.append("python: all lint groups and NumPy public docstrings are required")
    if ruff.get("extend-exclude", []) != ["docs/internal"] or "exclude" in ruff:
        findings.append("python: maintained files cannot be excluded from lint or formatting")
    coverage = config["coverage"]
    if coverage["run"]["source"] != [*PYTHON_ROOTS[:2], "controller_test_support"]:
        findings.append(
            "python: coverage must include the maintained package, tools and build support"
        )
    if (
        coverage["run"]["branch"] is not True
        or coverage["report"]["fail_under"] != COVERAGE_THRESHOLD
        or "omit" in coverage["run"]
        or "omit" in coverage["report"]
        or "include" in coverage["run"]
        or "include" in coverage["report"]
        or "exclude_lines" in coverage["report"]
        or "exclude_also" in coverage["report"]
    ):
        findings.append("python: the statement and branch coverage threshold must remain 100")
    return findings


def _rust_findings(root: Path) -> list[str]:
    toolchain = tomllib.loads((root / "rust-toolchain.toml").read_text(encoding="utf-8"))
    findings = []
    if toolchain != {
        "toolchain": {
            "channel": RUST_CHANNEL,
            "profile": "minimal",
            "components": ["rustfmt", "clippy"],
        }
    }:
        findings.append("rust: compiler, minimal profile and static checks must match the pin")
    for relative in RUST_MANIFESTS:
        manifest = tomllib.loads((root / relative).read_text(encoding="utf-8"))
        if manifest["package"]["rust-version"] != RUST_CHANNEL:
            findings.append(f"{relative}: Rust version differs from the compiler pin")
    return findings


def audit(root: Path) -> list[str]:
    """Check the full publishable source candidate against its registered scopes.

    Parameters
    ----------
    root
        Actual Git work tree, including new non-ignored source.

    Returns
    -------
    list[str]
        Catalogue, configuration or source-enrolment findings; empty on success.
    """
    try:
        profiles = load_profiles(root)
        files = candidate_files(root)
        findings = _python_findings(root, profiles["python"])
        findings.extend(_rust_findings(root))
    except (OSError, UnicodeError, ValueError, RuntimeError, KeyError, TypeError):
        return ["source catalogue, Git listing or language configuration is missing or invalid"]
    for language, profile in profiles.items():
        for relative in profile.paths:
            if relative not in files or _language(relative) != language:
                findings.append(f"{relative}: enrolled path is absent or has the wrong language")
        for relative in profile.roots:
            if not (root / relative).is_dir():
                findings.append(f"{relative}: enrolled source root is absent")
    for relative in files:
        source_language = _language(relative)
        if source_language is None:
            continue
        matches = [
            name
            for name, profile in profiles.items()
            if relative in profile.paths
            or (
                name == source_language
                and any(PurePosixPath(relative).is_relative_to(path) for path in profile.roots)
            )
        ]
        if matches != [source_language]:
            findings.append(
                f"{relative}: source must belong to exactly one {source_language} profile"
            )
    return findings


def main(argv: list[str] | None = None) -> int:
    """Run source enrolment through the public command-line interface.

    Parameters
    ----------
    argv
        Arguments without the executable; ``None`` reads ``sys.argv``.

    Returns
    -------
    int
        Zero for an admitted candidate, one for any invalid scope or source.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    findings = audit(args.root)
    for finding in findings:
        print(f"source-gates: FAIL {finding}")
    if findings:
        return 1
    print("source-gates: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
