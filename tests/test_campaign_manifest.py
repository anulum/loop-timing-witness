# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — repeat campaign manifest tests

"""Load real RTL repeats through the campaign contract and refuse unsound campaigns."""

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING, Any

import pytest

from conftest import write_bound_json
from loop_timing_witness.campaign_manifest import load_campaign, run_configuration
from loop_timing_witness.run_manifest import load_run

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from conftest import MakeRepeatCampaign


def _rewrite_campaign(path: Path, document: dict[str, Any]) -> None:
    """Replace the campaign manifest with a changed document.

    Parameters
    ----------
    path
        Campaign manifest path.
    document
        Complete changed campaign document.
    """
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def _rebind_repeat(
    path: Path, document: dict[str, Any], index: int, change: dict[str, Any]
) -> None:
    """Change fields of one repeat's run manifest and bind its new digest.

    Parameters
    ----------
    path
        Campaign manifest path.
    document
        Campaign document to update in place and rewrite.
    index
        One-based repeat index.
    change
        Top-level run manifest fields to replace.
    """
    entry = document["repeats"][index - 1]
    run_path = path.parent / entry["run_manifest"]["path"]
    value = {**json.loads(run_path.read_bytes()), **change}
    entry["run_manifest"] = write_bound_json(run_path, value)
    _rewrite_campaign(path, document)


def test_campaign_binds_every_repeat_and_one_configuration(
    make_repeat_campaign: MakeRepeatCampaign,
) -> None:
    """Load five real repeats with verified digests in index order.

    Parameters
    ----------
    make_repeat_campaign
        Campaign of copied real RTL captures.
    """
    path, document = make_repeat_campaign()
    campaign = load_campaign(path)
    assert campaign.manifest == document
    assert campaign.manifest_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert [repeat.repeat_index for repeat in campaign.repeats] == [1, 2, 3, 4, 5]
    assert all(repeat.refusal is None for repeat in campaign.repeats)
    assert all(repeat.rebooted_before_run for repeat in campaign.repeats)
    loaded = [repeat.inputs for repeat in campaign.repeats if repeat.inputs is not None]
    assert [inputs.manifest["run_id"] for inputs in loaded] == [
        f"rtl-repeat-{index}" for index in range(1, 6)
    ]
    for repeat, inputs, entry in zip(campaign.repeats, loaded, document["repeats"], strict=True):
        assert repeat.run_manifest_sha256 == entry["run_manifest"]["sha256"]
        assert inputs == load_run(path.parent / entry["run_manifest"]["path"])
    configuration = run_configuration(loaded[0])
    assert all(run_configuration(inputs) == configuration for inputs in loaded)
    assert configuration["source_kind"] == "rtl_simulation"
    assert configuration["hardware_artifacts"] is None
    assert configuration["tracking_sampling"] is None
    assert configuration["cycle_count"] == 3


def test_board_hardware_identity_is_part_of_the_configuration(
    make_repeat_campaign: MakeRepeatCampaign,
) -> None:
    """Expose hardware artefact digests and tool versions for agreement checks.

    Parameters
    ----------
    make_repeat_campaign
        Campaign of copied real RTL captures.
    """
    path, document = make_repeat_campaign(repeats=1)
    inputs = load_run(path.parent / document["repeats"][0]["run_manifest"]["path"])
    artefact = {"path": "events.bin", "sha256": inputs.manifest["files"]["events"]["sha256"]}
    manifest = {
        **inputs.manifest,
        "hardware_artifacts": {
            "bitstream": artefact,
            "firmware": artefact,
            "linux_image": artefact,
            "controller_binary": artefact,
            "libero_version": "2025.1",
            "toolchain_version": "riscv64 gcc 14.2",
        },
    }
    configuration = run_configuration(type(inputs)(manifest, inputs.domain, inputs.files))
    assert configuration["hardware_artifacts"] == {
        "bitstream": artefact["sha256"],
        "firmware": artefact["sha256"],
        "linux_image": artefact["sha256"],
        "controller_binary": artefact["sha256"],
        "libero_version": "2025.1",
        "toolchain_version": "riscv64 gcc 14.2",
    }


def test_refused_run_stays_in_the_campaign(make_repeat_campaign: MakeRepeatCampaign) -> None:
    """Keep a repeat whose run loader refuses changed capture bytes.

    Parameters
    ----------
    make_repeat_campaign
        Campaign of copied real RTL captures.
    """
    path, _ = make_repeat_campaign()
    events = path.parent / "repeat-3" / "events.bin"
    events.write_bytes(events.read_bytes() + bytes(16))
    campaign = load_campaign(path)
    refused = campaign.repeats[2]
    assert refused.inputs is None
    assert refused.refusal == "input SHA-256 mismatch: events.bin"
    assert [repeat.inputs is None for repeat in campaign.repeats] == [
        False,
        False,
        True,
        False,
        False,
    ]


