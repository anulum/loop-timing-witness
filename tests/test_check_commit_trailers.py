# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — tests of the commit-message policy guard

"""Contract tests for the commit-message hook."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from check_commit_trailers import REQUIRED_AUTHORSHIP_LINE, main, message_findings

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import RunTool

VALID = (
    "feat(tools): add the measurement-domain validator\n"
    "\n"
    "The validator checks the event record layout against the run plan.\n"
    "\n"
    f"Seat: ab12\n{REQUIRED_AUTHORSHIP_LINE}\n"
)


def test_valid_message_has_no_findings() -> None:
    """A conventional subject with the closing block is accepted."""
    assert message_findings(VALID) == []


def test_blank_line_between_seat_and_authorship_is_accepted() -> None:
    """Blank lines may separate the seat trailer from the authorship line."""
    message = f"docs: describe the protocol\n\nSeat: rs01\n\n{REQUIRED_AUTHORSHIP_LINE}\n"
    assert message_findings(message) == []


def test_git_comment_lines_are_ignored() -> None:
    """Editor comment lines are removed before the checks, as Git does."""
    message = f"# Please enter the commit message\n{VALID}# On branch main\n"
    assert message_findings(message) == []


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            f"added validator\n\nSeat: ab12\n{REQUIRED_AUTHORSHIP_LINE}\n",
            ["subject must read `type(scope): summary` with a conventional type"],
        ),
        (
            f"feat: {'x' * 70}\n\nSeat: ab12\n{REQUIRED_AUTHORSHIP_LINE}\n",
            ["subject exceeds 72 characters"],
        ),
        ("feat: x\n\nSeat: ab12\n", ["missing required authorship line"]),
        (
            f"feat: x\n\nSeat: ab12\n{REQUIRED_AUTHORSHIP_LINE}\n{REQUIRED_AUTHORSHIP_LINE}\n",
            ["expected exactly one authorship line"],
        ),
        (f"feat: x\n\n{REQUIRED_AUTHORSHIP_LINE}\n", ["missing `Seat: <seat-id>` trailer"]),
        (
            f"feat: x\n\nSeat: aa01\nSeat: bb02\n{REQUIRED_AUTHORSHIP_LINE}\n",
            ["expected exactly one `Seat: <seat-id>` trailer"],
        ),
        (
            f"feat: x\n\nSeat: agent-ab12\n{REQUIRED_AUTHORSHIP_LINE}\n",
            ["`Seat:` needs one lowercase alphanumeric identifier of 2-16 characters"],
        ),
        (
            f"feat: x\n\n{REQUIRED_AUTHORSHIP_LINE}\nSeat: ab12\n",
            ["`Seat:` trailer must come before the authorship line"],
        ),
        (
            f"feat: x\n\nSeat: ab12\nReviewed-by: someone\n{REQUIRED_AUTHORSHIP_LINE}\n",
            ["only the authorship line may follow the `Seat:` trailer"],
        ),
        (
            f"feat: x\n\nCo-Authored-By: Someone <a@b>\n\nSeat: ab12\n{REQUIRED_AUTHORSHIP_LINE}\n",
            ["`Co-Authored-By:` is forbidden"],
        ),
        (
            f"feat: x\n\nGenerated with a tool\n\nSeat: ab12\n{REQUIRED_AUTHORSHIP_LINE}\n",
            ["generated-by attribution is forbidden"],
        ),
        (
            (
                "feat: robust witness\n\nA comprehensive design.\n\n"
                f"Seat: ab12\n{REQUIRED_AUTHORSHIP_LINE}\n"
            ),
            ["self-applied quality terms are forbidden: comprehensive, robust"],
        ),
        (
            "",
            [
                "subject must read `type(scope): summary` with a conventional type",
                "missing required authorship line",
                "missing `Seat: <seat-id>` trailer",
            ],
        ),
    ],
)
def test_each_violation_is_reported_exactly(message: str, expected: list[str]) -> None:
    """Every rule produces its own finding and nothing else."""
    assert message_findings(message) == expected


def test_hook_accepts_a_valid_message_file_in_a_subprocess(
    tmp_path: Path, run_tool: RunTool
) -> None:
    """The script entry point exits 0 for a compliant message file."""
    path = tmp_path / "COMMIT_EDITMSG"
    path.write_text(VALID, encoding="utf-8")
    completed = run_tool("check_commit_trailers", str(path))
    assert completed.returncode == 0
    assert completed.stderr == ""


def test_hook_rejects_an_invalid_message_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A non-compliant message exits 1 and prints the findings and the required block."""
    path = tmp_path / "COMMIT_EDITMSG"
    path.write_text("feat: x\n", encoding="utf-8")
    assert main([str(path)]) == 1
    error = capsys.readouterr().err
    assert "commit-message: rejected" in error
    assert "  - missing required authorship line" in error
    assert REQUIRED_AUTHORSHIP_LINE in error


@pytest.mark.parametrize("content", [None, b"\xff\xfe"])
def test_unreadable_message_file_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: bytes | None
) -> None:
    """A directory or a non-UTF-8 file cannot be read and is rejected."""
    path = tmp_path / "COMMIT_EDITMSG"
    if content is None:
        path.mkdir()
    else:
        path.write_bytes(content)
    assert main([str(path)]) == 1
    assert "commit-message: cannot read" in capsys.readouterr().err
