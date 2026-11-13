# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — AMP snapshot corpus shared with the native analysis

"""Hold Python's runtime and firmware dependency snapshot checks in a shared corpus.

A captured AMP image keeps copies of its runtime libraries and of the
firmware's preprocessing sources, indexed by original name, and its
preparation receipt binds the preprocessing records. Each case here builds a
tree with Python's own snapshot writers (``snapshot_runtime``,
``snapshot_image_dependencies``) from small original files laid out as a real
image is, changes it, and records the tree and the outcome of one check:

- ``validate_runtime_snapshot`` (function ``runtime``);
- ``validate_image_dependency_snapshot`` (function ``image``);
- ``image_dependency_record_count`` (function ``record_count``), which reads
  only the preparation receipt and needs no tree.

The tree records text files and symbolic links with the case directory
written ``{root}``; the native tests write it under their own directory. An
outcome is the returned value, Python's refusal text or the ``OSError`` text,
with the case directory written ``<root>``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from loop_timing_witness import amp_image_dependencies, amp_runtime_snapshot
from loop_timing_witness.amp_image_dependencies import (
    image_dependency_hashes,
    image_dependency_record_count,
    snapshot_image_dependencies,
    validate_image_dependency_snapshot,
)
from loop_timing_witness.amp_runtime_snapshot import snapshot_runtime, validate_runtime_snapshot
from loop_timing_witness.manifest_io import sha256_of_file

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
CORPUS: Final = REPOSITORY_ROOT / "analysis/rust/tests/data/amp-snapshot-cases.json"
CRATE_SCHEMAS: Final = {
    "amp-runtime-hashes.schema.json": amp_runtime_snapshot.HASH_SCHEMA,
    "amp-firmware-dependency-hashes.schema.json": amp_image_dependencies.HASH_SCHEMA,
}
LIBRARIES: Final = ("libc.so.6", "libm.so.6")
SOURCES: Final = {
    "source/runtime/bare_metal/entry.S": "entry\n",
    "source/runtime/bare_metal/amp_controller.c": "controller\n",
    "source/runtime/bare_metal/amp_contract.h": "contract header\n",
    "source/runtime/isa/amp_exit.c": "exit\n",
    "source/controllers/c/witness_controller.c": "witness\n",
    "contract.c": "contract\n",
}
RECORDS: Final = (
    "source/runtime/bare_metal/entry.S",
    "source/runtime/bare_metal/amp_controller.c source/runtime/bare_metal/amp_contract.h {system}",
    "source/runtime/isa/amp_exit.c",
    "source/controllers/c/witness_controller.c {system}",
    "contract.c source/runtime/bare_metal/amp_contract.h",
)
# An absolute system dependency whose name and bytes are the same on every host, so a record's
# bytes and the index's numbering do not depend on where a case is written.
SYSTEM: Final = "/dev/null"
RUST_RECORDS: Final = (0, 1, 2, 4)
Builder = Callable[[Path], object]
Edit = Callable[[Path, Any], object]
Check = Callable[[Path, Any], object]


def _write(path: Path, text: str) -> None:
    """Write one text file, creating its directories.

    Parameters
    ----------
    path
        File to write.
    text
        Content.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _runtime(directory: Path) -> dict[str, str]:
    """Snapshot two original libraries into ``capture`` as a capture does.

    Parameters
    ----------
    directory
        Case directory.

    Returns
    -------
    dict[str, str]
        Original library identities.
    """
    identities = {}
    for name in LIBRARIES:
        path = directory / "original" / name
        _write(path, f"{name} bytes\n")
        identities[str(path)] = sha256_of_file(path)
    (directory / "capture").mkdir()
    snapshot_runtime(directory / "capture", identities)
    return identities


