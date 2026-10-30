# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — repeat campaign command tests

"""Run the repeat campaign command as a real process and check its outcomes."""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from loop_timing_witness import build_campaign_report, load_campaign
from loop_timing_witness.analyze_campaign import main

if TYPE_CHECKING:
    from conftest import MakeRepeatCampaign

ROOT = Path(__file__).resolve().parents[1]


def _command(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the package command module in a separate interpreter.

    Parameters
    ----------
    *arguments
        Command arguments.

    Returns
    -------
    subprocess.CompletedProcess[str]
        Exit status and both output streams.
    """
    return subprocess.run(
        [sys.executable, "-m", "loop_timing_witness.analyze_campaign", *arguments],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def test_console_script_names_the_campaign_command() -> None:
    """Register the installed command against the module entry point."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["scripts"]["loop-timing-witness-campaign"] == (
        "loop_timing_witness.analyze_campaign:main"
    )


@pytest.mark.parametrize(
    ("run_plan", "status", "heading"),
    [
        ({"cycles_per_repeat": 3, "repeats": 5}, 0, "repeat campaign: COMPLETE: "),
        (None, 2, "repeat campaign: INCOMPLETE: "),
    ],
)
def test_published_campaign_reports_its_status(
    make_repeat_campaign: MakeRepeatCampaign,
    tmp_path: Path,
    run_plan: dict[str, int] | None,
    status: int,
    heading: str,
) -> None:
    """Exit zero for a complete campaign and two for an incomplete one.

    Parameters
    ----------
    make_repeat_campaign
        Campaign of copied real RTL captures.
    tmp_path
        Report parent directory.
    run_plan
        Optional run plan written into every repeat's domain copy.
    status
        Expected exit status.
    heading
        Expected first output line prefix.
    """
    path, _ = make_repeat_campaign(run_plan=run_plan)
    output = tmp_path / "report"
    result = _command(str(path), "--output-dir", str(output))
    assert result.returncode == status, result.stderr
    assert result.stdout.splitlines()[0] == f"{heading}{output}"
    report = json.loads((output / "campaign_report.json").read_bytes())
    assert report == build_campaign_report(load_campaign(path))
    if status:
        assert result.stdout.splitlines()[1:] == [
            "  3 analysed cycles per repeat; the run plan requires 1000000"
        ]


def test_refused_campaign_publishes_nothing(
    make_repeat_campaign: MakeRepeatCampaign, tmp_path: Path
) -> None:
    """Exit one with the authored refusal and leave no report directory.

    Parameters
    ----------
    make_repeat_campaign
        Campaign of copied real RTL captures.
    tmp_path
        Report parent directory.
    """
    path, _ = make_repeat_campaign(repeats=2)
    run = path.parent / "repeat-1" / "manifest.json"
    run.write_bytes(run.read_bytes() + b"\n")
    output = tmp_path / "report"
    result = _command(str(path), "--output-dir", str(output))
    assert result.returncode == 1
    assert result.stderr == (
        "repeat campaign: FAIL: run manifest SHA-256 mismatch: repeat-1/manifest.json\n"
    )
    assert not output.exists()


def test_unwritable_report_parent_is_refused(
    make_repeat_campaign: MakeRepeatCampaign, tmp_path: Path
) -> None:
    """Exit one when the report parent does not exist.

    Parameters
    ----------
    make_repeat_campaign
        Campaign of copied real RTL captures.
    tmp_path
        Directory without the requested parent.
    """
    path, _ = make_repeat_campaign(repeats=1)
    result = _command(str(path), "--output-dir", str(tmp_path / "absent" / "report"))
    assert result.returncode == 1
    assert result.stderr.startswith("repeat campaign: FAIL: report parent does not exist: ")


def test_in_process_entry_point_matches_the_module_command(
    make_repeat_campaign: MakeRepeatCampaign,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Return the same status and report through the importable entry point.

    Parameters
    ----------
    make_repeat_campaign
        Campaign of copied real RTL captures.
    tmp_path
        Report parent directory.
    capsys
        Captured standard streams.
    """
    path, _ = make_repeat_campaign(repeats=2)
    output = tmp_path / "report"
    assert main([str(path), "--output-dir", str(output)]) == 2
    assert capsys.readouterr().out.splitlines() == [
        f"repeat campaign: INCOMPLETE: {output}",
        "  2 repeats declared; the run plan requires 5",
        "  3 analysed cycles per repeat; the run plan requires 1000000",
    ]
    assert json.loads((output / "campaign_report.json").read_bytes()) == build_campaign_report(
        load_campaign(path)
    )
