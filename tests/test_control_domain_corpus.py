# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — shared measurement-domain rule corpus of the control-run analysis

"""Keep the domain-rule corpus that both analysis implementations must reproduce.

Every case is a schema-valid change of the packaged measurement domain with
Python's cross-field findings. Integral floats are included because the schema
admits them as integers and Python computes and prints them as floats. The
native crate's unit tests read the same committed file.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import Any, Final

from conftest import REPOSITORY_ROOT
from loop_timing_witness.manifest_io import load_json_object
from loop_timing_witness.run_manifest import WIRE_FIELDS, WIRE_RECORD_BYTES
from loop_timing_witness.validate_measurement_domain import schema_locations, semantic_findings

DATA: Final = REPOSITORY_ROOT / "src/loop_timing_witness/data"
CORPUS: Final = REPOSITORY_ROOT / "analysis/rust/tests/data/control-domain-findings.json"
Change = Callable[[dict[str, Any]], None]


def _set(path: str, value: object) -> Change:
    """Return a change that sets one slash-separated member path.

    Parameters
    ----------
    path
        Member names and array indexes below the document.
    value
        New value.

    Returns
    -------
    Change
        In-place change.
    """

    def change(document: dict[str, Any]) -> None:
        node: Any = document
        parts = path.split("/")
        for part in parts[:-1]:
            node = node[int(part)] if isinstance(node, list) else node[part]
        last = parts[-1]
        if isinstance(node, list):
            node[int(last)] = value
        else:
            node[last] = value

    return change


def _floats(document: dict[str, Any]) -> None:
    """Turn every integer of the design contracts into an integral float.

    Parameters
    ----------
    document
        Domain changed in place.
    """
    pending: list[Any] = [document["design_contracts"]]
    while pending:
        node = pending.pop()
        members = node.items() if isinstance(node, dict) else enumerate(node)
        for key, value in list(members):
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                node[key] = float(value)
            elif isinstance(value, dict | list):
                pending.append(value)


def _profile_event(document: dict[str, Any]) -> None:
    """Declare one CONTROL event in the COMPUTE profile as well.

    Parameters
    ----------
    document
        Domain changed in place.
    """
    document["design_contracts"]["event_profiles"]["COMPUTE"]["occasional_events"].append(
        "DEADLINE"
    )


def _without_implementation(document: dict[str, Any]) -> None:
    """Remove the declared Gray-pointer implementation of the event buffer.

    Parameters
    ----------
    document
        Domain changed in place.
    """
    del document["design_contracts"]["event_fifo"]["implementation"]


CONTRACTS: Final = "design_contracts"
FIELDS: Final = f"{CONTRACTS}/event_record/fields"
CHANGES: Final[dict[str, list[Change]]] = {
    "packaged": [],
    "wrong project": [_set("project", "OTHER-PROJECT")],
    "wrong group": [_set("group", "OTHER-GROUP")],
    "wrong path": [_set("canonical_path", "03_CODE/OTHER/repositories/LOOP-TIMING-WITNESS")],
    "related repeated": [
        _set(
            "related_projects",
            [{"project": "A", "relation": "x"}, {"project": "A", "relation": "y"}],
        )
    ],
    "related self": [
        _set("related_projects", [{"project": "LOOP-TIMING-WITNESS", "relation": "x"}])
    ],
    "evidence declared": [
        _set("capabilities", ["c"]),
        _set("claims", ["c"]),
        _set("target_platform/verified_on_hardware", value=True),
    ],
    "field names repeat": [_set(f"{FIELDS}/1/name", "event_type")],
    "required field missing": [_set(f"{FIELDS}/3/name", "sequence")],
    "ticks field missing": [_set(f"{FIELDS}/4/name", "stamp")],
    "offset gap": [_set(f"{FIELDS}/3/offset_bytes", 5)],
    "record size": [_set(f"{CONTRACTS}/event_record/record_size_bytes", 17)],
    "narrow cycle": [_set(f"{FIELDS}/3/type", "u16"), _set(f"{FIELDS}/4/offset_bytes", 6)],
    "narrow ticks": [_set(f"{FIELDS}/4/type", "u32")],
    "resolution": [_set(f"{CONTRACTS}/timebase/resolution_ns", 11)],
    "counter wraps": [_set(f"{CONTRACTS}/timebase/counter_bits", 32)],
    "code missing": [_set(f"{CONTRACTS}/event_codes/ACT_LATE", None)],
    "codes repeat": [_set(f"{CONTRACTS}/event_codes/ACT_LATE", 3)],
    "events repeat": [_profile_event],
    "interval names repeat": [
        _set(f"{CONTRACTS}/event_profiles/CONTROL/intervals/1/name", "scheduling_latency")
    ],
    "interval foreign events": [
        _set(f"{CONTRACTS}/event_profiles/CONTROL/intervals/0/start_event", "INPUT_WRITE"),
        _set(f"{CONTRACTS}/event_profiles/CONTROL/intervals/0/end_event", "INPUT_WRITE"),
    ],
    "rate order": [_set(f"{CONTRACTS}/event_profiles/CONTROL/sample_rate_hz/default", 50)],
    "rate above maximum": [
        _set(f"{CONTRACTS}/event_profiles/CONTROL/sample_rate_hz/default", 30000)
    ],
    "control without rate": [_set(f"{CONTRACTS}/event_profiles/CONTROL/sample_rate_hz", None)],
    "gray depth": [_set(f"{CONTRACTS}/event_fifo/depth_records", 100)],
    "gray depth bounds": [_set(f"{CONTRACTS}/event_fifo/depth_records", 32768)],
    "no Gray implementation": [
        _without_implementation,
        _set(f"{CONTRACTS}/event_fifo/depth_records", 100),
    ],
    "shallow buffer": [
        _set(f"{CONTRACTS}/event_fifo/depth_records", 4096),
        _set(f"{CONTRACTS}/event_fifo/minimum_drain_rate_hz", 1),
    ],
    "placements repeat": [_set(f"{CONTRACTS}/controller_placements/1/identifier", "fabric_logic")],
    "integral floats": [_floats],
    "float offset gap": [_floats, _set(f"{FIELDS}/3/offset_bytes", 5.0)],
    "float record size": [_floats, _set(f"{CONTRACTS}/event_record/record_size_bytes", 17.0)],
    "float cycles": [
        _floats,
        _set(f"{FIELDS}/3/type", "u8"),
        _set(f"{FIELDS}/4/offset_bytes", 5.0),
        _set(f"{CONTRACTS}/event_record/record_size_bytes", 13.0),
    ],
    "float gray depth": [_floats, _set(f"{CONTRACTS}/event_fifo/depth_records", 96.0)],
    "float counter wraps": [_floats, _set(f"{CONTRACTS}/timebase/counter_bits", 30.0)],
    "float resolution": [_floats, _set(f"{CONTRACTS}/timebase/resolution_ns", 9.0)],
}


def _wire(document: dict[str, Any]) -> bool:
    """Tell whether the event record equals the 16-byte host wire layout.

    Parameters
    ----------
    document
        Schema-valid domain.

    Returns
    -------
    bool
        The comparison that ``run_manifest`` applies after the rules pass.
    """
    record = document["design_contracts"]["event_record"]
    observed = tuple(
        (item["name"], item["offset_bytes"], item["type"]) for item in record["fields"]
    )
    return bool(record["record_size_bytes"] == WIRE_RECORD_BYTES and observed == WIRE_FIELDS)


def corpus() -> dict[str, Any]:
    """Build the complete domain-rule corpus.

    Returns
    -------
    dict[str, Any]
        Cases with the changed domain, Python's findings and the wire result.
    """
    packaged = load_json_object(DATA / "measurement-domain.json")
    schema = load_json_object(DATA / "measurement-domain.schema.json")
    cases = []
    for name, changes in CHANGES.items():
        document = copy.deepcopy(packaged)
        for change in changes:
            change(document)
        codes = document["design_contracts"]["event_codes"]
        for code in [key for key, value in codes.items() if value is None]:
            del codes[code]
        assert schema_locations(document, schema) == [], name
        cases.append(
            {
                "name": name,
                "document": document,
                "findings": semantic_findings(document),
                "wire": _wire(document),
            }
        )
    return {"schema": "loop-timing-witness.control-domain-findings.v1", "cases": cases}


def test_committed_corpus_equals_python_findings() -> None:
    """The committed corpus is exactly what Python finds for every change."""
    text = json.dumps(corpus(), ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    expected = text + "\n"
    assert CORPUS.read_text(encoding="utf-8") == expected


def test_every_rule_family_and_float_text_is_held() -> None:
    """Each rule family fails at least once and float values print as floats."""
    cases = {case["name"]: case for case in corpus()["cases"]}
    assert cases["packaged"]["findings"] == []
    assert cases["packaged"]["wire"]
    assert cases["integral floats"]["findings"] == []
    assert cases["integral floats"]["wire"]
    findings = [finding for case in cases.values() for finding in case["findings"]]
    for prefix in (
        "project:",
        "group:",
        "canonical_path:",
        "related_projects:",
        "capabilities:",
        "claims:",
        "target_platform",
        "event_record",
        "timebase.resolution_ns",
        "timebase.counter_bits",
        "event_codes:",
        "event_profiles",
        "event_fifo:",
        "controller_placements:",
    ):
        assert any(finding.startswith(prefix) for finding in findings), prefix
    assert any("cycle: offset must be 4.0 (" in finding for finding in findings)
    assert any("record size is 17.0" in finding for finding in findings)
    assert any("1000000.0 cycles per repeat" in finding for finding in findings)
    assert CORPUS.with_name(CORPUS.name + ".license").is_file()
