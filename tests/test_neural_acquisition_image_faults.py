# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — image executor binding, boundary, tree and closure faults

"""Damage the image executor's binding, host boundary, image tree or observation.

Each fault must give one refusal or one report in Python and Rust. A binding
is constructed by the consumer's own registry factory in both languages, so a
binding refusal is compared where the Rust consumer meets it. A few kernel
failures cannot be produced by data; they are injected into the Rust verifier
and compared with the refusal the Python verifier gives for any such
operating-system error.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from neural_acquisition_support import (
    CHECKER,
    ENTRY,
    build_neural_acquisition,
    make_writable,
    rebind_image,
)
from neural_rust_support import assert_same_outcome, python_outcome, rust_outcome

from loop_timing_witness.manifest_io import canonical_json_bytes
from loop_timing_witness.neural_checker_image import ImageCheckerExecutor
from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError
from loop_timing_witness.neural_run_api import build_neural_run_report, load_neural_run

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from neural_acquisition_support import NeuralAcquisition

_CLOSED = "Checker image executor binding is not its closed reviewed form."
_HOST = "Checker image host platform or account differs from its boundary."
_ENTRIES = "Checker image entries differ from the bound image inventory."
_LINKS = "Checker image links differ from the bound image inventory."
_FILE = "Checker image file type, mode or length differs from its binding."
_ROOT = "Checker image root must be an absolute real directory."
_BIND = "Cannot bind the complete public neural acquisition."
_WORKER = "checker/worker.py"
_LARGE = 256 * 1024 * 1024 + 1


@pytest.fixture
def acquisition(tmp_path: Path) -> Iterator[NeuralAcquisition]:
    """Build one complete image acquisition and restore its permissions afterwards.

    Parameters
    ----------
    tmp_path
        Owned acquisition directory.

    Yields
    ------
    NeuralAcquisition
        Acquisition admitted by the test image executor.
    """
    written = build_neural_acquisition(tmp_path / "run")
    yield written
    for path in tmp_path.rglob("*"):
        if path.is_dir() and not path.is_symlink():
            path.chmod(0o755)
    make_writable(tmp_path)


def _factory_outcome(acquisition: NeuralAcquisition, binding: bytes) -> dict[str, Any]:
    """Run the Python API with a registry factory that constructs the image executor.

    Parameters
    ----------
    acquisition
        Acquisition admitted by the test image executor.
    binding
        Executor binding the factory constructs.

    Returns
    -------
    dict[str, Any]
        ``{"report": ...}`` or ``{"refusal": message}``.
    """
    policy, checker, executor = acquisition.entry
    assert isinstance(executor, ImageCheckerExecutor)
    (key,) = acquisition.registry

    def factory() -> tuple[bytes, bytes, ImageCheckerExecutor]:
        """Construct the executor from the binding when the entry is selected.

        Returns
        -------
        tuple[bytes, bytes, ImageCheckerExecutor]
            Reviewed policies and the constructed executor.
        """
        return (
            policy,
            checker,
            ImageCheckerExecutor(executor.image_root, binding, executor.runtime_bytes),
        )

    try:
        inputs = load_neural_run(acquisition.manifest, registry={key: factory})
    except NeuralCaptureRefusalError as exc:
        return {"refusal": str(exc)}
    return {"report": build_neural_run_report(inputs)}


def _edited(acquisition: NeuralAcquisition, edit: Callable[[dict[str, Any]], object]) -> bytes:
    """Return the acquisition's executor binding with one edit applied.

    Parameters
    ----------
    acquisition
        Acquisition admitted by the test image executor.
    edit
        Mutates the decoded binding in place.

    Returns
    -------
    bytes
        Canonical edited binding.
    """
    executor = acquisition.entry[2]
    assert isinstance(executor, ImageCheckerExecutor)
    binding = json.loads(executor.binding_bytes)
    edit(binding)
    return canonical_json_bytes(binding)


def _setter(*path: str | int, value: object) -> Callable[[dict[str, Any]], None]:
    """Return an edit that assigns one nested binding value.

    Parameters
    ----------
    *path
        Keys and indexes to the parent container, then the final key.
    value
        Assigned value.

    Returns
    -------
    Callable[[dict[str, Any]], None]
        In-place edit.
    """

    def edit(binding: dict[str, Any]) -> None:
        """Assign the value.

        Parameters
        ----------
        binding
            Decoded binding.
        """
        target: Any = binding
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    return edit


def _without_mode(binding: dict[str, Any]) -> None:
    """Remove the mode of the first image file.

    Parameters
    ----------
    binding
        Decoded binding.
    """
    del binding["image"]["files"][0]["mode"]


_CONSTRUCTION: dict[str, tuple[Callable[[dict[str, Any]], object] | None, str]] = {
    "syntax": (None, "Invalid original checker image executor binding."),
    "schema": (_setter("schema_id", value="other"), _CLOSED),
    "empty-command": (_setter("command", value=[]), _CLOSED),
    "open-command": (_setter("command", 0, value="{other}"), _CLOSED),
    "open-environment": (_setter("bootstrap_environment", "X", value="{other}"), _CLOSED),
    "zero-deadline": (_setter("deadline_seconds", value=0), _CLOSED),
    "long-deadline": (_setter("deadline_seconds", value=301), _CLOSED),
    "flag-deadline": (_setter("deadline_seconds", value=True), _CLOSED),
    "no-sources": (_setter("source_files", value=[]), _CLOSED),
    "no-workers": (_setter("worker_files", value=[]), _CLOSED),
    "text-uid": (_setter("host_boundary", "uid", value="0"), _CLOSED),
    "wide-gid": (_setter("host_boundary", "gid", value=2**32), _CLOSED),
    "file-without-mode": (_without_mode, _CLOSED),
    "link-not-record": (_setter("image", "symlinks", value=[1]), _CLOSED),
    "extra-member": (_setter("extra", value=1), _CLOSED),
}


@pytest.mark.parametrize("fault", list(_CONSTRUCTION))
def test_binding_construction_refuses_alike(
    acquisition: NeuralAcquisition, tmp_path: Path, fault: str
) -> None:
    """Refuse a binding that is not the closed reviewed form when the factory builds it.

    Parameters
    ----------
    acquisition
        Acquisition admitted by the test image executor.
    tmp_path
        Owned Rust outcome directory.
    fault
        Named binding fault.
    """
    edit, message = _CONSTRUCTION[fault]
    binding = b"{" if edit is None else _edited(acquisition, edit)
    python = _factory_outcome(acquisition, binding)
    rust = rust_outcome(acquisition, tmp_path / "rust", binding=binding)
    assert python == {"refusal": message}
    assert_same_outcome(python, rust)


def _real_file(binding: dict[str, Any], *, digest: str | None = None) -> None:
    """Bind one actual host launcher file, optionally with another digest.

    Parameters
    ----------
    binding
        Decoded binding.
    digest
        Replacement digest, or ``None`` for the actual one.
    """
    path = Path(shutil.which("sh") or "/bin/sh").resolve()
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    binding["host_boundary"]["files"] = [
        {"path": str(path), "sha256": digest or actual, "byte_length": len(raw)}
    ]


_BOUNDARY: dict[str, tuple[Callable[[dict[str, Any]], object], str | None]] = {
    "system": (_setter("host_boundary", "system", value="Other"), _HOST),
    "machine": (_setter("host_boundary", "machine", value="other"), _HOST),
    "kernel": (_setter("host_boundary", "kernel_release", value="other"), _HOST),
    "uid": (_setter("host_boundary", "uid", value=os.getuid() + 1), _HOST),
    "gid": (_setter("host_boundary", "gid", value=os.getgid() + 1), _HOST),
    "launcher-file": (_real_file, None),
    "changed-launcher-file": (
        lambda binding: _real_file(binding, digest="0" * 64),
        "Selected checker runtime file differs from its reviewed binding.",
    ),
    "present-absence": (_setter("host_boundary", "absent_paths", value=["/"]), None),
}


@pytest.mark.parametrize("fault", list(_BOUNDARY))
def test_host_boundary_is_verified_alike(
    acquisition: NeuralAcquisition, tmp_path: Path, fault: str
) -> None:
    """Refuse a host boundary that differs, and run under one that holds.

    Parameters
    ----------
    acquisition
        Acquisition admitted by the test image executor.
    tmp_path
        Owned Rust outcome directory.
    fault
        Named boundary change.
    """
    edit, message = _BOUNDARY[fault]
    if fault == "present-absence":
        message = "Checker image host contains a path its boundary requires absent."
    rebound = rebind_image(acquisition, edit)
    python = python_outcome(rebound)
    assert_same_outcome(python, rust_outcome(rebound, tmp_path / "rust"))
    if message is None:
        assert python["report"]["verification"]["whole"] is True
    else:
        assert python == {"refusal": message}


def _with_root(acquisition: NeuralAcquisition, root: Path) -> NeuralAcquisition:
    """Return the acquisition with its image executor rooted elsewhere.

    Parameters
    ----------
    acquisition
        Acquisition admitted by the test image executor.
    root
        Selected image root.

    Returns
    -------
    NeuralAcquisition
        The same acquisition and binding with another image root.
    """
    policy, checker, executor = acquisition.entry
    assert isinstance(executor, ImageCheckerExecutor)
    moved = ImageCheckerExecutor(root, executor.binding_bytes, executor.runtime_bytes)
    return replace(acquisition, entry=(policy, checker, moved))


def _image_file(acquisition: NeuralAcquisition, name: str) -> Path:
    """Return one image file made writable for a deliberate change.

    Parameters
    ----------
    acquisition
        Acquisition admitted by the test image executor.
    name
        Image-relative file name.

    Returns
    -------
    Path
        Writable image file.
    """
    path = acquisition.image / name
    path.chmod(0o644)
    return path


def _extra_file(acquisition: NeuralAcquisition) -> NeuralAcquisition:
    """Add a file the binding does not list.

    Parameters
    ----------
    acquisition
        Acquisition admitted by the test image executor.

    Returns
    -------
    NeuralAcquisition
        The unchanged acquisition.
    """
    (acquisition.image / "extra.txt").write_bytes(b"")
    return acquisition


def _extra_directory(acquisition: NeuralAcquisition) -> NeuralAcquisition:
    """Add an empty directory the binding does not list.

    Parameters
    ----------
    acquisition
        Acquisition admitted by the test image executor.

    Returns
    -------
    NeuralAcquisition
        The unchanged acquisition.
    """
    (acquisition.image / "extra").mkdir()
    return acquisition


def _unreadable_directory(acquisition: NeuralAcquisition) -> NeuralAcquisition:
    """Make one bound image directory unreadable.

    Parameters
    ----------
    acquisition
        Acquisition admitted by the test image executor.

    Returns
    -------
    NeuralAcquisition
        The unchanged acquisition.
    """
    (acquisition.image / "checker").chmod(0)
    return acquisition


def _non_utf8_name(acquisition: NeuralAcquisition) -> NeuralAcquisition:
    """Add an entry whose name is not UTF-8.

    Parameters
    ----------
    acquisition
        Acquisition admitted by the test image executor.

    Returns
    -------
    NeuralAcquisition
        The unchanged acquisition.
    """
    Path(os.fsdecode(os.fsencode(acquisition.image) + b"/\xff")).write_bytes(b"")
    return acquisition


def _extra_link(acquisition: NeuralAcquisition) -> NeuralAcquisition:
    """Add a link the binding does not list.

    Parameters
    ----------
    acquisition
        Acquisition admitted by the test image executor.

    Returns
    -------
    NeuralAcquisition
        The unchanged acquisition.
    """
    (acquisition.image / "link").symlink_to("checker")
    return acquisition


def _non_utf8_link(acquisition: NeuralAcquisition) -> NeuralAcquisition:
    """Add a link whose target is not UTF-8.

    Parameters
    ----------
    acquisition
        Acquisition admitted by the test image executor.

    Returns
    -------
    NeuralAcquisition
        The unchanged acquisition.
    """
    (acquisition.image / "link").symlink_to(os.fsdecode(b"\xff"))
    return acquisition


def _bound_link(acquisition: NeuralAcquisition) -> NeuralAcquisition:
    """Add a link and bind it.

    Parameters
    ----------
    acquisition
        Acquisition admitted by the test image executor.

    Returns
    -------
    NeuralAcquisition
        The acquisition whose binding lists the link.
    """
    (acquisition.image / "link").symlink_to("checker")
    return rebind_image(
        acquisition, _setter("image", "symlinks", value=[{"path": "link", "target": "checker"}])
    )


def _mode(acquisition: NeuralAcquisition) -> NeuralAcquisition:
    """Change the mode of one bound image file.

    Parameters
    ----------
    acquisition
        Acquisition admitted by the test image executor.

    Returns
    -------
    NeuralAcquisition
        The unchanged acquisition.
    """
    _image_file(acquisition, _WORKER)
    return acquisition


def _longer(acquisition: NeuralAcquisition) -> NeuralAcquisition:
    """Append one byte to a bound image file, keeping its mode.

    Parameters
    ----------
    acquisition
        Acquisition admitted by the test image executor.

    Returns
    -------
    NeuralAcquisition
        The unchanged acquisition.
    """
    path = _image_file(acquisition, _WORKER)
    path.write_bytes(path.read_bytes() + b"\n")
    path.chmod(0o444)
    return acquisition


def _changed_bytes(acquisition: NeuralAcquisition) -> NeuralAcquisition:
    """Change one byte of a bound image file, keeping its length and mode.

    Parameters
    ----------
    acquisition
        Acquisition admitted by the test image executor.

    Returns
    -------
    NeuralAcquisition
        The unchanged acquisition.
    """
    path = _image_file(acquisition, _WORKER)
    raw = bytearray(path.read_bytes())
    raw[-1] ^= 1
    path.write_bytes(bytes(raw))
    path.chmod(0o444)
    return acquisition


def _fifo(acquisition: NeuralAcquisition) -> NeuralAcquisition:
    """Replace a bound image file by a FIFO.

    Parameters
    ----------
    acquisition
        Acquisition admitted by the test image executor.

    Returns
    -------
    NeuralAcquisition
        The unchanged acquisition.
    """
    path = acquisition.image / _WORKER
    path.unlink()
    os.mkfifo(path, 0o444)
    return acquisition


def _large(acquisition: NeuralAcquisition) -> NeuralAcquisition:
    """Bind a sparse file larger than any admitted image file.

    Parameters
    ----------
    acquisition
        Acquisition admitted by the test image executor.

    Returns
    -------
    NeuralAcquisition
        The acquisition whose binding lists the large file.
    """
    path = acquisition.image / "large.bin"
    with path.open("wb") as stream:
        stream.truncate(_LARGE)
    path.chmod(0o444)
    entry = {"path": "large.bin", "sha256": "0" * 64, "byte_length": _LARGE, "mode": 0o444}
    return rebind_image(acquisition, lambda binding: binding["image"]["files"].append(entry))


def _missing_root(acquisition: NeuralAcquisition) -> NeuralAcquisition:
    """Move the image away from its selected root.

    Parameters
    ----------
    acquisition
        Acquisition admitted by the test image executor.

    Returns
    -------
    NeuralAcquisition
        The unchanged acquisition.
    """
    acquisition.image.rename(acquisition.image.with_name("moved"))
    return acquisition


def _linked_root(acquisition: NeuralAcquisition) -> NeuralAcquisition:
    """Select the image through a link to its directory.

    Parameters
    ----------
    acquisition
        Acquisition admitted by the test image executor.

    Returns
    -------
    NeuralAcquisition
        The acquisition selecting the linked root.
    """
    link = acquisition.image.with_name("linked-image")
    link.symlink_to(acquisition.image)
    return _with_root(acquisition, link)


_TREE: dict[str, tuple[Callable[[NeuralAcquisition], NeuralAcquisition], str | None]] = {
    "missing-root": (_missing_root, _ROOT),
    "relative-root": (lambda acquisition: _with_root(acquisition, Path("image")), _ROOT),
    "linked-root": (_linked_root, _ROOT),
    "extra-file": (_extra_file, _ENTRIES),
    "extra-directory": (_extra_directory, _ENTRIES),
    "unreadable-directory": (_unreadable_directory, _ENTRIES),
    "non-utf8-name": (_non_utf8_name, _ENTRIES),
    "extra-link": (_extra_link, _LINKS),
    "non-utf8-link": (_non_utf8_link, _LINKS),
    "bound-link": (_bound_link, None),
    "mode": (_mode, _FILE),
    "length": (_longer, _FILE),
    "fifo": (_fifo, _FILE),
    "large": (_large, _FILE),
    "bytes": (_changed_bytes, "Checker image file bytes differ from its binding."),
}


@pytest.mark.parametrize("fault", list(_TREE))
def test_image_tree_is_verified_alike(
    acquisition: NeuralAcquisition, tmp_path: Path, fault: str
) -> None:
    """Refuse an image tree that differs from its binding, and run one that matches.

    Parameters
    ----------
    acquisition
        Acquisition admitted by the test image executor.
    tmp_path
        Owned Rust outcome directory.
    fault
        Named image tree change.
    """
    change, message = _TREE[fault]
    changed = change(acquisition)
    python = python_outcome(changed)
    assert_same_outcome(python, rust_outcome(changed, tmp_path / "rust"))
    if message is None:
        assert python["report"]["verification"]["whole"] is True
    else:
        assert python == {"refusal": message}


def _crafted(files: str, modules: str = "[]") -> bytes:
    """Return a checker that leaves its own worker observation and stops.

    Parameters
    ----------
    files
        Python expression for the observed files; ``digest`` and ``raw`` name
        the checker's own bytes.
    modules
        Python expression for the observed modules.

    Returns
    -------
    bytes
        Complete checker program.
    """
    return (
        CHECKER
        + f"""import hashlib, json, os