def _missing_notes(path: Path, document: dict[str, Any]) -> None:
    del document["operator_notes"]
    _rewrite_campaign(path, document)


def _wrong_schema(path: Path, document: dict[str, Any]) -> None:
    document["schema"] = "loop-timing-witness.run-manifest.v1"
    _rewrite_campaign(path, document)


def _reordered(path: Path, document: dict[str, Any]) -> None:
    document["repeats"][0]["repeat_index"], document["repeats"][1]["repeat_index"] = 2, 1
    _rewrite_campaign(path, document)


def _upward_path(path: Path, document: dict[str, Any]) -> None:
    document["repeats"][1]["run_manifest"]["path"] = "repeat-2/../repeat-2/manifest.json"
    _rewrite_campaign(path, document)


def _outside_link(path: Path, document: dict[str, Any]) -> None:
    outside = path.parent.parent / "outside.json"
    outside.write_bytes((path.parent / "repeat-2" / "manifest.json").read_bytes())
    (path.parent / "linked.json").symlink_to(outside)
    document["repeats"][1]["run_manifest"]["path"] = "linked.json"
    _rewrite_campaign(path, document)


def _missing_file(path: Path, document: dict[str, Any]) -> None:
    document["repeats"][4]["run_manifest"]["path"] = "repeat-6/manifest.json"
    _rewrite_campaign(path, document)


def _duplicate_manifest(path: Path, document: dict[str, Any]) -> None:
    document["repeats"][3]["run_manifest"] = document["repeats"][2]["run_manifest"]
    _rewrite_campaign(path, document)


def _changed_manifest(path: Path, _document: dict[str, Any]) -> None:
    run = path.parent / "repeat-2" / "manifest.json"
    run.write_bytes(run.read_bytes() + b"\n")


def _reused_run_id(path: Path, document: dict[str, Any]) -> None:
    _rebind_repeat(path, document, 4, {"run_id": "rtl-repeat-2"})


def _other_load_case(path: Path, document: dict[str, Any]) -> None:
    _rebind_repeat(path, document, 3, {"load_case": "cpu_stress"})


def _other_floor(path: Path, document: dict[str, Any]) -> None:
    run = json.loads((path.parent / "repeat-5" / "manifest.json").read_bytes())
    _rebind_repeat(path, document, 5, {"instrument": {**run["instrument"], "floor_ticks": 4}})


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (_missing_notes, "repeat campaign (root): 'operator_notes' is a required property"),
        (_wrong_schema, "repeat campaign schema: 'loop-timing-witness.repeat-campaign.v1' was"),
        (_reordered, "repeat_index values must run 1, 2, 3, ... in manifest order"),
        (_upward_path, "run manifest path must stay within the campaign directory"),
        (_outside_link, "run manifest is not a regular file inside the campaign: linked.json"),
        (_missing_file, "run manifest is not a regular file inside the campaign: repeat-6"),
        (_duplicate_manifest, "two repeats bind the same run manifest"),
        (_changed_manifest, "run manifest SHA-256 mismatch: repeat-2/manifest.json"),
        (_reused_run_id, "repeat 4 reuses run_id 'rtl-repeat-2'"),
        (
            _other_load_case,
            "repeat 3 differs from repeat 1 in load_case; incompatible runs are not pooled",
        ),
        (_other_floor, "repeat 5 differs from repeat 1 in instrument_floor_ticks"),
    ],
)
def test_unsound_campaigns_are_refused(
    make_repeat_campaign: MakeRepeatCampaign,
    change: Callable[[Path, dict[str, Any]], None],
    message: str,
) -> None:
    """Refuse schema, order, containment, digest, identity and agreement failures.

    Parameters
    ----------
    make_repeat_campaign
        Campaign of copied real RTL captures.
    change
        Mutation of the campaign or one repeat.
    message
        Start of the authored refusal.
    """
    path, document = make_repeat_campaign()
    change(path, document)
    with pytest.raises(ValueError, match=f"^{re.escape(message)}"):
        load_campaign(path)


def test_malformed_campaign_json_is_refused(make_repeat_campaign: MakeRepeatCampaign) -> None:
    """Refuse repeated JSON member names before schema validation.

    Parameters
    ----------
    make_repeat_campaign
        Campaign of copied real RTL captures.
    """
    path, _ = make_repeat_campaign(repeats=1)
    path.write_text(path.read_text()[:-2] + ', "campaign_id": "again"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_campaign(path)
