# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — real documentation website publication tests

"""Build actual package, source and native references through the public CLI."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from build_docs_site import main

from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from conftest import RunTool


def test_actual_website_has_native_api_source_anchors_and_asset(
    tmp_path: Path, run_tool: RunTool
) -> None:
    """The public build contains actual interfaces, working fragments and checked hashes."""
    output = tmp_path / "site"
    result = run_tool("build_docs_site", "--output", str(output))
    assert result.returncode == 0, result.stdout + result.stderr
    inventory = json.loads((output / "site-provenance.json").read_text())
    assert len(inventory["source_revision"]) == 40
    assert "README.md" in inventory["documents"]
    assert not any("internal" in name for name in inventory["files"])
    for name, digest in inventory["files"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == digest
    assert (output / ".nojekyll").is_file()
    landing = (output / "index.html").read_text()
    assert 'id="validation"' in landing
    assert 'href="VALIDATION.html"' in landing
    assert 'src="docs/assets/loop-timing-witness.webp"' in landing
    assert (output / "docs/assets/loop-timing-witness.webp").read_bytes() == (
        REPOSITORY_ROOT / "docs/assets/loop-timing-witness.webp"
    ).read_bytes()
    for page in (
        "api/c/index.html",
        "api/rust/witness_controller/index.html",
        "api/rust/witness_amp_rust_kernel/index.html",
        "api/python/loop_timing_witness.html",
        "api/python/loop_timing_witness.analyze_run.html",
    ):
        assert (output / page).stat().st_size > 0
    assert "build_report" in (output / "api/python/loop_timing_witness.html").read_text()


def test_existing_output_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """An existing output directory is preserved when a new build is refused."""
    assert main(["--output", str(tmp_path)]) == 1
    error = capsys.readouterr().err
    assert error == "documentation-site: FAIL: could not read inputs or create output\n"
    assert str(tmp_path) not in error
    assert "File exists" not in error


def test_missing_native_reference_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Missing genuine C documentation cannot produce a partially published website."""
    index = REPOSITORY_ROOT / "build/native-api/c/html/index.html"
    saved = index.with_suffix(".html.saved-by-documentation-test")
    index.rename(saved)
    try:
        assert main(["--output", str(tmp_path / "site")]) == 1
        assert "required C/C++ and both Rust API references are missing" in capsys.readouterr().err
        assert not (tmp_path / "site").exists()
    finally:
        saved.rename(index)


def test_invalid_publishable_source_refuses_the_build(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A broken source link fails before any website output is created."""
    document = REPOSITORY_ROOT / "docs/documentation-build-refusal-test.md"
    assert not document.exists()
    document.write_text("# Documentation build refusal\n[Missing source](missing-source.md)\n")
    try:
        assert main(["--output", str(tmp_path / "site")]) == 1
        assert "invalid source documentation" in capsys.readouterr().err
        assert not (tmp_path / "site").exists()
    finally:
        document.unlink()


def test_repeated_source_headings_have_distinct_working_fragments(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Repeated actual protocol headings retain the same identifiers as GitHub."""
    document = REPOSITORY_ROOT / "docs/documentation-build-anchor-test.md"
    assert not document.exists()
    protocol = (REPOSITORY_ROOT / "docs/MEASUREMENT_PROTOCOL.md").read_text()
    document.write_text(protocol + "\n" + protocol)
    try:
        output = tmp_path / "site"
        assert main(["--output", str(output)]) == 0, capsys.readouterr().err
        page = (output / "docs/documentation-build-anchor-test.html").read_text()
        assert 'id="measurement-protocol"' in page
        assert 'id="measurement-protocol-1"' in page
    finally:
        document.unlink()
