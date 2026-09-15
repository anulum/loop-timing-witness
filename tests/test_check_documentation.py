# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — tests of the documentation link and anchor guard

"""Contract tests for the documentation link, image and anchor guard."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from check_documentation import audit, heading_anchors, link_targets, main

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import MakeGitTree, RunTool


def test_repository_documentation_passes_in_a_subprocess(run_tool: RunTool) -> None:
    """Every link in the repository's own Markdown resolves."""
    completed = run_tool("check_documentation")
    assert completed.returncode == 0, completed.stdout
    assert completed.stdout.strip() == "documentation: PASS"


def test_heading_anchors_follow_the_generated_identifiers() -> None:
    """Case, punctuation, code spans, repeats and fenced pseudo-headings are handled."""
    text = (
        "# Loop Timing Witness\n"
        "## Evidence boundary and non-claims\n"
        "## `COMPUTE` profile — planned!\n"
        "## Repeat\n"
        "## Repeat\n"
        "```text\n"
        "# not a heading\n"
        "```\n"
        "### Closing hashes ###\n"
    )
    assert heading_anchors(text) == {
        "loop-timing-witness",
        "evidence-boundary-and-non-claims",
        "compute-profile--planned",
        "repeat",
        "repeat-1",
        "closing-hashes",
    }


def test_link_targets_skip_code_and_keep_line_numbers() -> None:
    """Links inside fences and code spans are not targets; definitions are."""
    text = (
        'See [guide](docs/guide.md) and ![diagram](img/d.svg "Diagram").\n'
        "`[not a link](nowhere.md)`\n"
        "~~~\n"
        "[also not](nowhere.md)\n"
        "~~~\n"
        '[ref]: <docs/ref.md> "Reference"\n'
        "[external](https://example.org/page)\n"
    )
    assert link_targets(text) == [
        (1, "docs/guide.md"),
        (1, "img/d.svg"),
        (6, "docs/ref.md"),
        (7, "https://example.org/page"),
    ]


def test_reachable_links_pass(make_git_tree: MakeGitTree) -> None:
    """Files, directories with publishable content, anchors and external links all pass."""
    root = make_git_tree(
        {
            "README.md": (
                "# Start\n"
                "[guide](docs/guide.md#first-section) [docs](docs/) [top](#start)\n"
                "[mail](mailto:someone@example.org) [licence](LICENSE)\n"
            ),
            "docs/guide.md": "# First section\n[back](../README.md)\n",
            "LICENSE": "text",
        }
    )
    assert audit(root) == []


@pytest.mark.parametrize(
    ("readme", "expected"),
    [
        ("[gone](missing.md)", "README.md:1: link 'missing.md' does not reach a publishable path"),
        (
            "[private](docs/internal/notes.md)",
            "README.md:1: link 'docs/internal/notes.md' does not reach a publishable path",
        ),
        (
            "[abs](/etc/passwd)",
            "README.md:1: absolute link '/etc/passwd' does not resolve on every host",
        ),
        ("[out](../outside.md)", "README.md:1: link '../outside.md' leaves the repository"),
        ("# Start\n[bad](#finish)", "README.md:2: fragment 'finish' names no heading of README.md"),
        (
            "[bad](docs/guide.md#absent)",
            "README.md:1: fragment 'absent' names no heading of docs/guide.md",
        ),
    ],
)
def test_unreachable_links_are_reported(
    make_git_tree: MakeGitTree, readme: str, expected: str
) -> None:
    """Each kind of unreachable target is reported with its line."""
    root = make_git_tree(
        {
            ".gitignore": "docs/internal/\n",
            "README.md": readme,
            "docs/guide.md": "# Guide\n",
            "docs/internal/notes.md": "# Private\n",
        }
    )
    assert audit(root) == [expected]


def test_encoded_fragment_and_path_are_decoded(make_git_tree: MakeGitTree) -> None:
    """Percent-encoded paths and fragments resolve like their decoded form."""
    root = make_git_tree(
        {"README.md": "[x](my%20notes.md#s%C3%BAhrn)\n", "my notes.md": "# Súhrn\n"}
    )
    assert audit(root) == []


def test_undecodable_markdown_is_reported(make_git_tree: MakeGitTree) -> None:
    """A Markdown file that is not UTF-8 is a finding."""
    findings = audit(make_git_tree({"bad.md": b"\xff\xfe"}))
    assert len(findings) == 1
    assert findings[0].startswith("bad.md: unreadable as UTF-8:")


def test_command_line_reports_findings(
    make_git_tree: MakeGitTree, capsys: pytest.CaptureFixture[str]
) -> None:
    """The root argument selects the work tree and findings exit 1."""
    root = make_git_tree({"README.md": "[gone](missing.md)\n"})
    assert main([str(root)]) == 1
    assert capsys.readouterr().out.strip() == (
        "documentation: FAIL README.md:1: link 'missing.md' does not reach a publishable path"
    )


def test_directory_outside_git_is_a_finding(tmp_path: Path) -> None:
    """Without a work tree the guard reports the listing failure."""
    findings = audit(tmp_path)
    assert len(findings) == 1
    assert "git ls-files failed" in findings[0]
