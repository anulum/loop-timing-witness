# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — neural manifest refusals shared with the native analysis

"""Build the neural manifest refusal corpus from Python and hold it committed.

The base is the recorded neural declaration reduced to its first source
reference. Each group changes one node of it and records two Python outcomes
for every change: the failing locations of the committed carrier schema, and
what ``load_neural_manifest`` returns, the refusal text or ``None`` for an
admitted declaration. Crafted documents add the byte-level cases a node change
cannot express: encodings, nesting, repeated members, integer bounds, the byte
allocation and the order of the reference checks.

The native crate reads the same file. Its schema unit test requires the same
locations, and its public API test writes each document to a file and requires
the same refusal from ``load_neural_manifest``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Final

from test_control_schema_corpus import apply

from conftest import REPOSITORY_ROOT
from loop_timing_witness.manifest_io import load_json_object
from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError
from loop_timing_witness.neural_run_manifest import NEURAL_MANIFEST_LIMIT, load_neural_manifest
from loop_timing_witness.validate_measurement_domain import schema_locations

if TYPE_CHECKING:
    from pathlib import Path

CORPUS: Final = REPOSITORY_ROOT / "analysis/rust/tests/data/neural-manifest-refusals.json"
RECORDED: Final = REPOSITORY_ROOT / "tests/data/neural-selected-original.run.json"
SCHEMA: Final = REPOSITORY_ROOT / "src/loop_timing_witness/data/neural-step-run.schema.json"
REPLACEMENTS: Final[tuple[object, ...]] = (None, True, 1.5, "x", [], {})
# Integers the native test can hold exactly: both ends of the 64-bit ranges.
INTEGERS: Final[tuple[int | float, ...]] = (0, -1, 256, 1e300, 2**64 - 1, -(2**63))
PATHS: Final[tuple[str, ...]] = (
    "a",
    "a/b",
    "...",
    ".hidden",
    "a-b_c.d",
    "/a",
    "a/",
    "a//b",
    "./a",
    "a/./b",
    "a/../b",
    "..",
    ".",
    "a b",
    "a\\b",
    "\u00e9",
)
# The length bound is one rule for every reference, so one node holds it.
LONG_PATHS: Final[dict[tuple[str | int, ...], tuple[str, ...]]] = {
    ("source_files", 0, "path"): ("a" * 4096, "a" * 4097)
}
NOT_JSON: Final = "Neural manifest must contain a strict UTF-8 JSON object."
NOT_CLOSED: Final = "Neural manifest violates its closed schema or exact integer contract."
NOT_EXACT: Final = "Neural run identity and source pins require exact grammar."
NOT_DIGEST: Final = "Neural file reference requires an exact lowercase SHA-256."
NOT_PORTABLE: Final = "Neural file reference requires a bounded portable within-run path."
REPEATED: Final = "Neural source references contain a duplicate path."
OVERSIZED: Final = "Neural manifest exceeds its byte allocation."


def _base() -> dict[str, Any]:
    """Return the recorded declaration reduced to its first source reference.

    Returns
    -------
    dict[str, Any]
        Admitted declaration.
    """
    document: dict[str, Any] = json.loads(RECORDED.read_text(encoding="utf-8"))
    document["source_files"] = document["source_files"][:1]
    return document


def _changes(path: list[str | int], value: object) -> list[dict[str, object]]:
    """Return the single-node changes of one value of the declaration.

    Parameters
    ----------
    path
        Member names and array indexes of the node.
    value
        Admitted node.

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
        replacements.extend(["", " a b ", value + "\n", value.upper()])
        if path and path[-1] == "path":
            replacements.extend((*PATHS, *LONG_PATHS.get(tuple(path), ())))
        if path == ["run_id"]:
            replacements.extend(["a" * 128, "a" * 129, "-a", "_a", "a.b-c_d"])
    elif isinstance(value, int) and not isinstance(value, bool):
        replacements.extend(item for item in (*INTEGERS, float(value)) if item != value)
        if path and path[-1] == "byte_length":
            replacements.extend([65536, 65537, 1048576, 1048577])
    unique: list[object] = []
    for item in replacements:
        if not any(type(item) is type(other) and item == other for other in unique):
            unique.append(item)
    return [{"set": item} for item in unique] + changes