def _image(directory: Path, numbers: tuple[int, ...], system: str = SYSTEM) -> dict[str, str]:
    """Write an image's sources and preprocessing records and snapshot their closure.

    Parameters
    ----------
    directory
        Case directory; the image is its ``image`` folder.
    numbers
        Which of ``RECORDS`` the image's ``input_N.d`` records hold, in order.
    system
        Absolute or escaping name of a system dependency in two records.

    Returns
    -------
    dict[str, str]
        Compiler dependency identities, as the preparation records them.
    """
    image = directory / "image"
    for name, text in SOURCES.items():
        _write(image / name, text)
    records = []
    for index, number in enumerate(numbers):
        record = image / "precompile" / f"input_{index}.d"
        _write(record, f"objects/input_{index}.o: {RECORDS[number].format(system=system)}\n")
        records.append(record)
    identities = image_dependency_hashes(tuple(records), image)
    snapshot_image_dependencies(image, identities)
    return identities


def _edited(build: Builder, *edits: Edit) -> Builder:
    """Return a builder that changes another builder's tree or argument.

    Parameters
    ----------
    build
        Builder of the unchanged case.
    edits
        Changes in order; one that returns a value replaces the argument.

    Returns
    -------
    Builder
        The changed case's builder.
    """

    def case(directory: Path) -> object:
        argument = build(directory)
        for edit in edits:
            result = edit(directory, argument)
            argument = argument if result is None else result
        return argument

    return case


def _text(name: str, content: str) -> Edit:
    """Return a change that writes one text file of the case."""
    return lambda directory, _: _write(directory / name, content)


def _unlink(name: str) -> Edit:
    """Return a change that removes one file of the case."""
    return lambda directory, _: (directory / name).unlink()


def _link(name: str, target: str, moved: str | None = None) -> Edit:
    """Return a change that replaces one path by a symbolic link, moving it first if asked."""

    def edit(directory: Path, _: object) -> None:
        path = directory / name
        if moved is not None:
            (directory / moved).parent.mkdir(parents=True, exist_ok=True)
            path.rename(directory / moved)
        elif path.is_file():
            path.unlink()
        path.symlink_to(target)

    return edit


def _document(name: str, change: Callable[[dict[str, Any]], dict[str, Any]]) -> Edit:
    """Return a change that rewrites one JSON document of the case."""

    def edit(directory: Path, _: object) -> None:
        path = directory / name
        document = change(json.loads(path.read_text(encoding="utf-8")))
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    return edit


def _runtime_cases() -> dict[str, Builder]:
    """Return named cases of ``validate_runtime_snapshot``.

    Returns
    -------
    dict[str, Builder]
        Builders by case name; each returns the identities argument.
    """
    index = "capture/runtime_source_index.json"
    first, second = (f"capture/runtime_sources/{n:04d}/library" for n in range(2))
    changed = _text(first, "changed\n")
    return {
        "complete": _runtime,
        "identities not an object": _edited(_runtime, lambda _, __: []),
        "no identities": _edited(_runtime, lambda _, __: {}),
        "relative library name": _edited(
            _runtime, lambda d, ids: {k.removeprefix(f"{d}/"): v for k, v in ids.items()}
        ),
        "short digest": _edited(_runtime, lambda _, ids: {k: v[:63] for k, v in ids.items()}),
        "digest not text": _edited(_runtime, lambda _, ids: dict.fromkeys(ids, 1)),
        "index missing": _edited(_runtime, _unlink(index)),
        "index not JSON": _edited(_runtime, _text(index, "{")),
        "index repeats a member": _edited(_runtime, _text(index, '{"a": 1, "a": 2}')),
        "index is an array": _edited(_runtime, _text(index, "[]")),
        "index disagrees": _edited(
            _runtime,
            _document(index, lambda i: {k: {**v, "sha256": "0" * 64} for k, v in i.items()}),
        ),
        "library changed": _edited(_runtime, changed),
        "library missing": _edited(_runtime, _unlink(first)),
        "library is a folder": _edited(_runtime, _unlink(first), _text(f"{first}/x", "x\n")),
        "library linked inside": _edited(
            _runtime,
            _text("capture/copies/libc", "libc.so.6 bytes\n"),
            _link(first, "../../copies/libc"),
        ),
        "library folder linked outside": _edited(
            _runtime, _link("capture/runtime_sources/0000", "../../outside/0000", "outside/0000")
        ),
        "capture reached through a link": _edited(_runtime, _link("capture", "real", "real")),
        "first changed, second missing": _edited(_runtime, changed, _unlink(second)),
        "reversed index, first changed, second missing": _edited(
            _runtime,
            _document(index, lambda i: dict(reversed(i.items()))),
            changed,
            _unlink(second),
        ),
    }


