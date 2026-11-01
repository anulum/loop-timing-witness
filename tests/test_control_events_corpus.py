# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — shared events-block corpus of the control-run analysis

"""Keep the events-block corpus that both analysis implementations must reproduce.

Each case is a run declaration, the packaged measurement-domain contracts and
decoded events, with the ``events`` block and interval rows of Python's
``events_block`` or its refusal. The cases cover jitter coverage states,
fault, deadline and safe-state pairing, every refusal, integral-float cycle
counts and quantile interpolation of large tick values. The native crate's
unit tests read the same committed file.
"""

from __future__ import annotations

import json
from typing import Any, Final

from conftest import REPOSITORY_ROOT
from loop_timing_witness.analyze_run import events_block
from loop_timing_witness.event_stream import Event
from loop_timing_witness.manifest_io import load_json_object

CORPUS: Final = REPOSITORY_ROOT / "analysis/rust/tests/data/control-events-blocks.json"
CONTRACTS: Final = load_json_object(REPOSITORY_ROOT / "measurement-domain.json")["design_contracts"]
LARGE: Final = 2**60


def _cycle(cycle: int, base: int, read: int, write: int | None, deadline: int = 400) -> list[Any]:
    """Return one CONTROL cycle's periodic events.

    Parameters
    ----------
    cycle
        Cycle number.
    base
        Tick of SAMPLE_READY.
    read
        Ticks from SAMPLE_READY to SAMPLE_READ.
    write
        Ticks from SAMPLE_READY to ACT_WRITE, or ``None`` for no write.
    deadline
        Ticks from SAMPLE_READY to DEADLINE.

    Returns
    -------
    list[Any]
        ``[name, cycle, ticks]`` events in time order.
    """
    events = [["SAMPLE_READY", cycle, base], ["SAMPLE_READ", cycle, base + read]]
    if write is not None:
        events.append(["ACT_WRITE", cycle, base + write])
    events.append(["DEADLINE", cycle, base + deadline])
    return sorted(events, key=lambda event: event[2])


def _run(
    cycles: float, warmup: float, faults: list[int], profile: str = "CONTROL"
) -> dict[str, Any]:
    """Return the run members that the events block reads.

    Parameters
    ----------
    cycles
        Declared cycle count.
    warmup
        Declared warm-up cycles.
    faults
        Scheduled fault cycles.
    profile
        Event profile.

    Returns
    -------
    dict[str, Any]
        Partial run manifest.
    """
    schedule = [{"cycle": cycle, "kind": "delay", "delay_periods": 1} for cycle in faults]
    return {
        "profile": profile,
        "cycle_count": cycles,
        "warmup_cycles": warmup,
        "fault_schedule": schedule,
    }


