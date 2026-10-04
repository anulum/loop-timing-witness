# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — tests of the provenance header guard

"""Contract tests for the provenance header and rendered-Markdown guard."""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from check_provenance_headers import HEADER_LINES, TITLE_PREFIX, audit, main
from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from pathlib import Path

    from conftest import MakeGitTree, RunTool


def hash_header(title: str = "test file") -> str:
    """Build a complete hash-comment header.

    Parameters
    ----------
    title
        Description after the project prefix.

    Returns
    -------
    str
        Seven header lines with a trailing newline.
    """
    return "".join(f"# {line}\n" for line in (*HEADER_LINES, f"{TITLE_PREFIX}{title}"))


def slash_header(title: str = "test RTL") -> str:
    """Build a complete native/RTL line-comment header.

    Parameters
    ----------
    title
        Description after the project prefix.

    Returns
    -------
    str
        Seven slash-comment lines with a trailing newline.
    """
    return "".join(f"// {line}\n" for line in (*HEADER_LINES, f"{TITLE_PREFIX}{title}"))


def linker_header(title: str = "test linker script") -> str:
    """Build a syntactically valid complete linker-script provenance comment.

    Parameters
    ----------
    title
        Project-specific seventh line description.

    Returns
    -------
    str
        Complete block comment including its closing delimiter.
    """
    lines = ["/* " + HEADER_LINES[0], *(" * " + line for line in HEADER_LINES[1:])]
    return "\n".join([*lines, " * " + TITLE_PREFIX + title, " */", ""])


def markdown_header(title: str = "test page") -> str:
    """Build a complete Markdown header comment.

    Parameters
    ----------
    title
        Description after the project prefix.

    Returns
    -------
    str
        The HTML comment holding the seven lines, with a trailing newline.
    """
    return (
        "<!--\n"
        + "".join(f"{line}\n" for line in (*HEADER_LINES, f"{TITLE_PREFIX}{title}"))
        + "-->\n"
    )


def test_repository_passes_in_a_subprocess(run_tool: RunTool) -> None:
    """Every publishable file of this repository carries its header."""
    completed = run_tool("check_provenance_headers")
    assert completed.returncode == 0, completed.stdout
    assert completed.stdout.strip() == "provenance-headers: PASS"


@pytest.mark.parametrize(
    "name", ["anulum_logo_company.jpg", "anulum_logo.png", "fortis_studio_logo.jpg"]
)
def test_original_brand_image_and_attribution_pass_the_cli(
    name: str, make_git_tree: MakeGitTree, run_tool: RunTool
) -> None:
    """The registered original image and its actual attribution are admitted."""
    root = make_git_tree({})
    image = root / "docs/assets" / name
    image.parent.mkdir(parents=True)
    original = REPOSITORY_ROOT / "docs/assets" / name
    shutil.copyfile(original, image)
    shutil.copyfile(
        original.with_name(original.name + ".license"), image.with_name(image.name + ".license")
    )
    result = run_tool("check_provenance_headers", str(root))
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "provenance-headers: PASS"


