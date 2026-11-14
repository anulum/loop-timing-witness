# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — Rust kernel image receipt corpus shared with the native analysis

"""Hold Python's Rust kernel image check in a shared corpus.

Each case writes an image folder laid out as a real image built with the Rust
kernel, and runs ``validate_rust_image_receipt`` on it with the image's and
the preparation's receipts. The layout, the compiler and cargo identities,
the target and runtime library names and the four dependency records rustc
wrote are those of a real image built on the review host, with the toolchain
folder written ``/build/rust`` and two of its ten runtime libraries kept; the
large files (target libraries, archives, runtime copies, crate sources) are
replaced by small known contents whose digests are bound wherever the image
records them. Cases change the declarations, the captured preparation, every
snapshot, the records and the compiled outputs, each failing alone.

The committed form keeps the complete image's tree once; a case is the
patch of its receipts (member paths set or removed) and the entries its tree
removes and writes. An outcome is ``{"value": true}``, Python's refusal text
or the ``OSError`` text, with the case directory written ``<root>``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from test_amp_plugin_receipt_corpus import _edits, _patch
from test_amp_snapshot_corpus import _document, _edited, _link, _text, _tree, _unlink

from conftest import REPOSITORY_ROOT
from loop_timing_witness.amp_runtime_snapshot import runtime_index
from loop_timing_witness.amp_rust_receipt import TOOLCHAIN, validate_rust_image_receipt
from loop_timing_witness.amp_rust_vectors import ADAPTER, CORE, LIBRARY, TARGET, rust_vectors
from loop_timing_witness.manifest_io import canonical_json_bytes

if TYPE_CHECKING:
    from collections.abc import Callable

CORPUS: Final = REPOSITORY_ROOT / "analysis/rust/tests/data/amp-rust-receipt-cases.json"
CRATE_SCHEMA: Final = REPOSITORY_ROOT / "analysis/rust/amp-rust-toolchain.schema.json"
TOOLS: Final = "/build/rust"
COMPILER: Final = f"{TOOLS}/bin/rustc"
VERSIONS: Final = {
    "rustc": "rustc 1.99.1 (58cf8f9c3 2026-10-13)\n",
    "cargo": "cargo 1.99.1 (5f94df478 2026-08-27)\n",
    "verbose": (
        "rustc 1.99.1 (58cf8f9c3 2026-10-13)\nbinary: rustc\n"
        "commit-hash: 58cf8f9c35b355199727627d07ae34a4e2846d67\ncommit-date: 2026-10-13\n"
        "host: x86_64-unknown-linux-gnu\nrelease: 1.99.1\nLLVM version: 23.1.1\n"
    ),
}
LIBRARIES: Final = f"{TOOLS}/lib/rustlib/{TARGET}/lib"
TARGETS: Final = tuple(
    f"{LIBRARIES}/{name}.{kind}"
    for name in (
        "liballoc-070d0c0271ae76a6",
        "libcompiler_builtins-44e42ea2df1a0b83",
        "libcore-7636b19ffd67e4c9",
    )
    for kind in ("rlib", "rmeta")
)
RUNTIME: Final = (f"{TOOLS}/lib/librustc_driver-7ed0375ae352bd75.so", "/usr/lib/libc.so.6")
CORE_SOURCE: Final = f"source/{CORE}/src/lib.rs"
ADAPTER_SOURCE: Final = f"source/{ADAPTER}/src/lib.rs"


def _record(folder: str, name: str, output: str, source: str) -> str:
    """Return one dependency record as rustc wrote it on the review host.

    Parameters
    ----------
    folder
        Output folder of the vectors.
    name
        Record name.
    output
        Library the record belongs to.
    source
        The crate's one source.

    Returns
    -------
    str
        Record text.
    """
    return f"{folder}/{name}: {source}\n\n{folder}/{output}: {source}\n\n{source}:\n"


def _digest(content: bytes) -> str:
    """Return the SHA-256 of bytes.

    Parameters
    ----------
    content
        Bytes.

    Returns
    -------
    str
        Lowercase hexadecimal digest.
    """
    return hashlib.sha256(content).hexdigest()


def _write(path: Path, content: bytes) -> str:
    """Write one file, creating its folders, and return its digest.

    Parameters
    ----------
    path
        File.
    content
        Bytes.

    Returns
    -------
    str
        Digest of the bytes.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return _digest(content)