def _image_cases() -> dict[str, Builder]:
    """Return named cases of ``validate_image_dependency_snapshot``.

    Returns
    -------
    dict[str, Builder]
        Builders by case name; each returns the identities argument.
    """

    def build(directory: Path) -> dict[str, str]:
        return _image(directory, (0, 1, 2, 3, 4))

    index = "image/compiler_source_index.json"
    first, second = (f"image/compiler_sources/{n:04d}/source" for n in range(2))
    digest = "0" * 64
    return {
        "complete": build,
        "identities not an object": _edited(build, lambda _, __: []),
        "no identities": _edited(build, lambda _, __: {}),
        "name outside the image tree": _edited(build, lambda _, ids: {**ids, "lib/x.h": digest}),
        "contract name with a suffix": _edited(
            build, lambda _, ids: {**ids, "contract.c.o": digest}
        ),
        "escaping source name": _edited(build, lambda _, ids: {**ids, "source/../x.c": digest}),
        "escaping absolute name": _edited(build, lambda _, ids: {**ids, "/usr/../x.h": digest}),
        "index missing": _edited(build, _unlink(index)),
        "index disagrees": _edited(
            build, _document(index, lambda i: {k: {**v, "sha256": digest} for k, v in i.items()})
        ),
        "snapshot source changed": _edited(build, _text(second, "changed\n")),
        "snapshot source missing": _edited(build, _unlink(first)),
        "snapshot folder linked outside": _edited(
            build, _link("image/compiler_sources/0001", "../../outside/0001", "outside/0001")
        ),
        "reversed index, first missing, second changed": _edited(
            build,
            _document(index, lambda i: dict(reversed(i.items()))),
            _unlink(first),
            _text(second, "changed\n"),
        ),
    }


def _record_count_cases() -> dict[str, Builder]:
    """Return named cases of ``image_dependency_record_count``; they need no tree.

    Returns
    -------
    dict[str, Builder]
        Builders by case name; each returns the preparation receipt argument.
    """
    rust = {"kernel_backend": "rust", "inputs": {"rust_preparation.json": "0" * 64}}
    receipts: dict[str, Any] = {
        "C kernel": {"toolchain": {}},
        "Rust kernel": rust,
        "unknown kernel": {**rust, "kernel_backend": "c"},
        "kernel named by a number": {**rust, "kernel_backend": 1},
        "kernel named null": {**rust, "kernel_backend": None},
        "Rust kernel without inputs": {"kernel_backend": "rust"},
        "Rust kernel inputs not an object": {**rust, "inputs": ["rust_preparation.json"]},
        "Rust kernel without its preparation": {**rust, "inputs": {"rust.json": "0" * 64}},
        "Rust kernel with its preparation among others": {
            **rust,
            "inputs": {"a.json": "0" * 64, "rust_preparation.json": None},
        },
    }

    def returning(receipt: object) -> Builder:
        return lambda _: receipt

    return {name: returning(receipt) for name, receipt in receipts.items()}


FUNCTIONS: Final[dict[str, tuple[Check, Callable[[], dict[str, Builder]]]]] = {
    "runtime": (lambda d, a: validate_runtime_snapshot(d / "capture", a), _runtime_cases),
    "image": (lambda d, a: validate_image_dependency_snapshot(d / "image", a), _image_cases),
    "record_count": (lambda _, a: image_dependency_record_count(a), _record_count_cases),
}


