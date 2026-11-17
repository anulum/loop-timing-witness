# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — measurement-only counted Spike plugin variant

"""Hold the counted plugin variant to its receipt record and keep it out of admitted evidence."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from amp_plugin_receipt import admit_plugin, instrumentation_record, library_instrumented
from test_capture_amp_simulation import ROOT, capture_arguments
from test_write_amp_plugin_manifest import original_plugin
from write_amp_plugin_manifest import write_plugin_manifest

from loop_timing_witness.host_profile import scaled
from manifest_io import canonical_json_bytes

__all__ = ["capture_arguments", "original_plugin"]

if TYPE_CHECKING:
    from amp_plugin_inputs import PluginBuild

FIXED = "-std=c++20 -O2 -fPIC -Wall -Wextra -Werror -Wconversion -Wshadow"
COUNTED = "-O0 --coverage -fprofile-abs-path -fprofile-filter-files=runtime/"
EVIDENCE = "AMP plugin build is a coverage measurement variant, never admitted evidence"
DISAGREE = "AMP plugin instrumentation flags disagree with its kind"


@pytest.fixture(scope="module")
def counted_plugin(original_plugin: PluginBuild, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the counted variant with the public Make target and the production SDK.

    Parameters
    ----------
    original_plugin
        Production build whose SDK selection the variant shares.
    tmp_path_factory
        Exclusive module build allocation.

    Returns
    -------
    Path
        Counted library, its receipt beside it.
    """
    output = tmp_path_factory.mktemp("counted-plugin")
    result = subprocess.run(
        [
            "make",
            "amp-spike-plugin",
            "AMP_SPIKE_SOURCE=" + str(original_plugin.source),
            "AMP_SPIKE_BUILD=" + str(original_plugin.sdk),
            "AMP_PLUGIN_DIRECTORY=" + str(output),
            "AMP_PLUGIN_INSTRUMENTATION=coverage",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=scaled(180),
        check=False,
    )
    (output / "build.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    return output / "witness_spike_axi.so"


@pytest.mark.parametrize(
    ("kind", "compile_flags", "link_flags", "outcome"),
    [
        ("none", "", "", None),
        (
            "coverage",
            "-O0  --coverage",
            "--coverage",
            {
                "kind": "gcov",
                "objects": ["plugin"],
                "compile_flags": ["-O0", "--coverage"],
                "link_flags": ["--coverage"],
            },
        ),
        ("profile", "", "", "AMP plugin instrumentation must be none or coverage"),
        ("coverage", "-O0", "", DISAGREE),
        ("coverage", "", "--coverage", DISAGREE),
        ("none", "", "--coverage", DISAGREE),
        ("none", "-O0", "", DISAGREE),
    ],
)
def test_instrumentation_record(
    kind: str, compile_flags: str, link_flags: str, outcome: dict[str, object] | str | None
) -> None:
    """Record exactly the flags of a counted variant and nothing for production.

    Parameters
    ----------
    kind
        Selected instrumentation.
    compile_flags, link_flags
        Flags Make passes, whitespace-separated.
    outcome
        Expected record, None for production, or the refusal.
    """
    if isinstance(outcome, str):
        with pytest.raises(ValueError, match=f"^{outcome}$"):
            instrumentation_record(kind, compile_flags, link_flags)
    else:
        assert instrumentation_record(kind, compile_flags, link_flags) == outcome


def test_counted_receipt_records_its_flags(counted_plugin: Path) -> None:
    """Count only the device object and record the flags Make used.

    Parameters
    ----------
    counted_plugin
        Counted variant built by the public target.
    """
    data = json.loads(counted_plugin.with_name("plugin.json").read_bytes())
    assert data["instrumentation"] == {
        "kind": "gcov",
        "objects": ["plugin"],
        "compile_flags": COUNTED.split(),
        "link_flags": ["--coverage"],
    }
    assert library_instrumented(counted_plugin)
    notes = sorted(counted_plugin.parent.glob("*.gcno"))
    assert [path.name for path in notes] == ["plugin.gcno"]
    for source in (b"spike_axi_device.cpp", b"spike_amp_transport.h", b"amp_logger.h"):
        assert source in notes[0].read_bytes()


def test_counted_plugin_is_never_admitted_evidence(
    counted_plugin: Path, original_plugin: PluginBuild
) -> None:
    """Admit the counted variant only for a coverage run, and production only outside one.

    Parameters
    ----------
    counted_plugin
        Counted variant.
    original_plugin
        Production build.
    """
    with pytest.raises(ValueError, match=f"^{EVIDENCE}$"):
        admit_plugin(counted_plugin)
    _, data = admit_plugin(counted_plugin, instrumented=True)
    assert data["instrumentation"]["kind"] == "gcov"
    production = original_plugin.directory / "witness_spike_axi.so"
    assert not library_instrumented(production)
    with pytest.raises(
        ValueError, match=r"^AMP coverage run requires an instrumented plugin build$"
    ):
        admit_plugin(production, instrumented=True)


def test_counters_without_their_record_refused(counted_plugin: Path, tmp_path: Path) -> None:
    """Refuse a counted library whose receipt drops the instrumentation record.

    Parameters
    ----------
    counted_plugin
        Counted variant, left unchanged.
    tmp_path
        Copy of the library beside the edited receipt.
    """
    data = json.loads(counted_plugin.with_name("plugin.json").read_bytes())
    del data["instrumentation"]
    library = tmp_path / counted_plugin.name
    shutil.copyfile(counted_plugin, library)
    library.with_name("plugin.json").write_bytes(canonical_json_bytes(data))
    with pytest.raises(
        ValueError, match=r"^AMP plugin library counters disagree with its build receipt$"
    ):
        admit_plugin(library)


def test_writer_requires_agreeing_counters(
    counted_plugin: Path, original_plugin: PluginBuild
) -> None:
    """Refuse to write a receipt whose record disagrees with the library, before any output.

    Parameters
    ----------
    counted_plugin
        Counted variant with its receipt.
    original_plugin
        Production build with its receipt.
    """
    refusal = r"^AMP plugin library counters disagree with its instrumentation$"
    receipts = {
        path: path.read_bytes()
        for path in (
            counted_plugin.with_name("plugin.json"),
            original_plugin.directory / "plugin.json",
        )
    }
    with pytest.raises(ValueError, match=refusal):
        write_plugin_manifest(replace(original_plugin, directory=counted_plugin.parent))
    record = instrumentation_record("coverage", COUNTED, "--coverage")
    with pytest.raises(ValueError, match=refusal):
        write_plugin_manifest(original_plugin, record)
    assert {path: path.read_bytes() for path in receipts} == receipts


def test_capture_refuses_the_counted_plugin(
    capture_arguments: list[str], counted_plugin: Path
) -> None:
    """Refuse a capture with the counted variant before any output exists.

    Parameters
    ----------
    capture_arguments
        Public capture arguments with an admitted image.
    counted_plugin
        Counted variant.
    """
    arguments = [*capture_arguments]
    arguments[arguments.index("--plugin") + 1] = str(counted_plugin)
    result = subprocess.run(
        [sys.executable, "tools/capture_amp_simulation.py", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=scaled(60),
        check=False,
    )
    assert result.returncode == 1
    assert EVIDENCE in result.stderr
    assert not Path(arguments[arguments.index("--output") + 1]).exists()


def test_unknown_instrumentation_refused_before_generation(
    original_plugin: PluginBuild, tmp_path: Path
) -> None:
    """Refuse an unknown instrumentation before the build directory exists.

    Parameters
    ----------
    original_plugin
        Production SDK selection.
    tmp_path
        Parent of the refused build directory.
    """
    output = tmp_path / "plugin"
    result = subprocess.run(
        [
            "make",
            "amp-spike-plugin",
            "AMP_SPIKE_SOURCE=" + str(original_plugin.source),
            "AMP_SPIKE_BUILD=" + str(original_plugin.sdk),
            "AMP_PLUGIN_DIRECTORY=" + str(output),
            "AMP_PLUGIN_INSTRUMENTATION=profile",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=scaled(30),
        check=False,
    )
    assert result.returncode != 0
    assert not output.exists()


def test_command_line_cannot_change_the_plugin_flags() -> None:
    """Keep the fixed and counted flags when Make's command line assigns them."""
    show = (
        "plugin-flags: ; @echo "
        '"$(AMP_PLUGIN_CXXFLAGS)|$(AMP_PLUGIN_DEVICE_FLAGS)|$(AMP_PLUGIN_LINK_FLAGS)"'
    )
    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "--eval",
            show,
            "plugin-flags",
            "AMP_PLUGIN_CXXFLAGS=-O0",
            "AMP_PLUGIN_COVERAGE_FLAGS=-O3",
            "AMP_PLUGIN_DEVICE_FLAGS=-O1",
            "AMP_PLUGIN_LINK_FLAGS=-s",
            "AMP_PLUGIN_INSTRUMENTATION=coverage",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=scaled(30),
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"{FIXED}|{FIXED} {COUNTED}|--coverage"