def _cases() -> dict[str, tuple[dict[str, Any], list[list[Any]]]]:
    """Return every named run and event list of the corpus.

    Returns
    -------
    dict[str, tuple[dict[str, Any], list[list[Any]]]]
        Run members and ``[name, cycle, ticks]`` events.
    """
    steady = [
        event
        for cycle in range(5)
        for event in _cycle(cycle, 1000 * cycle, 10 + cycle, 30 + 3 * cycle)
    ]
    gapped = [
        event for cycle in (0, 1, 3, 4) for event in _cycle(cycle, 1000 * cycle, 10, 30 + cycle)
    ]
    faults = [
        *_cycle(0, 0, 10, 30),
        ["FAULT_INJECTED", 1, 1005],
        *_cycle(1, 1000, 10, None),
        ["FAULT_DETECTED", 1, 1500],
        *_cycle(2, 2000, 10, 450),
        *_cycle(3, 3000, 10, None),
        ["SAFE_STATE", 3, 3500],
        *_cycle(4, 4000, 10, None),
        ["SAFE_STATE", 4, 4500],
    ]
    faults = sorted(faults, key=lambda event: (event[1], event[2]))
    large = [
        event
        for cycle in range(7)
        for event in _cycle(cycle, LARGE + 1000 * cycle, 3 * cycle + 1, 40)
    ]
    compute = [
        [name, cycle, 1000 * cycle + offset]
        for cycle in range(3)
        for offset, name in enumerate(
            ("INPUT_WRITE", "COMPUTE_START", "COMPUTE_DONE", "OUTPUT_READ", "INTERRUPT_ENTRY")
        )
    ]
    return {
        "steady with warm-up": (_run(5, 1, []), steady),
        "gapped cycles": (_run(5, 0, []), gapped),
        "one analysed cycle": (_run(5, 4, []), steady),
        "warm-up excludes every event": (_run(9, 8, []), steady),
        "faults, misses and safe states": (_run(5, 0, [1]), faults),
        "large ticks": (_run(7, 0, []), large),
        "integral float counts": (_run(5.0, 1.0, []), steady),
        "float with one analysed cycle": (_run(5.0, 4.0, []), steady),
        "compute": (_run(3, 0, [], "COMPUTE"), compute),
        "schedule count differs": (_run(5, 0, [1, 2]), faults),
        "schedule cycle differs": (_run(5, 0, [2]), faults),
        "negative interval": (
            _run(1, 0, []),
            [["SAMPLE_READY", 0, 50], ["ACT_WRITE", 0, 60], ["SAMPLE_READ", 0, 40]],
        ),
        "overlapping injections": (
            _run(3, 0, [0, 1]),
            [["FAULT_INJECTED", 0, 5], ["FAULT_INJECTED", 1, 10]],
        ),
        "detection without injection": (_run(2, 0, []), [["FAULT_DETECTED", 1, 10]]),
        "detection before injection": (
            _run(2, 0, [0]),
            [["FAULT_INJECTED", 0, 20], ["FAULT_DETECTED", 1, 10]],
        ),
        "safe state without miss": (_run(2, 0, []), [["SAFE_STATE", 1, 10]]),
        "safe state before its miss": (
            _run(2, 0, []),
            [["DEADLINE", 0, 100], ["SAFE_STATE", 0, 50]],
        ),
    }


def corpus() -> dict[str, Any]:
    """Build the complete events-block corpus.

    Returns
    -------
    dict[str, Any]
        Contracts and cases with Python's block and rows or refusal.
    """
    cases = []
    for name, (run, listed) in _cases().items():
        events = tuple(Event(event_name, cycle, ticks) for event_name, cycle, ticks in listed)
        case: dict[str, Any] = {"name": name, "run": run, "events": listed}
        try:
            block, rows = events_block(run, CONTRACTS, events)
        except ValueError as error:
            case["refusal"] = str(error)
        else:
            case["block"] = block
            case["rows"] = [[row["cycle"], row["interval"], row["ticks"]] for row in rows]
        cases.append(case)
    return {
        "schema": "loop-timing-witness.control-events-blocks.v1",
        "contracts": CONTRACTS,
        "cases": cases,
    }


def test_committed_corpus_equals_python_blocks() -> None:
    """The committed corpus is exactly what Python's events block gives."""
    text = json.dumps(corpus(), ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    assert CORPUS.read_text(encoding="utf-8") == text + "\n"


def test_corpus_covers_every_state_and_refusal() -> None:
    """Hold every jitter state, the fault pairing and each refusal text."""
    cases = {case["name"]: case for case in corpus()["cases"]}
    statuses = {
        item["status"]
        for case in cases.values()
        if "block" in case
        for item in case["block"]["jitter"].values()
    }
    assert statuses == {"available", "partial", "unavailable"}
    control = cases["faults, misses and safe states"]["block"]["control"]
    assert control["fault_detections"] == 1
    assert control["safe_state_events"] == 2
    assert cases["integral float counts"]["block"]["cycle_count"] == 4.0
    assert isinstance(cases["integral float counts"]["block"]["cycle_count"], float)
    refusals = {case["refusal"].split(": ", 1)[-1] for case in cases.values() if "refusal" in case}
    assert refusals == {
        "fault schedule does not match captured FAULT_INJECTED events",
        "scheduling_latency ends before it starts",
        "fault injection overlaps an undetected fault",
        "fault detection lacks a prior injection",
        "safe state lacks a prior missed deadline",
    }
    assert CORPUS.with_name(CORPUS.name + ".license").is_file()