def _rooted(value: object, root: str, mark: str) -> object:
    """Return a JSON value with ``root`` written ``mark`` in every string and member name.

    Parameters
    ----------
    value
        JSON value.
    root
        Case directory text.
    mark
        Its written form.

    Returns
    -------
    object
        The value with the directory replaced.
    """
    if isinstance(value, str):
        return value.replace(root, mark)
    if isinstance(value, dict):
        return {key.replace(root, mark): _rooted(item, root, mark) for key, item in value.items()}
    if isinstance(value, list):
        return [_rooted(item, root, mark) for item in value]
    return value


def _tree(directory: Path) -> dict[str, Any]:
    """Record a case tree: text, bytes that are not UTF-8 as hexadecimal, links and empty folders.

    Parameters
    ----------
    directory
        Case directory.

    Returns
    -------
    dict[str, Any]
        Entries by path relative to the directory, with the directory written ``{root}``.
    """
    root = str(directory)
    tree: dict[str, Any] = {}
    for path in sorted(directory.rglob("*")):
        name = path.relative_to(directory).as_posix()
        if path.is_symlink():
            tree[name] = {"symlink": str(path.readlink()).replace(root, "{root}")}
        elif path.is_file():
            content = path.read_bytes()
            try:
                tree[name] = content.decode("utf-8").replace(root, "{root}")
            except UnicodeDecodeError:
                tree[name] = {"hex": content.hex()}
        elif not any(path.iterdir()):
            tree[name] = {"folder": True}
    return tree


def _outcome(directory: Path, function: str, argument: object) -> dict[str, Any]:
    """Run one check and return its value, refusal or ``OSError`` text, written with ``<root>``.

    Parameters
    ----------
    directory
        Case directory.
    function
        Key of ``FUNCTIONS``.
    argument
        The check's second argument.

    Returns
    -------
    dict[str, Any]
        ``{"value": ...}``, ``{"refusal": text}`` or ``{"os_error": text}``.
    """
    check, _ = FUNCTIONS[function]
    root = str(directory)
    try:
        value = check(directory, argument)
    except ValueError as error:
        return {"refusal": str(error).replace(root, "<root>")}
    except OSError as error:
        return {"os_error": str(error).replace(root, "<root>")}
    return {"value": _rooted(value, root, "<root>")}


def corpus(directory: Path) -> dict[str, Any]:
    """Build every case under an owned directory and return the corpus.

    Parameters
    ----------
    directory
        Owned empty directory for the case trees.

    Returns
    -------
    dict[str, Any]
        Cases with their trees, arguments and outcomes.
    """
    directory = directory.resolve()
    cases: list[dict[str, Any]] = []
    for function, (_, named) in FUNCTIONS.items():
        for name, build in named().items():
            path = directory / f"{function}-{len(cases)}"
            path.mkdir()
            argument = build(path)
            root = str(path)
            cases.append(
                {
                    "name": name,
                    "function": function,
                    "argument": _rooted(argument, root, "{root}"),
                    "tree": _tree(path),
                    **_outcome(path, function, argument),
                }
            )
    return {
        "schema": "loop-timing-witness.amp-snapshot-cases.v1",
        "description": (
            "Python's AMP runtime and firmware dependency snapshot checks on named trees. Each "
            "case writes its tree (text, hexadecimal bytes, symlinks or empty folders, {root} "
            "replaced by the case directory), calls function runtime "
            "(validate_runtime_snapshot on <case>/capture), image "
            "(validate_image_dependency_snapshot on <case>/image) or record_count "
            "(image_dependency_record_count) with argument ({root} replaced), and gives value, "
            "refusal or os_error, the case directory written <root>."
        ),
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
    """Rebuild the corpus from Python's writers and checks and require the committed file.

    Parameters
    ----------
    tmp_path
        Owned directory for the case trees.
    """
    assert CORPUS.read_text(encoding="utf-8") == _corpus_text(corpus(tmp_path))
    assert CORPUS.with_name(CORPUS.name + ".license").is_file()


def test_crate_schemas_equal_python_constants() -> None:
    """Require the native analysis's committed hash schemas to equal Python's constants."""
    for name, constant in CRATE_SCHEMAS.items():
        path = REPOSITORY_ROOT / "analysis/rust" / name
        assert json.loads(path.read_text(encoding="utf-8")) == constant, name