def _snapshots(image: Path, targets: tuple[str, ...]) -> dict[str, Any]:
    """Write the crate sources and the runtime and target library snapshots.

    Parameters
    ----------
    image
        Image folder.
    targets
        Target library names.

    Returns
    -------
    dict[str, Any]
        Source digests, target and runtime identities, and the target index.
    """
    sources = {
        f"source/{component}/{name}": _write(image / f"source/{component}/{name}", name.encode())
        for component in (CORE, ADAPTER)
        for name in ("Cargo.toml", "Cargo.lock", "README.md", "src/lib.rs")
    }
    target_libraries = {name: _digest(f"{name}\n".encode()) for name in targets}
    index = {
        name: {"path": f"rust_target_libraries/{number:04d}{Path(name).suffix}", "sha256": digest}
        for number, (name, digest) in enumerate(sorted(target_libraries.items()))
    }
    for name, item in index.items():
        _write(image / item["path"], f"{name}\n".encode())
    runtime = {name: _digest(f"{name}\n".encode()) for name in RUNTIME}
    for name, item in runtime_index(runtime).items():
        _write(image / "rust_runtime" / item["path"], f"{name}\n".encode())
    _write(
        image / "rust_runtime/runtime_source_index.json",
        canonical_json_bytes(runtime_index(runtime)),
    )
    return {"sources": sources, "targets": target_libraries, "runtime": runtime, "index": index}


def _records(core_source: str) -> dict[str, str]:
    """Return the four dependency records as rustc wrote them on the review host.

    Parameters
    ----------
    core_source
        Source that the controller's metadata record names.

    Returns
    -------
    dict[str, str]
        Record text by name in the image.
    """
    return {
        "rust_metadata/core.d": _record(
            "rust_metadata", "core.d", "libwitness_controller.rmeta", core_source
        ),
        "rust_metadata/adapter.d": _record(
            "rust_metadata", "adapter.d", "libwitness_amp_rust_kernel.rmeta", ADAPTER_SOURCE
        ),
        "objects/rust/core.d": _record(
            "objects/rust", "core.d", "libwitness_controller.rlib", CORE_SOURCE
        ),
        "objects/rust/adapter.d": _record(
            "objects/rust", "adapter.d", "libwitness_amp_rust_kernel.a", ADAPTER_SOURCE
        ),
    }


def _preparation(
    compiler: str, found: dict[str, Any], core_source: str, metadata: dict[str, str]
) -> dict[str, Any]:
    """Return the captured Rust preparation bound to the written snapshots and records.

    Parameters
    ----------
    compiler
        Compiler path of the toolchain identity.
    found
        Source digests, library identities and target index from ``_snapshots``.
    core_source
        Source that the controller's metadata record names.
    metadata
        Digests of the two metadata records.

    Returns
    -------
    dict[str, Any]
        Preparation document.
    """
    program = {"sha256": _digest(compiler.encode())}
    return {
        "schema": "loop-timing-witness.rust-preparation.v1",
        "toolchain": {
            "compiler": {"path": compiler, **program, "version": VERSIONS["rustc"]},
            "cargo": {"path": f"{TOOLS}/bin/cargo", **program, "version": VERSIONS["cargo"]},
            "verbose_version": VERSIONS["verbose"],
            "target": TARGET,
            "target_libraries": found["targets"],
            "runtime_libraries": found["runtime"],
        },
        "sources": found["sources"],
        "target_index": found["index"],
        "metadata_commands": rust_vectors(compiler, metadata=True),
        "compile_commands": rust_vectors(compiler, metadata=False),
        "dependencies": {core_source: found["sources"][core_source]}
        | {ADAPTER_SOURCE: found["sources"][ADAPTER_SOURCE]},
        "dependency_records": metadata,
    }


