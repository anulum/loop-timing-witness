# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — genuine Rust selector and installed library identities

"""Interrogate actual Rust programs and refuse invalid selections before execution."""

import shlex
import shutil
import subprocess
import threading
from pathlib import Path

import pytest
from amp_build_toolchain import rust_program_query
from amp_rust_build import prepare_rust_sources
from amp_rust_toolchain import TARGET, rust_toolchain

from manifest_io import sha256_of_file

ROOT = Path(__file__).resolve().parents[1]


def test_proxy_and_actual_compiler_identity() -> None:
    """Require the installed proxy and direct compiler to freeze identical actual input bytes."""
    selected = rust_toolchain("rustc")
    assert selected == rust_toolchain(selected["compiler"]["path"])
    assert selected["target"] == TARGET
    for path, digest in selected["target_libraries"].items():
        assert sha256_of_file(Path(path)) == digest
    archives = {Path(name).stem for name in selected["target_libraries"] if name.endswith(".rlib")}
    metadata = {Path(name).stem for name in selected["target_libraries"] if name.endswith(".rmeta")}
    assert archives == metadata
    for path, digest in selected["runtime_libraries"].items():
        assert sha256_of_file(Path(path)) == digest


def test_missing_rust_selector_refused() -> None:
    """Refuse an absent operator selection without substituting the default compiler."""
    with pytest.raises(ValueError, match="actual executable"):
        rust_toolchain("witness-rust-compiler-does-not-exist")


def test_real_compiler_selector_that_switches_to_cargo_is_refused(tmp_path: Path) -> None:
    """Refuse a selector whose sysroot is Rust but whose version query invokes actual Cargo.

    Parameters
    ----------
    tmp_path
        Exclusive executable selector that invokes original installed build programs.
    """
    original = rust_toolchain("rustc")
    selector = tmp_path / "switching-rustc"
    compiler = original["compiler"]["path"]
    cargo = original["cargo"]["path"]
    selector.write_text(
        "#!/bin/sh\n"
        f'if [ "$1" = "-vV" ]; then exec {shlex.quote(cargo)} "$@"; fi\n'
        f'exec {shlex.quote(compiler)} "$@"\n'
    )
    selector.chmod(0o755)
    with pytest.raises(ValueError, match="compiler identities disagree"):
        rust_toolchain(str(selector))


@pytest.mark.parametrize("query", ["arbitrary", "sysroot", "version", "target-libraries"])
def test_unavailable_introspection_refused(tmp_path: Path, query: str) -> None:
    """Refuse fixed or arbitrary queries when their selected program is absent or nonexecutable.

    Parameters
    ----------
    tmp_path
        Exclusive invalid executable allocation.
    query
        Unsupported arguments or one of the fixed introspection selections.
    """
    path = tmp_path / "rustc"
    with pytest.raises(ValueError, match="fixed query"):
        rust_program_query(path, query)
    path.write_bytes(b"actual nonexecutable file")
    with pytest.raises(ValueError, match="fixed query"):
        rust_program_query(path, query)


@pytest.fixture
def owned_rustup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, dict[str, object]]:
    """Copy actual installed Rust programs into an isolated Rustup-selected sysroot.

    Parameters
    ----------
    tmp_path
        Exclusive compiler and Rustup home; installed global toolchain remains read-only.
    monkeypatch
        Selects the owned Rustup home only for this test and its compiler subprocesses.

    Returns
    -------
    tuple of Path, Path, dict of str to object
        Owned toolchain, empty target directory and original actual toolchain receipt.
    """
    original = rust_toolchain("rustc")
    sysroot = Path(original["compiler"]["path"]).parent.parent
    toolchain = tmp_path / "toolchain"
    (toolchain / "bin").mkdir(parents=True)
    library = toolchain / "lib"
    library.mkdir()
    shutil.copy2(sysroot / "bin/rustc", toolchain / "bin/rustc")
    for source in (sysroot / "lib").iterdir():
        if source.is_file() and not source.is_symlink():
            shutil.copy2(source, library / source.name)
        elif source.is_symlink():
            (library / source.name).symlink_to(source.readlink())
    (library / "rustlib" / TARGET / "lib").mkdir(parents=True)
    rustup = shutil.which("rustup")
    assert rustup is not None, "actual installed Rustup is required"
    monkeypatch.setenv("RUSTUP_HOME", str(tmp_path / "rustup-home"))
    monkeypatch.setenv("RUSTUP_TOOLCHAIN", "witness-actual")
    subprocess.run(
        [rustup, "toolchain", "link", "witness-actual", str(toolchain)],
        check=True,
        capture_output=True,
        timeout=30,
    )
    proxy = shutil.which("rustc")
    assert proxy is not None
    assert Path(rust_program_query(Path(proxy), "sysroot").strip()).resolve() == toolchain.resolve()
    return toolchain, library / "rustlib" / TARGET / "lib", original


