# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — shared schema location corpus of the control-run analysis

"""Keep the schema-location corpus that both analysis implementations must reproduce.

The corpus mutates one valid run manifest per declaration variant and the
packaged measurement domain, node by node: wrong types, removed and unexpected
members, empty and repeated arrays, pattern, constant, enumeration and bound
violations. Every case records the locations Python's validator reports. The
native crate's unit tests read the same committed file, so both languages are
held to identical refusals.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Final

from conftest import REPOSITORY_ROOT
from loop_timing_witness.manifest_io import load_json_object
from loop_timing_witness.validate_measurement_domain import schema_locations

DATA: Final = REPOSITORY_ROOT / "src/loop_timing_witness/data"
CORPUS: Final = REPOSITORY_ROOT / "analysis/rust/tests/data/control-schema-locations.json"
FILE: Final = {"path": "events.bin", "sha256": "0" * 64}
REPLACEMENTS: Final[tuple[object, ...]] = (None, True, 1.5, "x", [], {})


def _run_manifest() -> dict[str, Any]:
    """Return one valid CONTROL simulation run declaration.

    Returns
    -------
    dict[str, Any]
        Schema-valid run manifest.
    """
    return {
        "schema": "loop-timing-witness.run-manifest.v1",
        "run_id": "rtl-capture-test",
        "started_utc": "2026-09-26T00:00:00Z",
        "source": {
            "kind": "rtl_simulation",
            "tool": "Icarus Verilog",
            "version": "12",
            "files": [FILE],
        },
        "measurement_domain": FILE,
        "profile": "CONTROL",
        "placement": "fabric_logic",
        "sample_period_ticks": 5000,
        "cycle_count": 3,
        "warmup_cycles": 0,
        "load_case": "idle",
        "controller": {"name": "pid_anti_windup", "coefficients": {"kp": 1}},
        "plant": {
            "name": "second_order_mechanical",
            "fixed_point_format": "Q16.16",
            "tracking_unit": "x",
        },
        "fault_schedule": [{"cycle": 2, "kind": "delay", "delay_periods": 1}],
        "files": {"events": FILE, "tracking": FILE, "power": FILE},
        "hardware_artifacts": None,
        "instrument": {
            "fifo_overflow_count": 0,
            "floor_ticks": None,
            "known_period_pass": False,
            "injected_delay_pass": False,
            "overflow_pass": False,
            "bus_offset_pass": False,
        },
        "environment": {"room_temperature_c": None, "board_supply_only": False},
        "operator_notes": "RTL simulation only",
    }


def _run_variants() -> dict[str, dict[str, Any]]:
    """Return valid run declarations that select every conditional branch of the schema.

    Returns
    -------
    dict[str, dict[str, Any]]
        Declarations keyed by a descriptive name.
    """
    control = _run_manifest()
    compute = {
        **control,
        "profile": "COMPUTE",
        "controller": None,
        "plant": None,
        "sample_period_ticks": None,
        "files": {**control["files"], "tracking": None},
    }
    board = {
        **control,
        "source": {**control["source"], "kind": "board"},
        "hardware_artifacts": dict.fromkeys(
            ("bitstream", "firmware", "linux_image", "controller_binary"), FILE
        )
        | {"libero_version": "2025.1", "toolchain_version": "13"},
        "instrument": {
            **control["instrument"],
            "floor_ticks": 2,
            **dict.fromkeys(
                ("known_period_pass", "injected_delay_pass", "overflow_pass", "bus_offset_pass"),
                True,
            ),
        },
        "environment": {"room_temperature_c": 21.5, "board_supply_only": True},
    }
    amp = {
        **control,
        "amp_capture": FILE,
        "tracking_sampling": "observed",
        "placement": "bare_metal_amp",
        "files": {**control["files"], "power": None},
    }
    native = {**control, "native_metadata": FILE, "host_load": FILE, "load_case": "cpu"}
    return {"control": control, "compute": compute, "board": board, "amp": amp, "native": native}


def _mutations(value: object) -> list[dict[str, object]]:
    """Return the single-node changes of one value.

    Parameters
    ----------
    value
        Valid node.

    Returns
    -------
    list[dict[str, object]]
        ``{"set": replacement}``, ``{"remove": member}`` or ``{"add": member}``;
        an added member has the value 1.
    """
    replacements: list[object] = [item for item in REPLACEMENTS if item != value]
    changes: list[dict[str, object]] = []
    if isinstance(value, dict):
        changes.extend({"remove": key} for key in sorted(value))
        changes.append({"add": "unexpected_member"})
    elif isinstance(value, list) and value:
        replacements.extend([[], [value[0], *value]])
    elif isinstance(value, str):
        replacements.extend(["", " a b ", value + "\n"])
    elif isinstance(value, int) and not isinstance(value, bool):
        numbers = (0, -1, float(value), 10**30, 1e300, 256)
        replacements.extend(number for number in numbers if number != value)
    return [{"set": item} for item in replacements] + changes


def apply(document: dict[str, Any], path: list[str | int], change: dict[str, Any]) -> object:
    """Return a copy of a document with one change applied at a path.

    Parameters
    ----------
    document
        Valid document.
    path
        Member names and array indexes of the changed node.
    change
        One change from :func:`_mutations`.

    Returns
    -------
    object
        Changed copy; a ``set`` at the empty path replaces the document.
    """
    if "set" in change and not path:
        return copy.deepcopy(change["set"])
    mutated = copy.deepcopy(document)
    node: Any = mutated
    for part in path[: -1 if "set" in change else None]:
        node = node[part]
    if "set" in change:
        node[path[-1]] = copy.deepcopy(change["set"])
    elif "remove" in change:
        del node[change["remove"]]
    else:
        node[change["add"]] = 1
    return mutated


def _cases(
    base: str, document: dict[str, Any], schema: dict[str, Any], depth: int
) -> list[dict[str, Any]]:
    """Change the nodes of one document and record Python's failing locations.

    Parameters
    ----------
    base
        Name of the valid document in the corpus.
    document
        Valid document.
    schema
        Its committed schema.
    depth
        Deepest path length whose node is changed.

    Returns
    -------
    list[dict[str, Any]]
        One group per changed node: the base, the node's path and its
        ``[change, locations]`` pairs; the first pair of the document's own
        group has the change ``None``, which keeps the valid document.
    """
    cases: list[dict[str, Any]] = []
    pending: list[tuple[list[str | int], Any]] = [([], document)]
    while pending:
        path, value = pending.pop(0)
        pairs: list[list[Any]] = [[None, []]] if not path else []
        for change in _mutations(value):
            mutated = apply(document, path, change)
            if isinstance(mutated, dict):
                pairs.append([change, schema_locations(mutated, schema)])
        cases.append({"base": base, "path": path, "changes": pairs})
        if len(path) < depth and isinstance(value, dict):
            pending.extend(([*path, key], item) for key, item in sorted(value.items()))
        elif len(path) < depth and isinstance(value, list):
            pending.extend(([*path, index], item) for index, item in enumerate(value))
    return cases


def corpus() -> dict[str, Any]:
    """Build the complete schema-location corpus from the packaged schemas and documents.

    Returns
    -------
    dict[str, Any]
        Valid base documents, and run and measurement-domain cases.
    """
    run_schema = load_json_object(DATA / "run-manifest.schema.json")
    domain_schema = load_json_object(DATA / "measurement-domain.schema.json")
    domain = load_json_object(DATA / "measurement-domain.json")
    # A JSON round trip gives every node its own object, as in a decoded document.
    variants = json.loads(json.dumps(_run_variants()))
    run_cases = [
        case
        for name, document in variants.items()
        for case in _cases(f"run {name}", document, run_schema, 99 if name == "control" else 1)
    ]
    return {
        "schema": "loop-timing-witness.control-schema-locations.v4",
        "bases": {
            **{f"run {name}": document for name, document in variants.items()},
            "domain": domain,
        },
        "run": run_cases,
        "domain": _cases("domain", domain, domain_schema, 99),
    }


def test_committed_corpus_equals_python_locations() -> None:
    """The committed corpus is exactly what Python reports for every mutation."""
    text = json.dumps(corpus(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    expected = text + "\n"
    assert CORPUS.read_text(encoding="utf-8") == expected


def test_corpus_exercises_failures_and_every_conditional_branch() -> None:
    """Hold valid declarations of every branch and many distinct refusals.

    The variants must be valid, and most mutations must fail somewhere, so the
    corpus cannot shrink into trivially passing cases.
    """
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    groups = {kind: data[kind] for kind in ("run", "domain")}
    valid = [group for group in groups["run"] if not group["path"]]
    assert [group["base"] for group in valid] == [f"run {name}" for name in _run_variants()]
    assert all(group["changes"][0] == [None, []] for group in valid)
    for kind, pairs in (
        (kind, [pair for group in groups[kind] for pair in group["changes"]]) for kind in groups
    ):
        changed = [pair for pair in pairs if pair[0] is not None]
        failing = [locations for _, locations in changed if locations]
        assert len(changed) > 1000, kind
        assert len(failing) > 0.8 * len(changed), kind
        assert len({tuple(locations) for locations in failing}) > 50, kind
    assert CORPUS.with_name(CORPUS.name + ".license").is_file()
