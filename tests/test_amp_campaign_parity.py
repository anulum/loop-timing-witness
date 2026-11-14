# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — AMP repeat campaign parity between the Python and the native command

"""Run both campaign commands on repeats copied from one real dedicated-hart capture.

Each case orders three copies of a real Spike capture as a repeat campaign,
changes the second repeat as the AMP run parity test does, and requires the
Python and the native command to print, exit and publish alike: a published
campaign when every repeat reports, a refused repeat when its capture is
refused, and no report at all when a captured artifact cannot be read while
the repeat's report is built, as Python's ``OSError`` refuses the whole
campaign.
"""

from __future__ import annotations

import json
import shutil
from typing import TYPE_CHECKING, Any, Final

from capture_amp_simulation import main as capture_main
from test_amp_run_parity import Change, _absent_first, _bind, _receipt
from test_campaign_parity import _same
from test_capture_amp_simulation import capture_arguments

from conftest import write_bound_json

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["capture_arguments"]
REPEATS: Final = 3


def _campaign(capture: Path, directory: Path, change: Change | None) -> Path:
    """Write a campaign of capture copies, the second one changed.

    Parameters
    ----------
    capture
        Real capture with its run manifest.
    directory
        Owned case directory; the campaign is written to its ``campaign`` folder.
    change
        Change of the second repeat's run, or ``None``.

    Returns
    -------
    Path
        Campaign manifest path.
    """
    campaign = directory / "campaign"
    campaign.mkdir(parents=True)
    entries = []
    for index in range(1, REPEATS + 1):
        run = campaign / f"repeat-{index}"
        shutil.copytree(capture, run, symlinks=True)
        if index == 2 and change is not None:
            change(run)
            _bind(run)
        manifest: dict[str, Any] = json.loads((run / "manifest.json").read_bytes())
        manifest["run_id"] = f"amp-repeat-{index}"
        entries.append(
            {
                "repeat_index": index,
                "run_manifest": write_bound_json(run / "manifest.json", manifest),
                "rebooted_before_run": True,
            }
        )
    document = {
        "schema": "loop-timing-witness.repeat-campaign.v1",
        "campaign_id": "amp-repeat-campaign",
        "repeats": entries,
        "operator_notes": "ISA simulation only",
    }
    path = campaign / "campaign.json"
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


def test_amp_campaigns_run_alike(capture_arguments: list[str], tmp_path: Path) -> None:
    """Require both commands to publish, refuse a repeat or refuse the campaign alike.

    Parameters
    ----------
    capture_arguments
        Actual source-bound image, Spike and production plugin.
    tmp_path
        Owned directory for the capture and the case campaigns.
    """
    assert capture_main(capture_arguments) == 0
    capture = tmp_path / "capture"
    published = _same(_campaign(capture, tmp_path / "captured", None), tmp_path / "captured")
    assert published["status"] in {0, 2}
    report = json.loads((tmp_path / "captured/python-report/campaign_report.json").read_bytes())
    assert [entry["invalid_reasons"] for entry in report["repeats"]] == [
        ["power series unavailable"]
    ] * REPEATS
    miss = _receipt(lambda receipt: receipt["completion"].update(misses=1))
    refused = _same(_campaign(capture, tmp_path / "refused", miss), tmp_path / "refused")
    assert refused["status"] in {0, 2}
    report = json.loads((tmp_path / "refused/python-report/campaign_report.json").read_bytes())
    assert report["repeats"][1]["status"] == "refused"
    assert "differs from the actual logger" in report["repeats"][1]["refusal"]
    absent = tmp_path / "unreadable"
    unreadable = _same(_campaign(capture, absent, _receipt(_absent_first)), absent)
    assert unreadable["status"] == 1
    assert "No such file or directory" in unreadable["stderr"]