def _copy_owned_target(original: dict[str, object], target: Path, *, suffix: str) -> None:
    """Copy actual installed target inputs of one suffix into the owned compiler sysroot.

    Parameters
    ----------
    original
        Actual original target-library receipt.
    target
        Owned Rustup-selected target directory.
    suffix
        `.rlib` or `.rmeta` target input suffix to capture.
    """
    libraries = original["target_libraries"]
    assert isinstance(libraries, dict)
    for name in libraries:
        path = Path(name)
        if path.suffix == suffix:
            shutil.copy2(path, target / path.name)


def test_actual_owned_rustup_missing_program_and_metadata(
    owned_rustup: tuple[Path, Path, dict[str, object]],
) -> None:
    """Refuse absent Cargo, absent target libraries and missing paired metadata in sequence.

    Parameters
    ----------
    owned_rustup
        Exclusive real compiler copy selected through an isolated Rustup home.
    """
    toolchain, target, original = owned_rustup
    with pytest.raises(ValueError, match="actual compiler and Cargo"):
        rust_toolchain("rustc")
    compiler = original["compiler"]
    assert isinstance(compiler, dict)
    sysroot = Path(compiler["path"]).parent.parent
    shutil.copy2(sysroot / "bin/cargo", toolchain / "bin/cargo")
    with pytest.raises(ValueError, match="core and compiler-builtins"):
        rust_toolchain("rustc")
    _copy_owned_target(original, target, suffix=".rlib")
    with pytest.raises(ValueError, match="archives and metadata"):
        rust_toolchain("rustc")


def test_actual_owned_target_symlink_boundaries(
    owned_rustup: tuple[Path, Path, dict[str, object]],
) -> None:
    """Refuse a symlinked target file or target directory with actual original Rust inputs.

    Parameters
    ----------
    owned_rustup
        Exclusive compiler and target directories; installed global libraries stay read-only.
    """
    toolchain, target, original = owned_rustup
    compiler = original["compiler"]
    assert isinstance(compiler, dict)
    shutil.copy2(Path(compiler["path"]).parent / "cargo", toolchain / "bin/cargo")
    for suffix in [".rlib", ".rmeta"]:
        _copy_owned_target(original, target, suffix=suffix)
    libraries = original["target_libraries"]
    assert isinstance(libraries, dict)
    assert len(rust_toolchain("rustc")["target_libraries"]) == len(libraries)
    metadata = next(target.glob("*.rmeta"))
    retained = metadata.with_suffix(".retained")
    metadata.rename(retained)
    metadata.symlink_to(retained)
    with pytest.raises(ValueError, match="regular file pairs"):
        rust_toolchain("rustc")
    metadata.unlink()
    retained.rename(metadata)
    inside = target.with_name("retained-target-libraries")
    target.rename(inside)
    target.symlink_to(Path(next(iter(libraries))).parent)
    with pytest.raises(ValueError, match="must belong to the original compiler sysroot"):
        rust_toolchain("rustc")


def test_actual_owned_target_drift_during_metadata_compilation(
    owned_rustup: tuple[Path, Path, dict[str, object]], tmp_path: Path
) -> None:
    """Refuse a changed owned target archive after genuine metadata compilation.

    Parameters
    ----------
    owned_rustup
        Exclusive compiler and original target-library copies.
    tmp_path
        Exclusive original source snapshot and actual compiler output directory.
    """
    toolchain, target, original = owned_rustup
    compiler = original["compiler"]
    assert isinstance(compiler, dict)
    shutil.copy2(Path(compiler["path"]).parent / "cargo", toolchain / "bin/cargo")
    for suffix in [".rlib", ".rmeta"]:
        _copy_owned_target(original, target, suffix=suffix)
    output = tmp_path / "metadata-drift"
    output.mkdir()
    archive = next(target.glob("liballoc-*.rlib"))
    stopped = threading.Event()
    mutated = threading.Event()

    def change_owned_archive_during_real_compile() -> None:
        """Change an owned installed archive after snapshot and during actual metadata compile."""
        marker = output / "rust_metadata/input_0.log"
        while not stopped.wait(0.002):
            if marker.exists():
                with archive.open("ab") as stream:
                    stream.write(b"owned-archive-drift")
                mutated.set()
                return

    watcher = threading.Thread(target=change_owned_archive_during_real_compile)
    watcher.start()
    try:
        with pytest.raises(ValueError, match="changed during metadata compilation"):
            prepare_rust_sources(ROOT, output, "rustc")
    finally:
        stopped.set()
        watcher.join(timeout=2)
    assert mutated.is_set()
    assert not (output / "rust_preparation.json").exists()