def _load(raw: bytes, directory: Path) -> tuple[str | None, dict[str, Any] | None]:
    """Load one declaration file as Python's public reader does.

    Parameters
    ----------
    raw
        Complete manifest bytes.
    directory
        Directory that holds the written manifest.

    Returns
    -------
    tuple[str | None, dict[str, Any] | None]
        The refusal text and no declaration, or no refusal and the admitted declaration.
    """
    path = directory / "manifest.json"
    path.write_bytes(raw)
    try:
        return None, load_neural_manifest(path)
    except NeuralCaptureRefusalError as refusal:
        return str(refusal), None


def _text(document: object) -> str:
    """Return the compact JSON text the native test also writes for a document.

    Parameters
    ----------
    document
        Decoded declaration.

    Returns
    -------
    str
        Compact JSON text.
    """
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"))


def _groups(base: dict[str, Any], schema: dict[str, Any], directory: Path) -> list[dict[str, Any]]:
    """Change every node of the base and record Python's locations and refusals.

    Parameters
    ----------
    base
        Admitted declaration.
    schema
        Committed carrier schema.
    directory
        Directory for the written manifests.

    Returns
    -------
    list[dict[str, Any]]
        One group per node: its path and ``[change, locations, refusal]``
        triples; the first triple of the root group keeps the base.
    """
    groups: list[dict[str, Any]] = []
    pending: list[tuple[list[str | int], Any]] = [([], base)]
    while pending:
        path, value = pending.pop(0)
        triples: list[list[Any]] = []
        if not path:
            triples.append([None, [], _load(_text(base).encode(), directory)[0]])
        for change in _changes(path, value):
            mutated = apply(base, path, change)
            if isinstance(mutated, dict):
                refusal, admitted = _load(_text(mutated).encode(), directory)
                assert admitted in (None, mutated)
                triples.append([change, schema_locations(mutated, schema), refusal])
        groups.append({"path": path, "changes": triples})
        if isinstance(value, dict):
            pending.extend(([*path, key], item) for key, item in sorted(value.items()))
        elif isinstance(value, list):
            pending.extend(([*path, index], item) for index, item in enumerate(value))
    return groups


def _member(base: dict[str, Any], name: str, value: object) -> list[str]:
    """Return the text edit that replaces one root member of the base.

    Parameters
    ----------
    base
        Admitted declaration.
    name
        Root member.
    value
        Its replacement.

    Returns
    -------
    list[str]
        The member's compact text and its replacement text.
    """
    return [f'"{name}":{_text(base[name])}', f'"{name}":{_text(value)}']


def _document(
    name: str,
    *edits: list[str],
    text: str | None = None,
    around: tuple[str, str] = ("", ""),
    encoding: str = "utf-8",
    pad: int = 0,
) -> dict[str, Any]:
    """Describe one crafted document.

    Parameters
    ----------
    name
        Description of the case.
    *edits
        ``[old, new]`` text replacements applied in order; each ``old`` occurs once.
    text
        Whole text, or ``None`` for the compact base text.
    around
        Texts written before and after the edited text.
    encoding
        ``utf-8``, or ``latin-1`` for bytes that are not UTF-8.
    pad
        Spaces appended after the encoded text.

    Returns
    -------
    dict[str, Any]
        The description the native test also renders.
    """
    return {
        "name": name,
        "text": text,
        "edits": list(edits),
        "before": around[0],
        "after": around[1],
        "encoding": encoding,
        "pad": pad,
    }


def _render(base_text: str, document: dict[str, Any]) -> bytes:
    """Return the bytes of one crafted document.

    Parameters
    ----------
    base_text
        Compact text of the base.
    document
        Description from :func:`_document`.

    Returns
    -------
    bytes
        Complete manifest bytes.
    """
    text: str = base_text if document["text"] is None else document["text"]
    for old, new in document["edits"]:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    encoded = (document["before"] + text + document["after"]).encode(document["encoding"])
    padding: int = document["pad"]
    return bytes(encoded + b" " * padding)


