# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — tests of the commit-message policy guard

"""Contract tests for the commit-message hook."""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING

import pytest

import check_commit_trailers
from check_commit_trailers import (
    REQUIRED_AUTHORSHIP_LINE,
    REVIEWER_DIGESTS,
    SEAT_PREFIX_DIGESTS,
    main,
    message_findings,
)

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


def _with_body(text: str) -> str:
    """Return a compliant message whose body is ``text``.

    Parameters
    ----------
    text
        Body paragraph placed between the subject and the closing block.

    Returns
    -------
    str
        Full commit-message text.
    """
    return f"feat(tools): add the validator\n\n{text}\n\nSeat: ab12\n{REQUIRED_AUTHORSHIP_LINE}\n"


def _digest(word: str) -> str:
    """Return the SHA-256 digest of ``word`` as the guard keeps it.

    Parameters
    ----------
    word
        Fictitious seat prefix or reviewer name.

    Returns
    -------
    str
        Lowercase hexadecimal digest.
    """
    return hashlib.sha256(word.encode("utf-8")).hexdigest()


@pytest.fixture
def fictitious_names(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refuse the fictitious seat prefix ``acme`` and reviewer ``AUDITOR`` instead of the real ones.

    Parameters
    ----------
    monkeypatch
        Replaces the two digest sets for one test.
    """
    monkeypatch.setattr(check_commit_trailers, "SEAT_PREFIX_DIGESTS", frozenset({_digest("acme")}))
    monkeypatch.setattr(check_commit_trailers, "REVIEWER_DIGESTS", frozenset({_digest("AUDITOR")}))


def test_the_refused_words_are_kept_only_as_digests() -> None:
    """Seven seat prefixes and one reviewer name are held as SHA-256 digests, not as words."""
    assert len(SEAT_PREFIX_DIGESTS) == 7
    assert len(REVIEWER_DIGESTS) == 1
    assert all(
        re.fullmatch(r"[0-9a-f]{64}", item) for item in SEAT_PREFIX_DIGESTS | REVIEWER_DIGESTS
    )


@pytest.mark.usefixtures("fictitious_names")
@pytest.mark.parametrize(
    ("text", "kind", "name"),
    [
        ("Found while gating for acme-f636.", "agent seat identifier", "acme-f636"),
        ("Routed by ACME-157251.", "agent seat identifier", "ACME-157251"),
        (
            "See HANDOVER_20261118T181923Z.",
            "coordination record name",
            "HANDOVER_20261118T181923Z",
        ),
        ("See REVIEW_2026-11-20 for the verdict.", "coordination record name", "REVIEW_2026-11-20"),
        ("Per LANDING_2026-11-21T1342Z.", "coordination record name", "LANDING_2026-11-21T1342Z"),
        (
            "As NOTE_FROM_PEER_20261120T212421Z says.",
            "coordination record name",
            "NOTE_FROM_PEER_20261120T212421Z",
        ),
        ("Approved by AUDITOR.", "internal reviewer name", "AUDITOR"),
        ("Asked on hub 399765.", "hub event citation", "hub 399765"),
        ("Answered in seq #401897.", "hub event citation", "seq #401897"),
        ("Recorded as event 12345.", "hub event citation", "event 12345"),
    ],
)
def test_an_internal_identifier_in_the_body_is_rejected(text: str, kind: str, name: str) -> None:
    """Each identifier form is reported under its own kind with the name it matched."""
    assert message_findings(_with_body(text)) == [f"{kind} in the message: {name}"]


@pytest.mark.usefixtures("fictitious_names")
@pytest.mark.parametrize(
    "text",
    [
        "Runs on Python 3.12 and keeps PEP_8 names.",
        "Reads the snapshot_2026-11-20 fixture and the UTF_8 codec.",
        "Retries seq 4321 and event 999, below the citation width.",
        "An auditor's check, the acme-code integration and a cafe-beef label.",
        "Pins the wheel digest 9e4e4d08 of HANDOVER and REVIEW forms.",
    ],
)
def test_text_that_only_resembles_an_identifier_is_allowed(text: str) -> None:
    """Version numbers, lowercase names, short numbers and unlisted prefixes pass."""
    assert message_findings(_with_body(text)) == []


def test_an_identifier_in_the_subject_is_rejected() -> None:
    """The subject line is checked like the body."""
    message = _with_body("Body.").replace("add the validator", "land REVIEW_20261121T133713Z")
    assert message_findings(message) == [
        "coordination record name in the message: REVIEW_20261121T133713Z"
    ]


@pytest.mark.usefixtures("fictitious_names")
def test_each_identifier_is_reported_once_in_first_order() -> None:
    """A repeated name is listed once, and the kinds keep their fixed order."""
    message = _with_body("hub 400312, then acme-b0f9, hub 400312 again and acme-b0f9.")
    assert message_findings(message) == [
        "agent seat identifier in the message: acme-b0f9",
        "hub event citation in the message: hub 400312",
    ]


def test_an_identifier_in_a_git_comment_line_is_ignored() -> None:
    """Comment lines are removed before the identifier rule, as before every rule."""
    message = VALID + "# Drafted from HANDOVER_20261118T181923Z on hub 399765\n"
    assert message_findings(message) == []


@pytest.mark.usefixtures("fictitious_names")
def test_the_seat_trailer_is_judged_by_its_own_rule_only() -> None:
    """A seat-shaped trailer is refused once, by the trailer rule, not again as an identifier."""
    message = f"feat: x\n\nSeat: acme-f636\n{REQUIRED_AUTHORSHIP_LINE}\n"
    assert message_findings(message) == [
        "`Seat:` needs one lowercase alphanumeric identifier of 2-16 characters"
    ]


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
    assert capsys.readouterr().err == "commit-message: cannot read message file\n"


@pytest.mark.parametrize("kind", ["directory", "invalid-utf8", "missing"])
def test_public_hook_read_failures_have_fixed_output(
    tmp_path: Path, run_tool: RunTool, kind: str
) -> None:
    """Real filesystem refusals retain status and a fixed caller-safe sentence.

    Parameters
    ----------
    tmp_path
        Exclusive directory containing the actual unreadable input controls.
    run_tool
        Runner invoking the real commit-message hook command.
    kind
        Directory, undecodable file, or missing-file refusal control.
    """
    path = tmp_path / kind
    if kind == "directory":
        path.mkdir()
    elif kind == "invalid-utf8":
        path.write_bytes(b"\xff\xfe")
    result = run_tool("check_commit_trailers", str(path))
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "commit-message: cannot read message file\n"
