# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual frozen Rust source and compiler dependency custody

"""Compile frozen original sources and reconcile genuine Rust dependency records."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from amp_rust_admission import admit_rust_archive, admit_rust_preparation
from amp_rust_build import prepare_rust_sources
from amp_rust_dependencies import rust_dependency_hashes
from amp_rust_vectors import ADAPTER, CORE

from loop_timing_witness.amp_rust_receipt import validate_rust_preparation_snapshot
from manifest_io import sha256_of_file

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def compiled_sources(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Freeze actual Rust source/library bytes and run both metadata and real library compilation.

    Parameters
    ----------
    tmp_path_factory
        Exclusive actual build allocation.

    Returns
    -------
    Path
        Captured sources and genuine metadata/final compiler dependency records and libraries.
    """
    directory = tmp_path_factory.mktemp("rust-source-custody")
    record = prepare_rust_sources(ROOT, directory, "rustc")
    for phase in ["compile_commands"]:
        for index, argv in enumerate(record[phase]):
            result = subprocess.run(
                argv, cwd=directory, capture_output=True, timeout=60, check=False
            )
            (directory / f"{phase}_{index}.log").write_bytes(result.stdout + result.stderr)
            assert result.returncode == 0, result.stderr
    return directory


def test_real_rust_source_and_library_custody(compiled_sources: Path) -> None:
    """Require original source, target library and compiler-recorded dependency bytes to agree.

    Parameters
    ----------
    compiled_sources
        Original real compiler output and captured source/target archive bytes.
    """
    metadata = tuple((compiled_sources / "rust_metadata").glob("*.d"))
    compiled = tuple((compiled_sources / "objects/rust").glob("*.d"))
    assert len(metadata) == len(compiled) == 2
    assert rust_dependency_hashes(metadata, compiled_sources) == rust_dependency_hashes(
        compiled, compiled_sources
    )
    record = json.loads((compiled_sources / "rust_preparation.json").read_bytes())
    for name, digest in record["sources"].items():
        assert sha256_of_file(compiled_sources / name) == digest
        assert sha256_of_file(ROOT / name.removeprefix("source/")) == digest
    for name, value in record["target_index"].items():
        assert sha256_of_file(Path(name)) == value["sha256"]
        assert sha256_of_file(compiled_sources / value["path"]) == value["sha256"]
    assert {Path(name).suffix for name in record["target_index"]} == {".rlib", ".rmeta"}


@pytest.mark.parametrize(
    "fault",
    [
        "empty",
        "missing-colon",
        "environment",
        "phony",
        "escaped",
        "targets",
        "absolute",
        "empty-target",
    ],
)
def test_rust_dependency_corruption_refused(
    compiled_sources: Path, tmp_path: Path, fault: str
) -> None:
    """Corrupt a real owned compiler record and require admission to refuse it.

    Parameters
    ----------
    compiled_sources
        Actual unchanged compiler records and original source inputs.
    tmp_path
        Exclusive corrupt record allocation.
    fault
        Incomplete or escaping rule shape to substitute in that actual record.
    """
    data = (compiled_sources / "rust_metadata/core.d").read_text()
    source = "source/controllers/rust/src/lib.rs"
    if fault == "empty":
        data = ""
    elif fault == "missing-colon":
        data = "malformed original record"
    elif fault == "environment":
        data += "\n# env-dep:UNRECORDED=changed\n"
    elif fault == "phony":
        data += "\nother/source.rs:\n"
    elif fault == "escaped":
        data = data.replace(source, "../outside.rs")
    elif fault == "absolute":
        data = data.replace(source, str((compiled_sources / source).resolve()))
    elif fault == "empty-target":
        data = data.replace("rust_metadata/core.d:", ":")
    else:
        data = data.replace("rust_metadata/core.d:", "first second:")
    path = tmp_path / "corrupt.d"
    path.write_text(data)
    with pytest.raises(ValueError, match="Rust dependency"):
        rust_dependency_hashes((path,), compiled_sources)