def _documents(base: dict[str, Any]) -> list[dict[str, Any]]:
    """Describe the crafted documents; every admitted one decodes to the base.

    Parameters
    ----------
    base
        Admitted declaration.

    Returns
    -------
    list[dict[str, Any]]
        Descriptions from :func:`_document`.
    """
    run_id: str = base["run_id"]
    run = f'"run_id":"{run_id}"'
    epoch = f'"epoch":{base["epoch"]}'
    source = base["source_files"][0]
    # A marked source length is the one unique place to splice integer texts into.
    marked = _member(base, "source_files", [{**source, "byte_length": 987654321}])

    def length(literal: str) -> tuple[list[str], list[str]]:
        return marked, ['"byte_length":987654321', f'"byte_length":{literal}']

    # The schema anchors digests with $, so only a trailing newline reaches the exact check.
    bad = {**source, "sha256": source["sha256"] + "\n"}
    escaped = {**source, "path": "../escape"}
    nested = "[" * 63 + "]" * 63
    first = f"\\u{ord(run_id[0]):04x}"
    allocation = NEURAL_MANIFEST_LIMIT - len(_text(base))
    return [
        _document("admitted"),
        _document("surrounding whitespace", around=(" \n\t", "\r\n")),
        _document("escaped letter", [run, f'"run_id":"{first}{run_id[1:]}"']),
        _document("negative zero", [epoch, '"epoch":-0']),
        _document("at the byte allocation", pad=allocation),
        _document("beyond the byte allocation", pad=allocation + 1),
        _document("empty", text=""),
        _document("whitespace only", text=" \n"),
        _document("array", around=("[", "]")),
        _document("string", text='"text"'),
        _document("truncated", text='{"schema_id":"loop-timing-witness.neural-step-run.v1"'),
        _document("trailing data", around=("", "{}")),
        _document("comment", around=("/**/", "")),
        _document("byte order mark", around=(chr(0xFEFF), "")),
        _document("not UTF-8", [run, f'"run_id":"a{chr(0xFF)}"'], encoding="latin-1"),
        _document("unpaired high surrogate", [run, '"run_id":"a\\ud800"']),
        _document("unpaired low surrogate", [run, '"run_id":"a\\udc00"']),
        _document("paired surrogates", [run, '"run_id":"a\\ud83d\\ude00"']),
        _document("control character", [run, '"run_id":"a\tb"']),
        _document("single quotes", [run, "'run_id':'x'"]),
        _document("repeated root member", [epoch, f"{epoch},{epoch}"]),
        _document(
            "repeated nested member", ['"pending_empty":', '"finalized":true,"pending_empty":']
        ),
        _document("nesting 64", [epoch, f'{epoch},"deep":{nested}']),
        _document("nesting 65", [epoch, f'{epoch},"deep":[{nested}]']),
        _document("integral decimal", [epoch, '"epoch":0.0']),
        _document("integral exponent", [epoch, '"epoch":0e0']),
        _document("upper exponent", [epoch, '"epoch":1E0']),
        _document("not a number", [epoch, '"epoch":NaN']),
        _document("infinity", [epoch, '"epoch":Infinity']),
        _document("negative infinity", [epoch, '"epoch":-Infinity']),
        _document("overflowing decimal", [epoch, '"epoch":1e400']),
        _document("leading zero", [epoch, '"epoch":00']),
        _document("leading plus", [epoch, '"epoch":+0']),
        _document("unsigned 64-bit maximum", *length("18446744073709551615")),
        _document("above unsigned 64 bits", *length("18446744073709551616")),
        _document("signed 64-bit minimum", *length("-9223372036854775808")),
        _document("below signed 64 bits", *length("-9223372036854775809")),
        _document("long integer", *length("9" * 5000)),
        _document("exponent length", *length("1e0")),
        _document("repeated source", _member(base, "source_files", [source, source])),
        _document(
            "every source before the repeated path",
            _member(base, "source_files", [source, source, bad]),
        ),
        _document("bad path before a later digest", _member(base, "source_files", [escaped, bad])),
        _document(
            "digest before path in one reference",
            _member(base, "source_files", [{**escaped, "sha256": bad["sha256"]}]),
        ),
        _document(
            "first root reference first",
            _member(base, "tool_receipt", {**base["tool_receipt"], "path": "a//b"}),
            _member(
                base,
                "source_contract_ref",
                {**base["source_contract_ref"], "sha256": bad["sha256"]},
            ),
        ),
        _document(
            "root references before channels",
            _member(base, "source_contract_ref", {**base["source_contract_ref"], "path": "/a"}),
            _member(
                base,
                "channels",
                [{**base["channels"][0], "capture": bad}, *base["channels"][1:]],
            ),
        ),
        _document(
            "sources before root references",
            _member(base, "source_files", [escaped]),
            _member(base, "tool_receipt", {**base["tool_receipt"], "sha256": bad["sha256"]}),
        ),
        _document(
            "identity before references",
            [run, f'"run_id":"{run_id}\\n"'],
            _member(base, "source_files", [bad]),
        ),
    ]


