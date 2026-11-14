# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — AMP plugin receipt corpus shared with the native analysis

"""Hold Python's plugin build receipt decoding and plugin snapshot check in a shared corpus.

Every case starts from the reduced real receipt
(``tests/data/amp-plugin-build-reduced.json``):

- ``decode`` cases give ``decode_plugin_receipt`` the bytes of a changed
  receipt: malformed JSON, schema failures, and each cross-check with its
  preparation broken alone (identities, every group of names, the
  preparation and generation digests, a preparation path without a name),
  plus spellings Python admits (an identity equal as a float, doubled
  separators, the root folder and a double-slash root);
- ``snapshot`` cases run ``validate_plugin_snapshot`` on a capture folder
  laid out as ``snapshot_plugin`` writes it, for a receipt whose dependency
  digests are rewritten to small known contents, then changed.

The receipt's own names stay ``/build/...``: only the captured copies are
read, so no recorded digest depends on where a case is written. A decoding
case is raw text, or a patch of the base receipt (member paths set or
removed) that the native tests apply and write as canonical JSON; a snapshot
case is the complete capture's tree with entries removed and written. An
outcome is ``{"value": true}`` for an admitted receipt or a passing check,
Python's refusal text, or the ``OSError`` text, with the case directory
written ``<root>``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from test_amp_snapshot_corpus import _document, _edited, _link, _text, _tree, _unlink

from conftest import REPOSITORY_ROOT
from loop_timing_witness.amp_plugin_receipt import decode_plugin_receipt
from loop_timing_witness.amp_plugin_snapshot import source_index, validate_plugin_snapshot
from loop_timing_witness.manifest_io import canonical_json_bytes

if TYPE_CHECKING:
    from collections.abc import Callable

BASE: Final = REPOSITORY_ROOT / "tests/data/amp-plugin-build-reduced.json"
CORPUS: Final = REPOSITORY_ROOT / "analysis/rust/tests/data/amp-plugin-receipt-cases.json"
ZERO: Final = "0" * 64


def _base() -> dict[str, Any]:
    """Return a fresh copy of the reduced real receipt.

    Returns
    -------
    dict[str, Any]
        Decoded receipt.
    """
    data: dict[str, Any] = json.loads(BASE.read_text(encoding="utf-8"))
    return data


def _bound(data: dict[str, Any]) -> dict[str, Any]:
    """Rebind the preparation's digest after a change to the preparation.

    Parameters
    ----------
    data
        Receipt, changed in place.

    Returns
    -------
    dict[str, Any]
        The same receipt.
    """
    digest = hashlib.sha256(canonical_json_bytes(data["preparation"])).hexdigest()
    data["dependencies"][data["preparation_path"]] = digest
    return data


def _moved(data: dict[str, Any], path: str, generation: str | None = None) -> dict[str, Any]:
    """Move the preparation to another path and bind it, and its generation record if named.

    Parameters
    ----------
    data
        Receipt, changed in place.
    path
        New preparation path as the receipt writes it.
    generation
        Name under which the generation record is bound, or None to leave it.

    Returns
    -------
    dict[str, Any]
        The same receipt.
    """
    data["preparation_path"] = path
    if generation is not None:
        data["dependencies"][generation] = data["preparation"]["generation_sha256"]
    return _bound(data)


def _decode_cases() -> dict[str, bytes]:
    """Return the receipt bytes of each named decoding case.

    Returns
    -------
    dict[str, bytes]
        Bytes by case name.
    """
    data = _base()
    source = next(iter(data["preparation"]["identity"]["sources"]))
    compiler = next(iter(data["compilers"]["c"]["runtime_libraries"]))
    generation = str(Path(data["preparation_path"]).with_name("generation.json"))

    def changed(change: Callable[[dict[str, Any]], object]) -> bytes:
        receipt = _base()
        change(receipt)
        return canonical_json_bytes(receipt)

    def identity(value: object) -> Callable[[dict[str, Any]], object]:
        def change(receipt: dict[str, Any]) -> object:
            receipt["preparation"]["identity"]["thermal"] = value
            return _bound(receipt)

        return change

    return {
        "reduced receipt": canonical_json_bytes(data),
        "not JSON": b"{",
        "repeated member": b'{"a": 1, "a": 2}',
        "array": b"[]",
        "schema identifier changed": changed(lambda r: r.update(schema="x")),
        "member missing": changed(lambda r: r.pop("thermal")),
        "identity differs": changed(identity(1)),
        "identity equal as a float": changed(identity(0.0)),
        "source missing from dependencies": changed(lambda r: r["dependencies"].pop(source)),
        "source digest differs": changed(lambda r: r["dependencies"].update({source: ZERO})),
        "compiler library missing": changed(lambda r: r["dependencies"].pop(compiler)),
        "preparation digest differs": changed(
            lambda r: r["dependencies"].update({r["preparation_path"]: ZERO})
        ),
        "preparation path without a name": changed(lambda r: _moved(r, "/")),
        "generation digest differs": changed(
            lambda r: r["dependencies"].update({generation: ZERO})
        ),
        "doubled separators": changed(lambda r: _moved(r, "/build//plugin/compilation.json")),
        "root folder": changed(lambda r: _moved(r, "/compilation.json", "/generation.json")),
        "root folder without generation": changed(lambda r: _moved(r, "/compilation.json")),
        "double-slash root": changed(lambda r: _moved(r, "//x/c.json", "//x/generation.json")),
    }


def _snapshot_receipt() -> tuple[dict[str, Any], dict[str, bytes]]:
    """Return a receipt bound to small known contents, and those contents by name.

    Every recorded digest of a dependency is rewritten to the digest of its
    new content wherever the receipt repeats it; the generation record and
    the preparation are bound last, the preparation as its canonical bytes.

    Returns
    -------
    tuple[dict[str, Any], dict[str, bytes]]
        Receipt that ``decode_plugin_receipt`` admits, and its dependency contents.
    """
    data = _base()
    path = data["preparation_path"]
    generation = str(Path(path).with_name("generation.json"))
    contents = {name: f"{name}\n".encode() for name in data["dependencies"]}
    digests = {name: hashlib.sha256(content).hexdigest() for name, content in contents.items()}

    def rewrite(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in digests and isinstance(value, str) and len(value) == len(ZERO):
                    node[key] = digests[key]
                rewrite(value)

    rewrite(data)
    data["preparation"]["generation_sha256"] = digests[generation]
    contents[path] = canonical_json_bytes(data["preparation"])
    data["dependencies"][path] = hashlib.sha256(contents[path]).hexdigest()
    decode_plugin_receipt(canonical_json_bytes(data))
    return data, contents


def _capture(directory: Path) -> dict[str, Any]:
    """Write a capture's plugin receipt, source index and copies as ``snapshot_plugin`` does.

    Parameters
    ----------
    directory
        Case directory; the capture is its ``capture`` folder.

    Returns
    -------
    dict[str, Any]
        The check's other arguments: the library digest and the plant.
    """
    data, contents = _snapshot_receipt()
    capture = directory / "capture"
    for name, item in source_index(data).items():
        target = capture / item["path"]
        target.parent.mkdir(parents=True)
        target.write_bytes(contents[name])
    (capture / "plugin_build.json").write_bytes(canonical_json_bytes(data))
    (capture / "plugin_source_index.json").write_bytes(canonical_json_bytes(source_index(data)))
    return {"plugin": data["plugin_sha256"], "thermal": False}


def _snapshot_cases() -> dict[str, Any]:
    """Return named ``validate_plugin_snapshot`` cases.

    Returns
    -------
    dict[str, Any]
        Builders by case name; each returns the library digest and plant.
    """
    receipt = "capture/plugin_build.json"
    index = "capture/plugin_source_index.json"
    first, second = (f"capture/plugin_sources/{number:04d}/source" for number in range(2))
    return {
        "complete": _capture,
        "receipt missing": _edited(_capture, _unlink(receipt)),
        "receipt refused": _edited(_capture, _text(receipt, "{")),
        "index missing": _edited(_capture, _unlink(index)),
        "another plugin library": _edited(_capture, lambda _, a: {**a, "plugin": ZERO}),
        "another plant": _edited(_capture, lambda _, a: {**a, "thermal": True}),
        "index disagrees": _edited(
            _capture, _document(index, lambda i: {k: {**v, "sha256": ZERO} for k, v in i.items()})
        ),
        "copy changed": _edited(_capture, _text(second, "changed\n")),
        "copy missing": _edited(_capture, _unlink(first)),
        "copy folder linked outside": _edited(
            _capture, _link("capture/plugin_sources/0000", "../../outside/0000", "outside/0000")
        ),
        "reversed index, first missing, second changed": _edited(
            _capture,
            _document(index, lambda i: dict(reversed(i.items()))),
            _unlink(first),
            _text(second, "changed\n"),
        ),
    }


def _outcome(directory: Path, argument: object) -> dict[str, Any]:
    """Run one call and return its value, refusal or ``OSError`` text, written with ``<root>``.

    Parameters
    ----------
    directory
        Case directory.
    argument
        Receipt bytes to decode, or the library digest and plant of a snapshot check.

    Returns
    -------
    dict[str, Any]
        ``{"value": true}``, ``{"refusal": text}`` or ``{"os_error": text}``.
    """
    root = str(directory)
    try:
        if isinstance(argument, bytes):
            decoded = decode_plugin_receipt(argument)
            assert decoded == json.loads(argument)
        else:
            assert isinstance(argument, dict)
            plugin, thermal = argument["plugin"], argument["thermal"]
            validate_plugin_snapshot(directory / "capture", plugin, thermal=thermal)
    except ValueError as error:
        return {"refusal": str(error).replace(root, "<root>")}
    except OSError as error:
        return {"os_error": str(error).replace(root, "<root>")}
    return {"value": True}


def _patch(base: object, changed: object, path: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """Return the member paths at which a changed document differs from its base.

    A value of another type is a change even where Python's ``==`` holds, so
    ``0.0`` replacing ``0`` is kept.

    Parameters
    ----------
    base
        Base document or node.
    changed
        Changed document or node.
    path
        Member names leading to the nodes.

    Returns
    -------
    list[dict[str, Any]]
        ``{"path": [...], "set": value}`` or ``{"path": [...], "remove": true}`` in name order.
    """
    if isinstance(base, dict) and isinstance(changed, dict):
        operations: list[dict[str, Any]] = []
        for key in sorted(base.keys() | changed.keys()):
            if key not in changed:
                operations.append({"path": [*path, key], "remove": True})
            elif key not in base:
                operations.append({"path": [*path, key], "set": changed[key]})
            else:
                operations.extend(_patch(base[key], changed[key], (*path, key)))
        return operations
    if type(base) is type(changed) and base == changed:
        return []
    return [{"path": list(path), "set": changed}]


def _edits(template: dict[str, Any], tree: dict[str, Any]) -> dict[str, Any]:
    """Return how a case tree differs from the complete capture's tree.

    Parameters
    ----------
    template
        Tree of the complete capture.
    tree
        Tree of the case.

    Returns
    -------
    dict[str, Any]
        Entries to remove, then entries to write, each in path order.
    """
    removed = sorted(template.keys() - tree.keys())
    written = {name: entry for name, entry in sorted(tree.items()) if template.get(name) != entry}
    return {"remove": removed, "write": written}


def corpus(directory: Path) -> dict[str, Any]:
    """Build every case under an owned directory and return the corpus.

    Parameters
    ----------
    directory
        Owned empty directory for the snapshot trees.

    Returns
    -------
    dict[str, Any]
        Decoding cases with their bytes, snapshot cases with their trees, and outcomes.
    """
    directory = directory.resolve()
    base = _base()
    cases: list[dict[str, Any]] = []
    for name, content in _decode_cases().items():
        path = directory / f"decode-{len(cases)}"
        path.mkdir()
        item: dict[str, Any] = {"name": name, "function": "decode"}
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict) and canonical_json_bytes(parsed) == content:
            item["patch"] = _patch(base, parsed)
        else:
            item["text"] = content.decode()
        cases.append({**item, **_outcome(path, content)})
    template = directory / "template"
    template.mkdir()
    _capture(template)
    complete = _tree(template)
    for name, build in _snapshot_cases().items():
        path = directory / f"snapshot-{len(cases)}"
        path.mkdir()
        argument = build(path)
        item = {"name": name, "function": "snapshot", "argument": argument}
        item["edits"] = _edits(complete, _tree(path))
        cases.append({**item, **_outcome(path, argument)})
    return {
        "schema": "loop-timing-witness.amp-plugin-receipt-cases.v1",
        "description": (
            "Python's decode_plugin_receipt on receipt bytes (text, or the base receipt patched "
            "and written as canonical JSON), and validate_plugin_snapshot on <case>/capture "
            "after writing the complete capture tree with the case's edits (text, symlinks or "
            "empty folders) and the argument's library digest and plant. value true is an "
            "admitted receipt or a passing check; refusal and os_error carry Python's text, the "
            "case directory written <root>."
        ),
        "base": base,
        "capture": complete,
        "cases": cases,
    }


def _corpus_text(document: dict[str, Any]) -> str:
    """Return the committed text form of the corpus.

    Parameters
    ----------
    document
        Corpus.

    Returns
    -------
    str
        Compact sorted JSON and a final newline.
    """
    return json.dumps(document, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"


def test_committed_corpus_equals_python_outcomes(tmp_path: Path) -> None:
    """Rebuild the corpus from Python's decoder and check and require the committed file.

    Parameters
    ----------
    tmp_path
        Owned directory for the snapshot trees.
    """
    assert CORPUS.read_text(encoding="utf-8") == _corpus_text(corpus(tmp_path))
    assert CORPUS.with_name(CORPUS.name + ".license").is_file()