@pytest.mark.parametrize(
    ("fault", "finding"),
    [
        ("changed-image", "bytes differ from the registered original brand image"),
        ("missing-image", "original image and UTF-8 attribution sidecar are required"),
        ("missing-attribution", "original image and UTF-8 attribution sidecar are required"),
        ("non-utf8-attribution", "original image and UTF-8 attribution sidecar are required"),
        ("changed-owner", "attribution sidecar lacks the canonical ownership fields"),
        ("missing-title", "attribution sidecar lacks the canonical ownership fields"),
        ("wrong-title", "header line 7 must read"),
        ("reordered-header", "attribution sidecar lacks the canonical ownership fields"),
    ],
)
def test_brand_custody_fault_is_refused_by_the_cli(
    fault: str, finding: str, make_git_tree: MakeGitTree, run_tool: RunTool
) -> None:
    """A real altered image, missing file or damaged attribution cannot pass."""
    root = make_git_tree({})
    image = root / "docs/assets/anulum_logo.png"
    image.parent.mkdir(parents=True)
    original = REPOSITORY_ROOT / "docs/assets/anulum_logo.png"
    attribution = image.with_name(image.name + ".license")
    shutil.copyfile(original, image)
    shutil.copyfile(original.with_name(original.name + ".license"), attribution)
    if fault == "changed-image":
        content = bytearray(image.read_bytes())
        content[-1] ^= 1
        image.write_bytes(content)
    elif fault == "missing-image":
        image.unlink()
    elif fault == "missing-attribution":
        attribution.unlink()
    elif fault == "non-utf8-attribution":
        attribution.write_bytes(b"\xff")
    elif fault == "missing-title":
        attribution.write_text("\n".join(HEADER_LINES) + "\n")
    elif fault == "wrong-title":
        text = attribution.read_text()
        attribution.write_text(text.replace(TITLE_PREFIX, "Other project: "))
    elif fault == "reordered-header":
        lines = attribution.read_text().splitlines()
        lines[0], lines[1] = lines[1], lines[0]
        attribution.write_text("\n".join(lines) + "\n")
    else:
        attribution.write_text(attribution.read_text().replace(HEADER_LINES[2], "Changed owner"))
    result = run_tool("check_provenance_headers", str(root))
    assert result.returncode == 1
    assert finding in result.stdout


def test_compliant_files_of_every_rule_pass(make_git_tree: MakeGitTree) -> None:
    """Hash-comment, shebang, Markdown, JSON and licence files all comply."""
    root = make_git_tree(
        {
            ".clang-format": hash_header() + "BasedOnStyle: LLVM\n",
            "tool.py": hash_header() + "\nprint('x')\n",
            "script.py": "#!/usr/bin/env python3\n" + hash_header() + "\n",
            "hardware/derive.sh": "#!/usr/bin/env bash\n" + hash_header() + "set -eu\n",
            "hardware/connect.tcl": hash_header() + "puts ready\n",
            "Makefile": hash_header() + "all:\n",
            ".github/CODEOWNERS": hash_header() + "* @owner\n",
            "config.yml": hash_header() + "key: value\n",
            "rtl/witness.sv": slash_header() + "module witness; endmodule\n",
            "rtl/codes.svh": slash_header() + "`define EVENT 1\n",
            "controllers/controller.c": slash_header() + "int main(void) { return 0; }\n",
            "runtime/simulator.cpp": slash_header() + "int main() { return 0; }\n",
            "controllers/controller.h": slash_header() + "void controller(void);\n",
            "controllers/lib.rs": slash_header() + "pub fn controller() {}\n",
            "controllers/Cargo.lock": "# This file is automatically @generated by Cargo.\n"
            "# It is not intended for manual editing.\n" + hash_header() + "version = 4\n",
            "runtime/entry.S": hash_header() + ".text\n",
            "runtime/plugin.mk": hash_header() + "all:\n",
            "runtime/firmware.ld": linker_header() + "ENTRY(_start)\n",
            "tests/platform.dts": slash_header() + "/dts-v1/;\n",
            "rtl/verify.ys": hash_header() + "check -assert\n",
            "README.md": markdown_header() + "\n# Title\n",
            "data.json": "{}\n",
            "LICENSE": "licence text\n",
            "LICENSES/AGPL-3.0-or-later.txt": "licence text\n",
        }
    )
    assert audit(root) == []


