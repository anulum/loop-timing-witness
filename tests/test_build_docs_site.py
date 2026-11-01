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
import html
import inspect
import json
import pydoc
import re
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from build_docs_site import REPOSITORY, RepositoryTextDoc, main

from conftest import REPOSITORY_ROOT
from loop_timing_witness import validate_measurement_domain

if TYPE_CHECKING:
    import pytest

    from conftest import RunTool


def test_actual_website_has_native_api_source_anchors_and_asset(
    tmp_path: Path, run_tool: RunTool
) -> None:
    """The real website retains API content and hashes without builder paths.

    Parameters
    ----------
    tmp_path
        Exclusive website output directory.
    run_tool
        Runner invoking the repository's actual public build command.
    """
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
    for name in ("anulum_logo_company.jpg", "anulum_logo.png", "fortis_studio_logo.jpg"):
        asset = "docs/assets/" + name
        assert (output / asset).read_bytes() == (REPOSITORY_ROOT / asset).read_bytes()
        assert f'src="./{asset}"' in landing
    assert 'aria-label="Loop Timing Witness overview"' in landing
    for page in (
        "api/c/index.html",
        "api/rust/witness_analysis/index.html",
        "api/rust/witness_controller/index.html",
        "api/rust/witness_amp_rust_kernel/index.html",
        "api/python/loop_timing_witness.html",
        "api/python/loop_timing_witness.analyze_run.html",
    ):
        assert (output / page).stat().st_size > 0
    assert "build_report" in (output / "api/python/loop_timing_witness.html").read_text()
    package_page = (output / "api/python/loop_timing_witness.html").read_text()
    assert 'src="../../docs/assets/anulum_logo.png"' in package_page
    assert 'src="../../docs/assets/anulum_logo_company.jpg"' in package_page
    assert 'src="../../docs/assets/fortis_studio_logo.jpg"' in package_page
    for module in inventory["python_api_modules"]:
        page = (output / "api/python" / f"{module}.html").read_text()
        assert str(REPOSITORY_ROOT) not in html.unescape(page)
        assert "/media/anulum" not in html.unescape(page)
        assert "/home/anulum" not in html.unescape(page)
        assert "Repository paths are shown relative to the source tree." in page
    assert "src/loop_timing_witness/__init__.py" in package_page
    schema_page = (
        output / "api/python/loop_timing_witness.validate_measurement_domain.html"
    ).read_text()
    assert "src/loop_timing_witness/data/measurement-domain.schema.json" in schema_page


