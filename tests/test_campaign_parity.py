# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — repeat campaign command through both analysis implementations

"""Run the Python and the native repeat campaign commands on the same real campaigns.

Both commands must exit with the same status, print the same lines and
publish byte-equal report directories, or refuse with the same text and
publish nothing. The repeats are copies of real Icarus captures.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

import pytest
from control_rust_support import python_command, rust_campaign_command
from test_campaign_analysis import (
    _delay_from_first_write,
    _last_record_at,
    _rewrite_events,
    _run_reports,
    _without_cycle_one_sample_read,
)
from test_control_run_parity import _board

from conftest import write_bound_json

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from conftest import MakeRepeatCampaign

OUTPUTS = ("python-report", "rust-report")
"""Report directories of the Python and the native command, beside the campaign."""


def _rewrite(path: Path, document: dict[str, Any]) -> None:
    """Replace the campaign manifest with a changed document.

    Parameters
    ----------
    path
        Campaign manifest path.
    document
        Complete changed campaign document.
    """
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def _edit_run(
    path: Path, document: dict[str, Any], index: int, edit: Callable[[dict[str, Any]], None]
) -> None:
    """Change one repeat's run manifest in place and bind its new digest.

    Parameters
    ----------
    path
        Campaign manifest path.
    document
        Campaign document, updated in place and rewritten.
    index
        One-based repeat index.
    edit
        Change of the decoded run manifest.
    """
    entry = document["repeats"][index - 1]
    run_path = path.parent / entry["run_manifest"]["path"]
    manifest = json.loads(run_path.read_bytes())
    edit(manifest)
    entry["run_manifest"] = write_bound_json(run_path, manifest)
    _rewrite(path, document)


def _files(directory: Path) -> dict[str, bytes]:
    """Read every file of one report directory.

    Parameters
    ----------
    directory
        Published report directory.

    Returns
    -------
    dict[str, bytes]
        Bytes by file name.
    """
    return {item.name: item.read_bytes() for item in sorted(directory.iterdir())}


def _same(path: Path, tmp_path: Path) -> dict[str, Any]:
    """Run both commands on one campaign and require the same outcome.

    Parameters
    ----------
    path
        Campaign manifest.
    tmp_path
        Working directory of both commands and owner of their outputs.

    Returns
    -------
    dict[str, Any]
        The Python command's status and printed text.
    """
    python = python_command([str(path), "--output-dir", OUTPUTS[0]], tmp_path, campaign=True)
    rust = rust_campaign_command([str(path), "--output-dir", OUTPUTS[1]], tmp_path, tmp_path / "rs")
    assert rust == {**python, "stdout": python["stdout"].replace(*OUTPUTS)}
    published = (tmp_path / OUTPUTS[0]).exists()
    assert (tmp_path / OUTPUTS[1]).exists() is published
    if published:
        assert _files(tmp_path / OUTPUTS[1]) == _files(tmp_path / OUTPUTS[0])
    return python


def _duplicate_member(path: Path, document: dict[str, Any]) -> None:
    """Repeat a member name holding an unpaired surrogate in repeat 2's run manifest.

    Parameters
    ----------
    path
        Campaign manifest path.
    document
        Campaign document, updated in place and rewritten.
    """
    run = path.parent / "repeat-2" / "manifest.json"
    run.write_text(run.read_text()[:-2] + ', "\\ud800": 1, "\\ud800": 2}\n', encoding="utf-8")
    document["repeats"][1]["run_manifest"]["sha256"] = hashlib.sha256(run.read_bytes()).hexdigest()
    _rewrite(path, document)


def _integral_floats(path: Path, document: dict[str, Any]) -> None:
    """Declare counts and an index as integral floats, which the schemas admit.

    Repeat 1 declares 3.0 cycles and 0.0 warm-up cycles, so the fewest analysed
    cycles are the float 3.0; repeat 2 has index 2.0 and no reboot.

    Parameters
    ----------
    path
        Campaign manifest path.
    document
        Campaign document, updated in place and rewritten.
    """
    _edit_run(path, document, 1, lambda run: run.update(cycle_count=3.0, warmup_cycles=0.0))
    document["repeats"][1].update(repeat_index=2.0, rebooted_before_run=False)
    _rewrite(path, document)


def _tick_range(path: Path, document: dict[str, Any]) -> None:
    """Make two valid COMPUTE repeats span exactly the 64-bit tick range together.

    Parameters
    ----------
    path
        Campaign manifest path.
    document
        Campaign document, updated in place and rewritten.
    """
    second = _run_reports(path, document, [2])[0][0]["events"]["duration_ticks"]
    start = int.from_bytes((path.parent / "repeat-1" / "events.bin").read_bytes()[8:16], "little")
    _rewrite_events(path, document, 1, _last_record_at(start + 2**64 - 1 - second))


def _board_repeats(path: Path, document: dict[str, Any]) -> None:
    """Declare every repeat a board run whose artefacts are its real source file.

    Parameters
    ----------
    path
        Campaign manifest path.
    document
        Campaign document, updated in place and rewritten.
    """
    for index in range(1, len(document["repeats"]) + 1):
        _edit_run(path, document, index, _board)


def _invalid_and_refused(path: Path, document: dict[str, Any]) -> None:
    """Overflow repeat 4, cut repeat 3's events and change repeat 5's events unbound.

    Parameters
    ----------
    path
        Campaign manifest path.
    document
        Campaign document, updated in place and rewritten.
    """
    _edit_run(path, document, 4, lambda run: run["instrument"].update(fifo_overflow_count=1))
    _rewrite_events(path, document, 3, lambda events: events[:-1])
    _append_unbound(path, 5)


def _append_unbound(path: Path, index: int) -> None:
    """Append one zero record to a repeat's events without binding its digest.

    Parameters
    ----------
    path
        Campaign manifest path.
    index
        One-based repeat index.
    """
    events = path.parent / f"repeat-{index}" / "events.bin"
    events.write_bytes(events.read_bytes() + bytes(16))


def _short_without_reboot(path: Path, document: dict[str, Any]) -> None:
    """Declare that repeat 2 did not reboot.

    Parameters
    ----------
    path
        Campaign manifest path.
    document
        Campaign document, updated in place and rewritten.
    """
    document["repeats"][1]["rebooted_before_run"] = False
    _rewrite(path, document)


def _refused_at_load(path: Path, _document: dict[str, Any]) -> None:
    """Change both repeats' events without binding them, so neither run loads.

    Parameters
    ----------
    path
        Campaign manifest path.
    _document
        Unchanged campaign document.
    """
    for index in (1, 2):
        _append_unbound(path, index)


def _refused_at_analysis(path: Path, document: dict[str, Any]) -> None:
    """Cut and rebind both repeats' events, so both load but neither is analysed.

    Parameters
    ----------
    path
        Campaign manifest path.
    document
        Campaign document, updated in place and rewritten.
    """
    for index in (1, 2):
        _rewrite_events(path, document, index, lambda events: events[:-1])


def _final_separator(path: Path, document: dict[str, Any]) -> None:
    """Bind repeat 1's run manifest by a path ending with a separator.

    Parameters
    ----------
    path
        Campaign manifest path.
    document
        Campaign document, updated in place and rewritten.
    """
    document["repeats"][0]["run_manifest"]["path"] = "repeat-1/manifest.json/"
    _rewrite(path, document)


def _line_feed_identifier(path: Path, document: dict[str, Any]) -> None:
    """Name the campaign with the final line feed its schema pattern admits.

    Parameters
    ----------
    path
        Campaign manifest path.
    document
        Campaign document, updated in place and rewritten.
    """
    document["campaign_id"] = "rtl-campaign\n"
    _rewrite(path, document)


REPORTS: dict[str, tuple[dict[str, Any], Callable[[Path, dict[str, Any]], None] | None]] = {
    "complete": ({"run_plan": {"cycles_per_repeat": 3, "repeats": 5}}, None),
    "incomplete": ({}, None),
    "COMPUTE": ({"repeats": 2, "profile": "COMPUTE"}, None),
    "delayed repeat": (
        {},
        lambda path, document: _rewrite_events(
            path, document, 2, lambda events: _delay_from_first_write(events, 3)
        ),
    ),
    "invalid and refused": ({}, _invalid_and_refused),
    "gapped cycles": (
        {"repeats": 2},
        lambda path, document: _rewrite_events(path, document, 1, _without_cycle_one_sample_read),
    ),
    "short without reboot": (
        {"repeats": 3, "run_plan": {"cycles_per_repeat": 3, "repeats": 5}},
        _short_without_reboot,
    ),
    "refused at load": ({"repeats": 2}, _refused_at_load),
    "refused at analysis": ({"repeats": 2}, _refused_at_analysis),
    "invalid only": (
        {"repeats": 1},
        lambda path, document: _edit_run(
            path, document, 1, lambda run: run["instrument"].update(fifo_overflow_count=2)
        ),
    ),
    "surrogate refusal": ({"repeats": 2}, _duplicate_member),
    "integral floats": ({}, _integral_floats),
    "integral coefficient": (
        {"repeats": 2},
        lambda path, document: _edit_run(
            path, document, 2, lambda run: run["controller"]["coefficients"].update(kp=1.0)
        ),
    ),
    "tick range": ({"repeats": 2, "profile": "COMPUTE"}, _tick_range),
    "final separator": ({"repeats": 2}, _final_separator),
    "line-feed campaign id": ({"repeats": 2}, _line_feed_identifier),
    "board": ({"repeats": 2}, _board_repeats),
}


@pytest.mark.parametrize("variant", list(REPORTS))
def test_campaign_reports_are_byte_equal(
    variant: str, make_repeat_campaign: MakeRepeatCampaign, tmp_path: Path
) -> None:
    """Publish byte-equal campaign reports with the same status and lines.

    Parameters
    ----------
    variant
        Campaign shape: complete or incomplete plans, COMPUTE repeats, a delayed
        repeat, invalid and refused repeats, gapped cycles, a short campaign with
        a missed reboot, repeats refused at load or analysis, only invalid
        repeats, a refusal naming an unpaired surrogate, integral floats, an
        integral-float coefficient, a pooled duration at the 64-bit tick range,
        a run manifest path with a final separator, a campaign identifier ending
        with a line feed, or board repeats.
    make_repeat_campaign
        Campaign of copied real captures.
    tmp_path
        Working directory of both commands.
    """
    options, change = REPORTS[variant]
    path, document = make_repeat_campaign(**options)
    if change is not None:
        change(path, document)
    outcome = _same(path, tmp_path)
    assert outcome["status"] in {0, 2}, outcome["stderr"]
    assert (outcome["status"] == 0) is (variant == "complete")


def _changed_configuration(
    index: int, edit: Callable[[dict[str, Any]], None]
) -> Callable[..., None]:
    """Return a change of one repeat's run manifest.

    Parameters
    ----------
    index
        One-based repeat index.
    edit
        Change of the decoded run manifest.

    Returns
    -------
    Callable[..., None]
        Change of the campaign.
    """
    return lambda path, document: _edit_run(path, document, index, edit)


def _campaign_text(change: Callable[[str], str]) -> Callable[..., None]:
    """Return a change of the campaign manifest's text.

    Parameters
    ----------
    change
        Edit of the complete text.

    Returns
    -------
    Callable[..., None]
        Change of the campaign.
    """
    return lambda path, _: path.write_text(
        change(path.read_text(encoding="utf-8")), encoding="utf-8"
    )


def _campaign_document(edit: Callable[[dict[str, Any]], object]) -> Callable[..., None]:
    """Return a change of the decoded campaign document.

    Parameters
    ----------
    edit
        Change of the decoded document.

    Returns
    -------
    Callable[..., None]
        Change of the campaign.
    """

    def change(path: Path, document: dict[str, Any]) -> None:
        """Edit the document and rewrite the campaign.

        Parameters
        ----------
        path
            Campaign manifest path.
        document
            Campaign document, updated in place and rewritten.
        """
        edit(document)
        _rewrite(path, document)

    return change


def _outside_link(path: Path, document: dict[str, Any]) -> None:
    """Bind a link to a run manifest outside the campaign directory.

    Parameters
    ----------
    path
        Campaign manifest path.
    document
        Campaign document, updated in place and rewritten.
    """
    outside = path.parent.parent / "outside.json"
    outside.write_bytes((path.parent / "repeat-2" / "manifest.json").read_bytes())
    (path.parent / "linked.json").symlink_to(outside)
    document["repeats"][1]["run_manifest"]["path"] = "linked.json"
    _rewrite(path, document)


def _unreadable(relative: str) -> Callable[..., None]:
    """Return a change that removes every permission of one campaign file.

    Parameters
    ----------
    relative
        File path below the campaign directory.

    Returns
    -------
    Callable[..., None]
        Change of the campaign.
    """
    return lambda path, _: (path.parent / relative).chmod(0)


def _reordered(document: dict[str, Any]) -> None:
    """Swap the first two repeat indexes.

    Parameters
    ----------
    document
        Campaign document changed in place.
    """
    document["repeats"][0]["repeat_index"], document["repeats"][1]["repeat_index"] = 2, 1


def _negative_coefficient(path: Path, document: dict[str, Any]) -> None:
    """Give repeat 1 the coefficient 0 and repeat 2 the coefficient -1.0.

    Parameters
    ----------
    path
        Campaign manifest path.
    document
        Campaign document, updated in place and rewritten.
    """
    _edit_run(path, document, 1, lambda run: run["controller"]["coefficients"].update(kp=0))
    _edit_run(path, document, 2, lambda run: run["controller"]["coefficients"].update(kp=-1.0))


def _other_hardware(path: Path, document: dict[str, Any]) -> None:
    """Declare board repeats whose second names another Libero version.

    Parameters
    ----------
    path
        Campaign manifest path.
    document
        Campaign document, updated in place and rewritten.
    """
    _board_repeats(path, document)
    _edit_run(path, document, 2, lambda run: run["hardware_artifacts"].update(libero_version="x"))


def _campaign_directory(path: Path, _document: dict[str, Any]) -> None:
    """Replace the campaign manifest with a directory of its name.

    Parameters
    ----------
    path
        Campaign manifest path.
    _document
        Unchanged campaign document.
    """
    path.unlink()
    path.mkdir()


def _beyond_the_tick_range(path: Path, document: dict[str, Any]) -> None:
    """Make two valid COMPUTE repeats span one tick more than the 64-bit range.

    Parameters
    ----------
    path
        Campaign manifest path.
    document
        Campaign document, updated in place and rewritten.
    """
    _tick_range(path, document)
    events = (path.parent / "repeat-1" / "events.bin").read_bytes()
    last = int.from_bytes(events[-8:], "little")
    _rewrite_events(path, document, 1, _last_record_at(last + 1))


REFUSALS: dict[str, tuple[dict[str, Any], Callable[..., None]]] = {
    "missing notes": ({}, _campaign_document(lambda document: document.pop("operator_notes"))),
    "wrong schema": (
        {},
        _campaign_document(lambda document: document.update(schema="loop-timing-witness.x.v1")),
    ),
    "reordered": ({}, _campaign_document(_reordered)),
    "upward path": (
        {},
        _campaign_document(
            lambda document: document["repeats"][1]["run_manifest"].update(
                path="repeat-2/../repeat-2/manifest.json"
            )
        ),
    ),
    "outside link": ({}, _outside_link),
    "missing run manifest": (
        {},
        _campaign_document(
            lambda document: document["repeats"][4]["run_manifest"].update(
                path="repeat-6/manifest.json"
            )
        ),
    ),
    "duplicate run manifest": (
        {},
        _campaign_document(
            lambda document: document["repeats"][3].update(
                run_manifest=document["repeats"][2]["run_manifest"]
            )
        ),
    ),
    "changed run manifest": (
        {},
        lambda path, _: (path.parent / "repeat-2" / "manifest.json").write_bytes(
            (path.parent / "repeat-2" / "manifest.json").read_bytes() + b"\n"
        ),
    ),
    "reused run id": ({}, _changed_configuration(4, lambda run: run.update(run_id="rtl-repeat-2"))),
    "other load case": ({}, _changed_configuration(3, lambda run: run.update(load_case="cpu"))),
    "other floor": (
        {},
        _changed_configuration(5, lambda run: run["instrument"].update(floor_ticks=4)),
    ),
    "negative coefficient": ({"repeats": 2}, _negative_coefficient),
    "extra coefficient": (
        {"repeats": 2},
        _changed_configuration(2, lambda run: run["controller"]["coefficients"].update(ki=0.5)),
    ),
    "renamed coefficient": (
        {"repeats": 2},
        _changed_configuration(2, lambda run: run["controller"].update(coefficients={"kd": 1})),
    ),
    "fault schedule": (
        {"repeats": 2},
        _changed_configuration(2, lambda run: run.update(fault_schedule=[])),
    ),
    "tracking sampling": (
        {"repeats": 2},
        _changed_configuration(2, lambda run: run.update(tracking_sampling="complete")),
    ),
    "hardware": ({"repeats": 2}, _other_hardware),
    "wide integer": (
        {"repeats": 1},
        _campaign_text(
            lambda text: text.replace('"repeat_index": 1', '"repeat_index": 1' + "0" * 20)
        ),
    ),
    "unpaired surrogate": (
        {"repeats": 1},
        _campaign_text(
            lambda text: text.replace('"operator_notes": "', '"operator_notes": "\\ud800')
        ),
    ),
    "nesting 65": (
        {"repeats": 1},
        _campaign_text(lambda text: text[:-2] + ', "deep": ' + "[" * 64 + "]" * 64 + "}\n"),
    ),
    "repeated member": (
        {"repeats": 1},
        _campaign_text(lambda text: text[:-2] + ', "campaign_id": "again"}\n'),
    ),
    "missing campaign": ({"repeats": 1}, lambda path, _: path.unlink()),
    "campaign directory": ({"repeats": 1}, _campaign_directory),
    "unreadable run manifest": ({"repeats": 2}, _unreadable("repeat-2/manifest.json")),
    "unreadable events": ({"repeats": 2}, _unreadable("repeat-2/events.bin")),
    "unreadable source": ({"repeats": 2}, _unreadable("repeat-2/event_capture.vvp")),
    "beyond the tick range": ({"repeats": 2, "profile": "COMPUTE"}, _beyond_the_tick_range),
}


@pytest.mark.parametrize("variant", list(REFUSALS))
def test_campaign_refusals_are_identical(
    variant: str, make_repeat_campaign: MakeRepeatCampaign, tmp_path: Path
) -> None:
    """Refuse an unsound campaign with the same text and publish nothing.

    Parameters
    ----------
    variant
        Schema, order, path, digest, identity, configuration, JSON bound, file
        or pooled-range defect of the campaign or one of its repeats.
    make_repeat_campaign
        Campaign of copied real captures.
    tmp_path
        Working directory of both commands.
    """
    options, change = REFUSALS[variant]
    path, document = make_repeat_campaign(**options)
    change(path, document)
    try:
        outcome = _same(path, tmp_path)
    finally:
        for item in path.parent.rglob("*"):
            if not item.is_symlink():
                item.chmod(0o700 if item.is_dir() else 0o600)
    assert outcome["status"] == 1, outcome
    assert outcome["stderr"].startswith("repeat campaign: FAIL: "), outcome
    assert not (tmp_path / OUTPUTS[0]).exists()


@pytest.mark.parametrize("defect", ["existing output", "missing parent"])
def test_publication_refusals_are_identical(
    defect: str, make_repeat_campaign: MakeRepeatCampaign, tmp_path: Path
) -> None:
    """Refuse an existing output or a missing output parent with the same text.

    Parameters
    ----------
    defect
        The output exists, or its parent does not.
    make_repeat_campaign
        Campaign of copied real captures.
    tmp_path
        Working directory of both commands.
    """
    path, _ = make_repeat_campaign(repeats=1)
    outputs = (
        OUTPUTS if defect == "existing output" else tuple(f"absent/{name}" for name in OUTPUTS)
    )
    if defect == "existing output":
        for output in outputs:
            (tmp_path / output).mkdir()
    python = python_command([str(path), "--output-dir", outputs[0]], tmp_path, campaign=True)
    rust = rust_campaign_command([str(path), "--output-dir", outputs[1]], tmp_path, tmp_path / "rs")
    assert python["status"] == 1
    assert rust == {**python, "stderr": python["stderr"].replace(*OUTPUTS)}


def test_a_campaign_with_an_amp_capture_is_refused_by_the_native_command(
    make_repeat_campaign: MakeRepeatCampaign, tmp_path: Path
) -> None:
    """Refuse a campaign whose repeat binds an AMP capture, which only Python completes.

    Parameters
    ----------
    make_repeat_campaign
        Campaign of copied real captures.
    tmp_path
        Working directory of the native command.
    """
    path, document = make_repeat_campaign(repeats=2)

    def amp(run: dict[str, Any]) -> None:
        """Declare an AMP placement with its capture.

        Parameters
        ----------
        run
            Decoded run manifest.
        """
        run.update(placement="bare_metal_amp", tracking_sampling="observed")
        run["files"]["power"] = None
        run["amp_capture"] = run["files"]["events"].copy()

    for index in (1, 2):
        _edit_run(path, document, index, amp)
    rust = rust_campaign_command([str(path), "--output-dir", "report"], tmp_path, tmp_path / "rs")
    assert rust == {
        "status": 1,
        "stdout": "",
        "stderr": "repeat campaign: FAIL: AMP capture completion is not analysed by the native "
        "analysis\n",
    }
    assert not (tmp_path / "report").exists()
