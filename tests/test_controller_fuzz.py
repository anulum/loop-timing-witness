# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual coverage-guided controller fuzzing engine

"""Build the public controller fuzz target and prove that the real engine finds real defects."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from pathlib import Path

CONTROLLER = REPOSITORY_ROOT / "controllers" / "c" / "witness_controller.c"
SEEDS = sorted((REPOSITORY_ROOT / "fuzz" / "corpus").glob("*.bin"))
ASSERTION = "controller_fuzz.cpp"
DEFECTS = {
    "unsaturated-command": (
        "clamp(raw, coefficients->output_min, coefficients->output_max)",
        "(int32_t)raw",
        2,
        ASSERTION,
    ),
    "narrow-accumulator": (
        "__extension__ typedef __int128 witness_wide;",
        "typedef int64_t witness_wide;",
        1,
        "signed integer overflow",
    ),
    "mutation-before-refusal": (
        "if (!witness_coefficients_valid(coefficients)) {",
        "command->cycle = cycle;\n    if (!witness_coefficients_valid(coefficients)) {",
        2,
        ASSERTION,
    ),
    "unbounded-integral": (
        "coefficients->integral_min, coefficients->integral_max);",
        "INT32_MIN, INT32_MAX);",
        1,
        ASSERTION,
    ),
}


def campaign(directory: Path, source: Path, seconds: int) -> subprocess.CompletedProcess[str]:
    """Build one instrumented target and run one bounded campaign through the public make target.

    Parameters
    ----------
    directory
        Fresh output allocation for the object, executable, corpus copy, log and crash inputs.
    source
        Controller implementation compiled into the target.
    seconds
        Wall-clock bound of the campaign.

    Returns
    -------
    subprocess.CompletedProcess[str]
        Completed make process with the engine log on standard output.
    """
    return subprocess.run(
        [
            "make",
            "--no-print-directory",
            "controller-fuzz",
            f"FUZZ_DIRECTORY={directory}",
            f"FUZZ_SOURCE={source}",
            f"FUZZ_SECONDS={seconds}",
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


def replay(program: Path, sample: Path) -> int:
    """Execute one retained input once through an instrumented target.

    Parameters
    ----------
    program
        Instrumented fuzz target.
    sample
        Seed or retained crash input.

    Returns
    -------
    int
        Exit status of the target.
    """
    return subprocess.run(
        [str(program), str(sample)], capture_output=True, check=False, timeout=60
    ).returncode


@pytest.mark.parametrize(("variable", "compiler"), [("FUZZ_CC", "gcc"), ("FUZZ_CXX", "g++")])
def test_build_refuses_an_incompatible_compiler(
    tmp_path: Path, variable: str, compiler: str
) -> None:
    """Reject actual GCC compilers before producing a purported sanitizer target.

    Parameters
    ----------
    tmp_path
        Exclusive build allocation which must remain empty after refusal.
    variable
        Public Make variable selecting the C or C++ compiler.
    compiler
        Installed GCC executable whose version differs from the pinned Clang.
    """
    directory = tmp_path / "refused-build"
    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "controller-fuzz-build",
            f"FUZZ_DIRECTORY={directory}",
            f"{variable}={compiler}",
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode != 0
    assert ' = "18.1.3"' in result.stdout
    assert not directory.exists()


@pytest.fixture(scope="module")
def qualified(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Run a short campaign against the unmodified controller.

    Parameters
    ----------
    tmp_path_factory
        Fresh allocation for the unmodified build.

    Returns
    -------
    Path
        Directory holding the unmodified instrumented target and its campaign outputs.
    """
    directory = tmp_path_factory.mktemp("controller-fuzz")
    completed = campaign(directory, CONTROLLER, 5)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return directory


def test_unmodified_controller_survives_a_bounded_campaign(qualified: Path) -> None:
    """The real engine explores beyond the seeds and retains no crash input."""
    log = (qualified / "run.log").read_text(encoding="utf-8")
    assert "DONE" in log
    assert "ERROR" not in log
    assert list((qualified / "crashes").iterdir()) == []
    assert len(list((qualified / "corpus").iterdir())) > len(SEEDS)


def test_every_committed_seed_replays_cleanly(qualified: Path) -> None:
    """Each committed seed is a valid input of the unmodified target."""
    assert len(SEEDS) == 3
    for seed in SEEDS:
        assert replay(qualified / "controller_fuzz", seed) == 0, seed.name


@pytest.mark.parametrize("defect", sorted(DEFECTS))
def test_engine_finds_and_retains_a_controlled_defect(
    defect: str, qualified: Path, tmp_path: Path
) -> None:
    """A controlled incorrect copy of the controller is caught, retained and reproducible."""
    original, replacement, occurrences, signature = DEFECTS[defect]
    text = CONTROLLER.read_text(encoding="utf-8")
    assert text.count(original) == occurrences
    broken = tmp_path / "witness_controller.c"
    broken.write_text(text.replace(original, replacement), encoding="utf-8")
    directory = tmp_path / "campaign"
    completed = campaign(directory, broken, 30)
    assert completed.returncode != 0
    assert signature in completed.stdout
    retained = sorted((directory / "crashes").iterdir())
    assert retained
    assert replay(directory / "controller_fuzz", retained[0]) != 0
    assert replay(qualified / "controller_fuzz", retained[0]) == 0
    assert CONTROLLER.read_text(encoding="utf-8") == text