def test_every_page_footer_carries_the_licence_and_sources_keep_hidden_headers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Show the licence in each footer while source provenance headers stay invisible.

    Parameters
    ----------
    tmp_path
        Exclusive website output directory.
    capsys
        Captured build diagnostics.
    """
    output = tmp_path / "site"
    assert main(["--output", str(output)]) == 0, capsys.readouterr().err
    revision = json.loads((output / "site-provenance.json").read_text())["source_revision"]
    licence = f'Licensed under <a href="{REPOSITORY}/blob/{revision}/LICENSE">AGPL-3.0-or-later</a>'
    for name in ("index.html", "docs/HOST_ANALYSIS.html", "api/python/loop_timing_witness.html"):
        page = (output / name).read_text()
        footer = page[page.index("<footer>") : page.index("</footer>")]
        assert licence in footer
        assert "© Concepts 1996–2026 and code 2020–2026 Miroslav Šotek." in footer
        assert 'href="mailto:protoscience@anulum.li"' in footer
    for name in ("index.html", "docs/HOST_ANALYSIS.html", "VALIDATION.html"):
        page = (output / name).read_text()
        visible = re.sub(r"<!--.*?-->", "", page, flags=re.DOTALL)
        for header_line in ("Commercial license available", "ORCID: 0009-0009-3560-0851"):
            assert header_line in page
            assert header_line not in visible
        main_content = visible[visible.index("<main>") + len("<main>") :].lstrip()
        assert main_content.startswith(("<h1", "<p")), main_content[:80]


def test_reference_path_values_preserve_actual_repository_boundaries() -> None:
    """Real source paths become relative while the actual parent path stays external."""
    renderer = RepositoryTextDoc()
    assert renderer.repr(REPOSITORY_ROOT) == "PosixPath('.')"
    assert renderer.repr(REPOSITORY_ROOT / "src/loop_timing_witness/data") == (
        "PosixPath('src/loop_timing_witness/data')"
    )
    assert renderer.repr(REPOSITORY_ROOT.parent) == pydoc.TextDoc().repr(REPOSITORY_ROOT.parent)


def test_reference_absolute_defaults_follow_resolved_repository_boundaries(tmp_path: Path) -> None:
    """Actual parent components and symlinks preserve outside default representations.

    Parameters
    ----------
    tmp_path
        Exclusive existing directory outside the repository used by the symlink control.
    """
    renderer = RepositoryTextDoc()
    external = REPOSITORY_ROOT / ".."
    assert renderer.repr(external) == pydoc.TextDoc().repr(external)
    internal = REPOSITORY_ROOT / "src" / ".." / "src/loop_timing_witness/data"
    assert renderer.repr(internal) == "PosixPath('src/loop_timing_witness/data')"
    with TemporaryDirectory(
        prefix="documentation-path-boundary-", dir=REPOSITORY_ROOT / "build"
    ) as owned:
        outside_alias = Path(owned) / "outside-default"
        outside_alias.symlink_to(tmp_path, target_is_directory=True)
        assert renderer.repr(outside_alias) == pydoc.TextDoc().repr(outside_alias)
        inside_alias = Path(owned) / "inside-default"
        inside_alias.symlink_to(
            REPOSITORY_ROOT / "src/loop_timing_witness/data", target_is_directory=True
        )
        assert renderer.repr(inside_alias) == "PosixPath('src/loop_timing_witness/data')"


def test_relative_reference_defaults_are_independent_of_caller_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same genuine relative default keeps its representation in two real directories.

    Parameters
    ----------
    tmp_path
        Exclusive directory outside the repository.
    monkeypatch
        Restoring manager for the actual caller working directory.
    """
    renderer = RepositoryTextDoc()
    relative = Path("src/loop_timing_witness/data")
    expected = pydoc.TextDoc().repr(relative)
    monkeypatch.chdir(REPOSITORY_ROOT)
    assert renderer.repr(relative) == expected
    monkeypatch.chdir(tmp_path)
    assert renderer.repr(relative) == expected


def test_actual_validator_signature_is_relative_without_changing_its_defaults() -> None:
    """The real manifest command exposes relative defaults while its callable stays intact."""
    routine = validate_measurement_domain.main
    assert inspect.isfunction(routine)
    before = inspect.signature(routine)
    before_defaults: object = routine.__kwdefaults__
    reference = pydoc.plain(RepositoryTextDoc().docroutine(routine))
    assert str(REPOSITORY_ROOT) not in reference
    assert "src/loop_timing_witness/data/measurement-domain.json" in reference
    assert "src/loop_timing_witness/data/measurement-domain.schema.json" in reference
    assert inspect.signature(routine) == before
    assert routine.__kwdefaults__ is before_defaults


def test_actual_validator_external_and_relative_signature_defaults_are_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real routine metadata retains outside and relative defaults during documentation.

    Parameters
    ----------
    monkeypatch
        Restoring manager for the actual command's default metadata.
    """
    routine = validate_measurement_domain.main
    defaults = {
        "default_manifest": REPOSITORY_ROOT / "..",
        "default_schema": Path("src/loop_timing_witness/data"),
    }
    monkeypatch.setattr(routine, "__kwdefaults__", defaults)
    expected = pydoc.TextDoc().docroutine(routine)
    assert RepositoryTextDoc().docroutine(routine) == expected


def test_native_pydoc_fallbacks_remain_available_for_actual_runtime_objects() -> None:
    """Actual runtime routines keep supported signatures and native fallback text."""
    renderer = RepositoryTextDoc()
    assert renderer.docroutine(sys.getsizeof) == pydoc.TextDoc().docroutine(sys.getsizeof)
    assert renderer.docroutine(sys.getrecursionlimit) == pydoc.TextDoc().docroutine(
        sys.getrecursionlimit
    )
    assert renderer.docroutine(validate_measurement_domain) == pydoc.TextDoc().docroutine(
        validate_measurement_domain
    )


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
        assert "required C/C++ and Rust API references are missing" in capsys.readouterr().err
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