@pytest.mark.parametrize(
    ("relative", "content", "expected"),
    [
        (
            ".clang-format",
            "BasedOnStyle: LLVM\n",
            ".clang-format: must start with the seven-line '# ' provenance header",
        ),
        (
            "runtime/simulator.cpp",
            "int main() { return 0; }\n",
            "runtime/simulator.cpp: must start with the seven-line '// ' provenance header",
        ),
        (
            "Cargo.lock",
            hash_header(),
            "Cargo.lock: Cargo preamble must precede the seven-line provenance header",
        ),
        (
            "rtl/verify.ys",
            "check -assert\n",
            "rtl/verify.ys: must start with the seven-line '# ' provenance header",
        ),
        (
            "tool.py",
            "print('x')\n",
            "tool.py: must start with the seven-line '# ' provenance header",
        ),
        (
            "hardware/derive.sh",
            "#!/usr/bin/env bash\nset -eu\n",
            "hardware/derive.sh: must start with the seven-line '# ' provenance header",
        ),
        (
            "hardware/connect.tcl",
            "puts ready\n",
            "hardware/connect.tcl: must start with the seven-line '# ' provenance header",
        ),
        (
            "rtl/witness.sv",
            "module witness; endmodule\n",
            "rtl/witness.sv: must start with the seven-line '// ' provenance header",
        ),
        (
            "short.toml",
            "".join(f"# {line}\n" for line in HEADER_LINES),
            "short.toml: must start with the seven-line '# ' provenance header",
        ),
        (
            "wrong.yml",
            hash_header().replace("Loop Timing Witness — test file", "Other Project — file"),
            "wrong.yml: header line 7 must read 'Loop Timing Witness — <description>'",
        ),
        (
            "blank.cfg.in",
            hash_header("   "),
            "blank.cfg.in: header line 7 must read 'Loop Timing Witness — <description>'",
        ),
        (
            "shebang.sh.txt",
            "#!/bin/sh\n" + hash_header(),
            "shebang.sh.txt: must start with the seven-line '# ' provenance header",
        ),
        (
            "page.md",
            "# Title\n",
            "page.md: must start with the provenance header inside '<!--' and '-->'",
        ),
        (
            "unclosed.md",
            markdown_header().replace("-->\n", "\n"),
            "unclosed.md: must start with the provenance header inside '<!--' and '-->'",
        ),
        (
            "titled.md",
            markdown_header("").replace("— \n", "—\n"),
            "titled.md: header line 7 must read 'Loop Timing Witness — <description>'",
        ),
        (
            "empty.md",
            markdown_header() + "\n\n",
            "empty.md: no rendered content follows the provenance comment",
        ),
        (
            "invalid.ld",
            "ENTRY(_start)\n",
            "invalid.ld: must start with the seven-line linker block-comment provenance header",
        ),
        (
            "unclosed.ld",
            linker_header().replace(" */", ""),
            "unclosed.ld: must start with the seven-line linker block-comment provenance header",
        ),
        (
            "uncommented.ld",
            linker_header().replace(" * Loop Timing", "Loop Timing"),
            "uncommented.ld: must start with the seven-line linker block-comment provenance header",
        ),
        (
            "untitled.ld",
            linker_header(" "),
            "untitled.ld: header line 7 must read 'Loop Timing Witness — <description>'",
        ),
        ("image.png", "binary-looking", "image.png: no provenance rule for this file type"),
    ],
)
def test_each_violation_is_reported(
    make_git_tree: MakeGitTree, relative: str, content: str, expected: str
) -> None:
    """Every rule reports its own finding for the offending file."""
    assert audit(make_git_tree({relative: content})) == [expected]


def test_undecodable_file_is_a_finding(make_git_tree: MakeGitTree) -> None:
    """A file that is not UTF-8 is reported rather than skipped."""
    findings = audit(make_git_tree({"notes.txt": b"\xff\xfe\x00"}))
    assert len(findings) == 1
    assert findings[0].startswith("notes.txt: unreadable as UTF-8 text:")


def test_ignored_files_are_not_checked(make_git_tree: MakeGitTree) -> None:
    """Content ignored by Git is outside the publishable set."""
    root = make_git_tree(
        {".gitignore": hash_header() + "private/\n", "private/notes.md": "no header"}
    )
    assert audit(root) == []


def test_command_line_reports_findings_for_a_given_root(
    make_git_tree: MakeGitTree, capsys: pytest.CaptureFixture[str]
) -> None:
    """The root argument selects the work tree and findings exit 1."""
    root = make_git_tree({"tool.py": "print('x')\n"})
    assert main([str(root)]) == 1
    assert capsys.readouterr().out.strip() == (
        "provenance-headers: FAIL tool.py: must start with the seven-line '# ' provenance header"
    )


def test_directory_outside_git_is_a_finding(tmp_path: Path) -> None:
    """Without a work tree the guard reports the listing failure."""
    findings = audit(tmp_path)
    assert len(findings) == 1
    assert "git ls-files failed" in findings[0]