def _image(
    directory: Path,
    compiler: str = COMPILER,
    targets: tuple[str, ...] = TARGETS,
    core_source: str = CORE_SOURCE,
) -> dict[str, Any]:
    """Write a consistent Rust kernel image and return its receipts.

    Parameters
    ----------
    directory
        Case directory; the image is its ``image`` folder.
    compiler
        Compiler path of the toolchain identity.
    targets
        Target library names.
    core_source
        Source that the controller's metadata record names.

    Returns
    -------
    dict[str, Any]
        ``{"image": ..., "preparation": ...}``, the receipts the check reads.
    """
    image = directory / "image"
    found = _snapshots(image, targets)
    records = _records(core_source)
    record_digests = {name: _write(image / name, text.encode()) for name, text in records.items()}
    metadata = {name: record_digests[name] for name in records if "metadata" in name}
    data = _preparation(compiler, found, core_source, metadata)
    _write(image / "rust_preparation.json", canonical_json_bytes(data))
    outputs = {name: record_digests[name] for name in records if name.startswith("objects")}
    outputs[LIBRARY] = _write(image / LIBRARY, b"!<arch>\nwitness kernel\n")
    rlib = "objects/rust/libwitness_controller.rlib"
    outputs[rlib] = _write(image / rlib, b"witness controller\n")
    receipt = {"kernel_backend": "rust", "rust_kernel": {"preparation": data, "outputs": outputs}}
    return {"image": receipt, "preparation": {"kernel_backend": "rust"}}


def _receipts(change: Callable[[dict[str, Any]], object]) -> Callable[[Path, Any], object]:
    """Return an edit that changes the receipts, the argument of the check.

    Parameters
    ----------
    change
        Change applied to a copy of the receipts in place.

    Returns
    -------
    Callable[[Path, Any], object]
        Edit returning the changed receipts.
    """

    def edit(_: Path, argument: object) -> object:
        changed = json.loads(json.dumps(argument))
        change(changed)
        return changed

    return edit


PREPARATION: Final = "image/rust_preparation.json"
ZERO: Final = "0" * 64


def _c_kernel(keep: tuple[str, ...]) -> Callable[[dict[str, Any]], object]:
    """Return a change that declares the C kernel, keeping the named image members.

    Parameters
    ----------
    keep
        Image members that stay.

    Returns
    -------
    Callable[[dict[str, Any]], object]
        Change of the receipts.
    """

    def change(receipts: dict[str, Any]) -> None:
        receipts["preparation"].pop("kernel_backend")
        for name in ("kernel_backend", "rust_kernel"):
            if name not in keep:
                receipts["image"].pop(name)

    return change


def _declared(image: object, preparation: object) -> Callable[[dict[str, Any]], object]:
    """Return a change that sets both backend declarations.

    Parameters
    ----------
    image
        The image's declaration.
    preparation
        The preparation's declaration.

    Returns
    -------
    Callable[[dict[str, Any]], object]
        Change of the receipts.
    """

    def change(receipts: dict[str, Any]) -> None:
        receipts["image"]["kernel_backend"] = image
        receipts["preparation"]["kernel_backend"] = preparation

    return change


def _prepared(change: Callable[[dict[str, Any]], object]) -> Callable[[Path, Any], object]:
    """Return an edit that changes the captured Rust preparation document.

    Parameters
    ----------
    change
        Change applied to the decoded document in place.

    Returns
    -------
    Callable[[Path, Any], object]
        Tree edit.
    """

    def rewrite(data: dict[str, Any]) -> dict[str, Any]:
        change(data)
        return data

    return _document(PREPARATION, rewrite)


def _built(
    compiler: str = COMPILER, targets: tuple[str, ...] = TARGETS, core_source: str = CORE_SOURCE
) -> Callable[[Path], object]:
    """Return a builder of a consistent image with other inputs.

    Parameters
    ----------
    compiler
        Compiler path.
    targets
        Target library names.
    core_source
        Source the controller's metadata record names.

    Returns
    -------
    Callable[[Path], object]
        Image builder.
    """
    return lambda directory: _image(directory, compiler, targets, core_source)