def test_no_rust_dependency_record_refused(tmp_path: Path) -> None:
    """Refuse missing compiler evidence rather than treating it as a source-free build.

    Parameters
    ----------
    tmp_path
        Exclusive source root.
    """
    with pytest.raises(ValueError, match="requires actual dependency"):
        rust_dependency_hashes((), tmp_path)


@pytest.mark.parametrize("fault", ["file-symlink", "broken-symlink", "directory-symlink"])
def test_original_rust_source_symlink_escape_refused(tmp_path: Path, fault: str) -> None:
    """Refuse an outside or absent original source before any Rust build receipt exists.

    Parameters
    ----------
    tmp_path
        Exclusive source tree, outside file and attempted original build snapshot.
    fault
        Actual symlink file, absent symlink target or symlinked parent directory.
    """
    root = tmp_path / "source-root"
    for component in [CORE, ADAPTER]:
        for name in ["Cargo.toml", "Cargo.lock", "README.md", "src/lib.rs"]:
            relative = Path(component) / name
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
    original = root / ADAPTER / "src/lib.rs"
    if fault == "directory-symlink":
        outside = tmp_path / "outside-src/lib.rs"
        outside.parent.mkdir()
        shutil.copy2(original, outside)
        original.unlink()
        original.parent.rmdir()
        original.parent.symlink_to(outside.parent, target_is_directory=True)
    else:
        outside = tmp_path / "outside-original.rs"
        if fault == "file-symlink":
            shutil.copy2(original, outside)
        original.unlink()
        original.symlink_to(outside)
    directory = tmp_path / "snapshot"
    directory.mkdir()
    with pytest.raises(ValueError, match="contained regular file"):
        prepare_rust_sources(root, directory, "rustc")
    assert not (directory / "rust_preparation.json").exists()


def test_real_rust_preparation_and_archive_admission(compiled_sources: Path) -> None:
    """Admit actual captured sources and the compiler-produced final RV64 archive.

    Parameters
    ----------
    compiled_sources
        Actual metadata and final compiler outputs.
    """
    prepared = admit_rust_preparation(compiled_sources)
    receipt = admit_rust_archive(compiled_sources)
    assert receipt["preparation"] == prepared
    assert len(receipt["outputs"]) == 4
    for name, digest in receipt["outputs"].items():
        assert sha256_of_file(compiled_sources / name) == digest


@pytest.mark.parametrize("fault", ["metadata-omitted", "core-omitted", "unknown-suffix"])
def test_portable_target_library_closure_refused(compiled_sources: Path, fault: str) -> None:
    """Refuse incomplete target archive/metadata declarations without a live compiler.

    Parameters
    ----------
    compiled_sources
        Actual captured original libraries and metadata.
    fault
        Declared missing metadata/core pair or unsupported target input suffix.
    """
    data = json.loads((compiled_sources / "rust_preparation.json").read_bytes())
    libraries = data["toolchain"]["target_libraries"]
    if fault == "metadata-omitted":
        name = next(name for name in libraries if name.endswith(".rmeta"))
        del libraries[name]
    elif fault == "core-omitted":
        for name in list(libraries):
            if Path(name).name.startswith("libcore-"):
                del libraries[name]
    else:
        libraries["/unrecognized.target"] = "0" * 64
    with pytest.raises(ValueError, match="Rust original target archives and metadata"):
        validate_rust_preparation_snapshot(compiled_sources, data)