def corpus(directory: Path) -> dict[str, Any]:
    """Build the complete refusal corpus.

    Parameters
    ----------
    directory
        Empty directory for the written manifests.

    Returns
    -------
    dict[str, Any]
        The base and its compact text, the refusal texts, the node groups and
        the crafted documents; an outcome is an index into the refusal texts,
        or ``None`` for an admitted declaration.
    """
    base = _base()
    base_text = _text(base)
    assert base_text.isascii()
    schema = load_json_object(SCHEMA)
    groups = _groups(base, schema, directory)
    documents = _documents(base)
    for document in documents:
        refusal, value = _load(_render(base_text, document), directory)
        assert value in (None, base), document["name"]
        document["refusal"] = refusal
    outcomes = {triple[2] for group in groups for triple in group["changes"]}
    outcomes |= {document["refusal"] for document in documents}
    refusals = sorted(outcomes - {None})
    for group in groups:
        for triple in group["changes"]:
            triple[2] = None if triple[2] is None else refusals.index(triple[2])
    for document in documents:
        refusal = document["refusal"]
        document["refusal"] = None if refusal is None else refusals.index(refusal)
    return {
        "schema": "loop-timing-witness.neural-manifest-refusals.v1",
        "base": base,
        "base_text": base_text,
        "refusals": refusals,
        "groups": groups,
        "documents": documents,
    }


def test_committed_corpus_equals_python_outcomes(tmp_path: Path) -> None:
    """The committed corpus is exactly what Python reports for every change and document."""
    text = json.dumps(corpus(tmp_path), ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    assert CORPUS.read_text(encoding="utf-8") == text + "\n"
    assert CORPUS.with_name(CORPUS.name + ".license").is_file()


def test_corpus_reaches_every_declaration_refusal() -> None:
    """Every refusal after the file checks occurs, and admitted declarations remain.

    The corpus cannot shrink into one refusal: node changes reach every text
    after decoding, crafted documents reach every text, and the crafted
    ordering cases are refused for their first defect.
    """
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    texts = [None, *data["refusals"]]
    changed = [
        texts[0 if triple[2] is None else triple[2] + 1]
        for group in data["groups"]
        for triple in group["changes"]
    ]
    crafted = {
        document["name"]: texts[0 if document["refusal"] is None else document["refusal"] + 1]
        for document in data["documents"]
    }
    every = {NOT_JSON, NOT_CLOSED, NOT_EXACT, NOT_DIGEST, NOT_PORTABLE, REPEATED, None}
    assert every - {NOT_JSON} <= set(changed)
    assert every | {OVERSIZED} == set(crafted.values())
    assert {
        name: crafted[name]
        for name in (
            "every source before the repeated path",
            "bad path before a later digest",
            "digest before path in one reference",
            "first root reference first",
            "root references before channels",
            "sources before root references",
            "identity before references",
        )
    } == {
        "every source before the repeated path": NOT_DIGEST,
        "bad path before a later digest": NOT_PORTABLE,
        "digest before path in one reference": NOT_DIGEST,
        "first root reference first": NOT_PORTABLE,
        "root references before channels": NOT_PORTABLE,
        "sources before root references": NOT_PORTABLE,
        "identity before references": NOT_EXACT,
    }
    assert len(changed) > 1000
    locations = [triple[1] for group in data["groups"] for triple in group["changes"]]
    assert len({tuple(item) for item in locations if item}) > 100
    assert data["groups"][0]["changes"][0] == [None, [], None]