def _receipt_cases() -> dict[str, Any]:
    """Return the cases of the declarations and the captured preparation.

    Returns
    -------
    dict[str, Any]
        Builders by case name; each returns the receipts.
    """
    return {
        "complete Rust image": _image,
        "C kernel": _edited(_image, _receipts(_c_kernel(()))),
        "C kernel with a Rust archive receipt": _edited(
            _image, _receipts(_c_kernel(("rust_kernel",)))
        ),
        "C kernel with a Rust declaration": _edited(
            _image, _receipts(_c_kernel(("kernel_backend",)))
        ),
        "preparation declares the C kernel": _edited(_image, _receipts(_declared("rust", "c"))),
        "image declares the C kernel": _edited(_image, _receipts(_declared("c", "rust"))),
        "image declares no kernel": _edited(
            _image, _receipts(lambda r: r["image"].pop("kernel_backend"))
        ),
        "Rust preparation missing": _edited(_image, _unlink(PREPARATION)),
        "Rust preparation not JSON": _edited(_image, _text(PREPARATION, "{")),
        "preparation schema changed": _edited(_image, _prepared(lambda d: d.update(schema="x"))),
        "toolchain target changed": _edited(
            _image, _prepared(lambda d: d["toolchain"].update(target="x"))
        ),
        "toolchain missing": _edited(_image, _prepared(lambda d: d.pop("toolchain"))),
        "metadata vectors disagree": _edited(
            _image, _prepared(lambda d: d["metadata_commands"].pop())
        ),
        "compile vectors disagree": _edited(
            _image, _prepared(lambda d: d["compile_commands"].pop())
        ),
        "compiler at the root folder": _built(compiler="/rustc"),
    }


def _snapshot_cases() -> dict[str, Any]:
    """Return the cases of the runtime, source and target library snapshots.

    Returns
    -------
    dict[str, Any]
        Builders by case name; each returns the receipts.
    """
    source = f"image/{CORE_SOURCE}"
    target = "image/rust_target_libraries/0000.rlib"
    others = (*TARGETS, f"{LIBRARIES}/libstd-0.so")
    return {
        "runtime library copy changed": _edited(
            _image, _text("image/rust_runtime/runtime_sources/0000/library", "x\n")
        ),
        "source changed": _edited(_image, _text(source, "x\n")),
        "source missing": _edited(_image, _unlink(source)),
        "source folder linked outside": _edited(
            _image, _link(f"image/source/{CORE}", f"../../../outside/{CORE}", f"outside/{CORE}")
        ),
        "target libraries without core": _built(targets=TARGETS[:4]),
        "target libraries without builtins": _built(targets=(*TARGETS[:2], *TARGETS[4:])),
        "target archive without metadata": _built(targets=TARGETS[1:]),
        "target library of another kind": _built(targets=others),
        "target names with only leading dots": _built(
            targets=(*TARGETS, f"{LIBRARIES}/..rlib", f"{LIBRARIES}/..rmeta")
        ),
        "target name ending in a dot": _built(targets=(*TARGETS, f"{LIBRARIES}/libx.")),
        "target names with dotted stems": _built(
            targets=(*TARGETS, f"{LIBRARIES}/libx-1.2.rlib", f"{LIBRARIES}/libx-1.2.rmeta")
        ),
        "target index disagrees": _edited(
            _image, _prepared(lambda d: d["target_index"][TARGETS[0]].update(sha256=ZERO))
        ),
        "target library copy changed": _edited(_image, _text(target, "x\n")),
        "target library copy missing": _edited(_image, _unlink(target)),
        "target library folder linked outside": _edited(
            _image, _link("image/rust_target_libraries", "../outside/t", "outside/t")
        ),
    }