raw = open(os.path.abspath(__file__), "rb").read()
digest = hashlib.sha256(raw).hexdigest()
observation = {{
    "schema_id": "loop-timing-witness.sc-checker-worker-observation.v1",
    "operation": sys.argv[1][2:],
    "actual_argv": sys.argv,
    "native_returncode": 0,
    "phase": "source",
    "started_ns": 1,
    "completed_ns": 2,
    "elapsed_ns": 1,
    "modules": {modules},
    "files": {files},
}}
open("checker-observation.json", "w").write(json.dumps(observation))
os._exit(0)
"""
    ).encode()


_ENTRY = f'"/{ENTRY}"'
_OBSERVED: dict[str, tuple[bytes, str]] = {
    "relative-and-work-files": (
        _crafted(
            '[{"path": "relative.txt", "sha256": digest, "byte_length": 0},'
            ' {"path": "/work/other.txt", "sha256": digest, "byte_length": 0}]'
        ),
        "did not open its complete admitted source closure",
    ),
    "changed-digest": (
        _crafted(f'[{{"path": {_ENTRY}, "sha256": "0" * 64, "byte_length": len(raw)}}]'),
        "opened a file outside its complete runtime binding",
    ),
    "changed-length": (
        _crafted(f'[{{"path": {_ENTRY}, "sha256": digest, "byte_length": len(raw) + 1}}]'),
        "opened a file outside its complete runtime binding",
    ),
    "live-module": (
        _crafted(
            "[]",
            '[{"name": "json", "path": "/elsewhere.py"},'
            ' {"name": "sc_neurocore_live", "path": "/elsewhere.py"}]',
        ),
        "imported a live or unbound SC source fallback",
    ),
}


@pytest.mark.parametrize("fault", list(_OBSERVED))
def test_image_observation_findings_are_alike(tmp_path: Path, fault: str) -> None:
    """Report the same closure findings for one crafted worker observation.

    Parameters
    ----------
    tmp_path
        Owned acquisition and Rust outcome directories.
    fault
        Named observation fault.
    """
    program, message = _OBSERVED[fault]
    acquisition = build_neural_acquisition(tmp_path / "run", program=program)
    try:
        python = python_outcome(acquisition)
        assert_same_outcome(python, rust_outcome(acquisition, tmp_path / "rust"))
    finally:
        make_writable(tmp_path)
    findings = python["report"]["source_binding"]["findings"]
    assert any(message in finding for finding in findings), findings


def test_image_source_closure_must_be_the_admitted_one(
    acquisition: NeuralAcquisition, tmp_path: Path
) -> None:
    """Report an image whose bound source closure differs from the admitted sources.

    Parameters
    ----------
    acquisition
        Acquisition admitted by the test image executor.
    tmp_path
        Owned Rust outcome directory.
    """
    rebound = rebind_image(acquisition, lambda binding: binding["source_files"].append(_WORKER))
    python = python_outcome(rebound)
    assert_same_outcome(python, rust_outcome(rebound, tmp_path / "rust"))
    findings = python["report"]["source_binding"]["findings"]
    assert "Checker image source closure differs from the admitted sources." in findings


@pytest.mark.parametrize(
    ("target", "syscall", "message"),
    [
        ("/proc/sys/kernel/osrelease", "openat", _HOST),
        (_WORKER, "openat", "Checker image file is unavailable."),
        ("link", "readlink", _BIND),
    ],
)
def test_injected_image_failures_refuse_as_python_does(
    acquisition: NeuralAcquisition, tmp_path: Path, target: str, syscall: str, message: str
) -> None:
    """Refuse a failed kernel read, image file open or link read in the Rust verifier.

    The Python verifier reads the kernel release from the host name service,
    and gives these refusals for any operating-system error opening an image
    file or reading a link; the injected Rust failures must match them.

    Parameters
    ----------
    acquisition
        Acquisition admitted by the test image executor.
    tmp_path
        Owned Rust outcome directory.
    target
        Absolute path, or image-relative name, whose syscall fails.
    syscall
        Failed syscall.
    message
        Expected refusal.
    """
    bound = _bound_link(acquisition)
    path = target if target.startswith("/") else str(bound.image / target)
    injected = (
        "strace",
        "-f",
        "-o",
        "/dev/null",
        "-P",
        path,
        "-e",
        f"trace={syscall}",
        "-e",
        f"inject={syscall}:error=EIO",
    )
    assert rust_outcome(bound, tmp_path / "rust", wrapper=injected) == {"refusal": message}