@pytest.mark.parametrize(
    "fault",
    [
        "schema",
        "shape",
        "toolchain",
        "compiler",
        "path",
        "vectors",
        "metadata-vectors",
        "sources",
        "index",
        "metadata-omitted",
        "dependencies",
        "records",
    ],
)
def test_rust_preparation_receipt_drift_refused(compiled_sources: Path, fault: str) -> None:
    """Mutate an actual original preparation receipt and restore it after genuine refusal.

    Parameters
    ----------
    compiled_sources
        Owned actual preparation whose receipt is restored after each admission attempt.
    fault
        Original identity or compiler-command field to corrupt.
    """
    path = compiled_sources / "rust_preparation.json"
    original = path.read_bytes()
    data = json.loads(original)
    changes: dict[str, tuple[tuple[str, ...], object]] = {
        "schema": (("schema",), "incorrect"),
        "shape": (("toolchain",), []),
        "toolchain": (("toolchain", "verbose_version"), "incorrect"),
        "compiler": (("toolchain", "compiler"), {}),
        "path": (("toolchain", "compiler", "path"), 1),
        "metadata-vectors": (("metadata_commands",), []),
        "vectors": (("compile_commands",), []),
        "sources": (("sources",), {}),
        "index": (("target_index",), {}),
        "dependencies": (("dependencies",), {}),
        "records": (("dependency_records",), {}),
    }
    if fault == "metadata-omitted":
        for field in [data["toolchain"]["target_libraries"], data["target_index"]]:
            for name in list(field):
                if name.endswith(".rmeta"):
                    del field[name]
    else:
        keys, value = changes[fault]
        selected = data
        for key in keys[:-1]:
            selected = selected[key]
        selected[keys[-1]] = value
    try:
        path.write_text(json.dumps(data))
        with pytest.raises(ValueError, match="Rust"):
            admit_rust_preparation(compiled_sources)
    finally:
        path.write_bytes(original)


@pytest.mark.parametrize(
    "fault", ["source", "library", "target-metadata", "metadata", "final", "archive"]
)
def test_rust_actual_byte_drift_refused(compiled_sources: Path, fault: str) -> None:
    """Alter owned actual compiler input or output bytes and require admission refusal.

    Parameters
    ----------
    compiled_sources
        Owned actual preparation; altered original bytes are restored after each check.
    fault
        Source, target library, metadata record, final dependency graph or static archive to alter.
    """
    names = {
        "source": "source/controllers/rust/src/lib.rs",
        "library": "rust_target_libraries/0000.rlib",
        "target-metadata": "rust_target_libraries/0001.rmeta",
        "metadata": "rust_metadata/core.d",
        "final": "objects/rust/adapter.d",
        "archive": "objects/rust/libwitness_amp_rust_kernel.a",
    }
    path = compiled_sources / names[fault]
    original = path.read_bytes()
    changed = (
        original.replace(
            b"source/runtime/bare_metal/rust_kernel/src/lib.rs",
            b"source/controllers/rust/src/lib.rs",
        )
        if fault == "final"
        else b"changed original bytes"
    )
    try:
        path.write_bytes(changed)
        with pytest.raises(ValueError, match="Rust"):
            admit_rust_archive(compiled_sources)
    finally:
        path.write_bytes(original)


@pytest.mark.parametrize(
    "name",
    [
        "source/controllers/rust/src/lib.rs",
        "rust_target_libraries/0000.rlib",
        "rust_target_libraries/0001.rmeta",
    ],
)
def test_rust_snapshot_symlink_escape_refused(
    compiled_sources: Path, tmp_path: Path, name: str
) -> None:
    """Replace an owned captured input with equal bytes outside its root and require refusal.

    Parameters
    ----------
    compiled_sources
        Owned actual preparation, restored after the containment check.
    tmp_path
        Exclusive outside file allocation within the pytest workspace.
    name
        Captured source or target archive whose original path must remain contained.
    """
    path = compiled_sources / name
    original = path.read_bytes()
    outside = tmp_path / "outside-input"
    outside.write_bytes(original)
    try:
        path.unlink()
        path.symlink_to(outside)
        with pytest.raises(ValueError, match="Rust"):
            admit_rust_preparation(compiled_sources)
    finally:
        path.unlink()
        path.write_bytes(original)