def _output_cases() -> dict[str, Any]:
    """Return the cases of the dependency records and the compiled outputs.

    Returns
    -------
    dict[str, Any]
        Builders by case name; each returns the receipts.
    """
    return {
        "metadata record changed": _edited(_image, _text("image/rust_metadata/core.d", "x:\n")),
        "metadata record missing": _edited(_image, _unlink("image/rust_metadata/core.d")),
        "metadata dependencies differ": _edited(
            _image, _prepared(lambda d: d["dependencies"].update({CORE_SOURCE: ZERO}))
        ),
        "metadata record names another source": _built(core_source=f"source/{CORE}/README.md"),
        "compiled record names another source": _edited(
            _image,
            _text(
                "image/objects/rust/core.d",
                _record("objects/rust", "core.d", "x.rlib", f"source/{CORE}/README.md"),
            ),
        ),
        "archive without its magic": _edited(_image, _text(f"image/{LIBRARY}", "x\n")),
        "archive missing": _edited(_image, _unlink(f"image/{LIBRARY}")),
        "controller library missing": _edited(
            _image, _unlink("image/objects/rust/libwitness_controller.rlib")
        ),
        "output digest differs": _edited(
            _image,
            _receipts(lambda r: r["image"]["rust_kernel"]["outputs"].update({LIBRARY: ZERO})),
        ),
        "receipt preparation differs": _edited(
            _image, _receipts(lambda r: r["image"]["rust_kernel"]["preparation"].update(schema="x"))
        ),
    }


def _cases() -> dict[str, Any]:
    """Return every named case of ``validate_rust_image_receipt``, in corpus order.

    Returns
    -------
    dict[str, Any]
        Builders by case name; each returns the receipts.
    """
    return {**_receipt_cases(), **_snapshot_cases(), **_output_cases()}


def _outcome(directory: Path, receipts: dict[str, Any]) -> dict[str, Any]:
    """Run the check and return its value, refusal or ``OSError`` text, written with ``<root>``.

    Parameters
    ----------
    directory
        Case directory.
    receipts
        The image's and the preparation's receipts.

    Returns
    -------
    dict[str, Any]
        ``{"value": true}``, ``{"refusal": text}`` or ``{"os_error": text}``.
    """
    root = str(directory)
    try:
        validate_rust_image_receipt(directory / "image", receipts["image"], receipts["preparation"])
    except ValueError as error:
        return {"refusal": str(error).replace(root, "<root>")}
    except OSError as error:
        return {"os_error": str(error).replace(root, "<root>")}
    return {"value": True}


def corpus(directory: Path) -> dict[str, Any]:
    """Build every case under an owned directory and return the corpus.

    Parameters
    ----------
    directory
        Owned empty directory for the image trees.

    Returns
    -------
    dict[str, Any]
        The complete image's tree and receipts, and each case's patch, edits and outcome.
    """
    directory = directory.resolve()
    template = directory / "template"
    template.mkdir()
    base = _image(template)
    complete = _tree(template)
    cases: list[dict[str, Any]] = []
    for name, build in _cases().items():
        path = directory / f"case-{len(cases)}"
        path.mkdir()
        receipts = build(path)
        assert isinstance(receipts, dict)
        item: dict[str, Any] = {"name": name, "patch": _patch(base, receipts)}
        item["edits"] = _edits(complete, _tree(path))
        cases.append({**item, **_outcome(path, receipts)})
    return {
        "schema": "loop-timing-witness.amp-rust-receipt-cases.v1",
        "description": (
            "Python's validate_rust_image_receipt on <case>/image with the receipts {image, "
            "preparation}. Each case writes the complete image's tree with its edits (text, "
            "symlinks or empty folders) and patches the complete image's receipts (member paths "
            "set or removed). value true is a passing check; refusal and os_error carry "
            "Python's text, the case directory written <root>."
        ),
        "tree": complete,
        "receipts": base,
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
    """Rebuild the corpus from Python's check and require the committed file.

    Parameters
    ----------
    tmp_path
        Owned directory for the image trees.
    """
    assert CORPUS.read_text(encoding="utf-8") == _corpus_text(corpus(tmp_path))
    assert CORPUS.with_name(CORPUS.name + ".license").is_file()


def test_crate_schema_equals_python_toolchain() -> None:
    """Require the native analysis's committed toolchain schema to equal Python's constant."""
    assert json.loads(CRATE_SCHEMA.read_text(encoding="utf-8")) == TOOLCHAIN
