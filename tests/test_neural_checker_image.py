# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — immutable checker image executor tests

"""Exercise image verification, real launcher processes and closure findings."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import signal
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from loop_timing_witness.manifest_io import canonical_json_bytes
from loop_timing_witness.neural_checker_execution import CheckerInvocation
from loop_timing_witness.neural_checker_image import IMAGE_EXECUTOR_SCHEMA, ImageCheckerExecutor
from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError
from loop_timing_witness.neural_run_selected_profile import (
    IMAGE_BINDING_VARIABLE,
    IMAGE_ROOT_VARIABLE,
    image_neural_profile,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import FrameType

_DATA = Path(__file__).resolve().parents[1] / "src/loop_timing_witness/data"
_RUNTIME = (_DATA / "neural-image-checker-runtime.json").read_bytes()
_WORKER = """
import json, os, sys, time
root, work, operation = sys.argv[1:4]
print("operation", operation, os.environ["TMPDIR"] == work)
if operation == "check":
    time.sleep(30)
if work.endswith("tamper"):
    open(os.path.join(root, "planted"), "w").close()
json.dump(dict(phase="source", files=[], modules=[]), open("checker-observation.json", "w"))
"""


def _sha(raw: bytes) -> str:
    """Return the SHA-256 hex digest.

    Parameters
    ----------
    raw
        Bytes to hash.

    Returns
    -------
    str
        Lowercase digest.
    """
    return hashlib.sha256(raw).hexdigest()


def _image(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    """Build a small real image tree and its matching inventory.

    Parameters
    ----------
    tmp_path
        Test allocation.

    Returns
    -------
    tuple[Path, dict[str, Any]]
        Image root and the bound inventory.
    """
    root = tmp_path / "image"
    (root / "usr/bin").mkdir(parents=True)
    (root / "empty").mkdir()
    (root / "src").mkdir()
    bodies = {"usr/bin/tool": (b"tool", 0o555), "src/model.py": (b"model = 1\n", 0o444)}
    files = []
    for name, (body, mode) in bodies.items():
        path = root / name
        path.write_bytes(body)
        path.chmod(mode)
        files.append({"path": name, "sha256": _sha(body), "byte_length": len(body), "mode": mode})
    (root / "bin").symlink_to("usr/bin")
    inventory = {
        "files": files,
        "directories": ["empty", "src", "usr", "usr/bin"],
        "symlinks": [{"path": "bin", "target": "usr/bin"}],
    }
    return root, inventory


def _binding(tmp_path: Path, **changes: object) -> tuple[Path, bytes]:
    """Return an image root and a closed binding for this real host.

    Parameters
    ----------
    tmp_path
        Test allocation.
    **changes
        Top-level binding replacements.

    Returns
    -------
    tuple[Path, bytes]
        Image root and canonical binding bytes.
    """
    root, inventory = _image(tmp_path)
    host_file = tmp_path / "launcher"
    host_file.write_bytes(b"launcher")
    value: dict[str, Any] = {
        "schema_id": IMAGE_EXECUTOR_SCHEMA,
        "supplier": {},
        "historical_contracts": {},
        "command": [
            sys.executable,
            "-I",
            "-c",
            _WORKER,
            "{image_root}",
            "{work_directory}",
            "{operation}",
        ],
        "bootstrap_environment": {"PATH": "/usr/bin:/bin", "TMPDIR": "{work_directory}"},
        "deadline_seconds": 1,
        "host_boundary": {
            "system": platform.system(),
            "machine": platform.machine(),
            "kernel_release": platform.release(),
            "uid": os.getuid(),
            "gid": os.getgid(),
            "files": [{"path": str(host_file), "sha256": _sha(b"launcher"), "byte_length": 8}],
            "absent_paths": [str(tmp_path / "absent")],
        },
        "image": inventory,
        "source_files": ["src/model.py"],
        "worker_files": ["usr/bin/tool"],
    }
    value.update(changes)
    return root, canonical_json_bytes(value)


def _executor(tmp_path: Path, **changes: object) -> ImageCheckerExecutor:
    """Construct an executor over a fresh real image.

    Parameters
    ----------
    tmp_path
        Test allocation.
    **changes
        Top-level binding replacements.

    Returns
    -------
    ImageCheckerExecutor
        Executor bound to the test image and the real historical runtime.
    """
    root, raw = _binding(tmp_path, **changes)
    return ImageCheckerExecutor(root, raw, _RUNTIME)


def test_verified_image_exposes_historical_runtime(tmp_path: Path) -> None:
    """Verify a matching image and return the exact historical declarations.

    Parameters
    ----------
    tmp_path
        Test allocation.
    """
    executor = _executor(tmp_path)
    executor.verify()
    assert executor.contract_bytes() == _RUNTIME
    references = executor.runtime_references()
    runtime = json.loads(_RUNTIME)
    assert len(references) == len(runtime["files"]) + len(runtime["worker_sources"])
    assert references["loop_timing_witness/neural_checker_worker.py"]["sha256"] == (
        "28f2a3d33c3278738b589035f95944800a8a31a58031888783f468b93685e001"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"schema_id": "other"},
        {"command": []},
        {"command": "not-a-list"},
        {"command": [sys.executable, "--root={image_root}"]},
        {"bootstrap_environment": {"TMPDIR": "x{work_directory}"}},
        {"bootstrap_environment": []},
        {"deadline_seconds": 1.5},
        {"deadline_seconds": 0},
        {"deadline_seconds": 301},
        {"source_files": []},
        {"worker_files": []},
        {"extra": True},
    ],
)
def test_binding_must_be_closed(tmp_path: Path, change: dict[str, Any]) -> None:
    """Refuse bindings outside the closed reviewed form before any use.

    Parameters
    ----------
    tmp_path
        Test allocation.
    change
        One contradiction of the closed form.
    """
    with pytest.raises(NeuralCaptureRefusalError, match="closed reviewed form"):
        _executor(tmp_path, **change)


def _replace_model(root: Path, body: bytes | None, mode: int) -> None:
    """Replace the bound model file by new bytes, a FIFO or an unreadable file.

    Parameters
    ----------
    root
        Image root.
    body
        Replacement bytes, or ``None`` for a FIFO.
    mode
        Final permission bits.
    """
    path = root / "src/model.py"
    path.unlink()
    if body is None:
        os.mkfifo(path, mode)
    else:
        path.write_bytes(body)
        path.chmod(mode)


def _relink(root: Path) -> None:
    """Point the bound link at another target.

    Parameters
    ----------
    root
        Image root.
    """
    (root / "bin").unlink()
    (root / "bin").symlink_to("usr")


_IMAGE_MUTATIONS: dict[str, tuple[Callable[[Path], object], str]] = {
    "extra-file": (lambda root: (root / "empty/extra").write_bytes(b""), "entries differ"),
    "missing-directory": (lambda root: (root / "empty").rmdir(), "entries differ"),
    "link-target": (_relink, "links differ"),
    "mode": (lambda root: (root / "src/model.py").chmod(0o644), "type, mode or length"),
    "bytes": (lambda root: _replace_model(root, b"model = 2\n", 0o444), "bytes differ"),
    "fifo": (lambda root: _replace_model(root, None, 0o444), "type, mode or length"),
    "unreadable": (lambda root: _replace_model(root, b"model = 1\n", 0o000), "unavailable"),
}


@pytest.mark.parametrize("mutation", sorted(_IMAGE_MUTATIONS))
def test_image_contradictions_refuse(tmp_path: Path, mutation: str) -> None:
    """Refuse every image inventory, link, mode and byte contradiction.

    Parameters
    ----------
    tmp_path
        Test allocation.
    mutation
        Real filesystem contradiction.
    """
    root, raw = _binding(tmp_path)
    change, message = _IMAGE_MUTATIONS[mutation]
    change(root)
    with pytest.raises(NeuralCaptureRefusalError, match=message):
        ImageCheckerExecutor(root, raw, _RUNTIME).verify()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("kernel", "platform or account"),
        ("host-file", "differs from its reviewed binding"),
        ("absent", "requires absent"),
        ("relative-root", "absolute real directory"),
        ("symlink-root", "absolute real directory"),
        ("missing-root", "absolute real directory"),
    ],
)
def test_host_and_root_contradictions_refuse(tmp_path: Path, mutation: str, message: str) -> None:
    """Refuse every host boundary and image root contradiction.

    Parameters
    ----------
    tmp_path
        Test allocation.
    mutation
        Real host or root contradiction.
    message
        Expected authored refusal fragment.
    """
    root, raw = _binding(tmp_path)
    value = json.loads(raw)
    if mutation == "kernel":
        value["host_boundary"]["kernel_release"] = "0.0.0-other"
    elif mutation == "host-file":
        (tmp_path / "launcher").write_bytes(b"replaced")
    elif mutation == "absent":
        (tmp_path / "absent").mkdir()
    elif mutation == "relative-root":
        root = Path("image")
    elif mutation == "symlink-root":
        (tmp_path / "alias").symlink_to(root)
        root = tmp_path / "alias"
    else:
        root = tmp_path / "missing"
    executor = ImageCheckerExecutor(root, canonical_json_bytes(value), _RUNTIME)
    with pytest.raises(NeuralCaptureRefusalError, match=message):
        executor.verify()


def test_real_launcher_substitutes_only_whole_placeholders(tmp_path: Path) -> None:
    """Run the bound command and record status, logs, observation and boundary.

    Parameters
    ----------
    tmp_path
        Test allocation.
    """
    executor = _executor(tmp_path)
    work = tmp_path / "generate"
    work.mkdir()
    actual = executor.invoke("generate", work)
    assert actual.returncode == 0
    assert not actual.interrupted
    assert actual.command[-3:] == (str(tmp_path / "image"), str(work), "generate")
    assert actual.stdout == b"operation generate True\n"
    assert actual.stderr == b""
    assert actual.observation == {"phase": "source", "files": [], "modules": []}
    assert actual.completed_ns >= actual.started_ns
    assert actual.elapsed_ns > 0
    boundary = json.loads(actual.trace)
    assert boundary["image_and_host_boundary"] == "verified-before-and-after"
    assert boundary["environment"] == {"PATH": "/usr/bin:/bin", "TMPDIR": str(work)}
    assert boundary["executor_binding_sha256"] == _sha(executor.binding_bytes)
    assert (tmp_path / "generate.stdout").is_file()


def test_unsupported_operation_refuses(tmp_path: Path) -> None:
    """Refuse any operation other than the two fixed ones.

    Parameters
    ----------
    tmp_path
        Test allocation.
    """
    with pytest.raises(NeuralCaptureRefusalError, match="Unsupported fixed"):
        _executor(tmp_path).invoke("--help", tmp_path)


def test_deadline_stops_and_reaps_the_group(tmp_path: Path) -> None:
    """Stop an operation at its deadline without restarting it.

    Parameters
    ----------
    tmp_path
        Test allocation.
    """
    work = tmp_path / "check"
    work.mkdir()
    actual = _executor(tmp_path).invoke("check", work)
    assert actual.interrupted
    assert actual.returncode == -signal.SIGKILL
    assert actual.observation is None


def test_interrupted_parent_reaps_the_group(tmp_path: Path) -> None:
    """Reap the owned group when the waiting parent is interrupted.

    Parameters
    ----------
    tmp_path
        Test allocation.
    """
    work = tmp_path / "check"
    work.mkdir()
    executor = _executor(tmp_path, deadline_seconds=60)

    def interrupt(number: int, frame: FrameType | None) -> None:
        """Raise a parent interruption from the alarm.

        Parameters
        ----------
        number, frame
            Signal details.

        Raises
        ------
        KeyboardInterrupt
            Always.
        """
        del number, frame
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGALRM, interrupt)
    try:
        signal.setitimer(signal.ITIMER_REAL, 0.5)
        with pytest.raises(KeyboardInterrupt):
            executor.invoke("check", work)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def test_image_changed_by_the_operation_refuses(tmp_path: Path) -> None:
    """Refuse an operation that changed the image it ran from.

    Parameters
    ----------
    tmp_path
        Test allocation.
    """
    work = tmp_path / "tamper"
    work.mkdir()
    with pytest.raises(NeuralCaptureRefusalError, match="entries differ"):
        _executor(tmp_path).invoke("generate", work)


def test_oversized_log_refuses(tmp_path: Path) -> None:
    """Refuse a launcher log beyond its allocation.

    Parameters
    ----------
    tmp_path
        Test allocation.
    """
    command = [sys.executable, "-I", "-c", "import sys; sys.stdout.write('x' * 1048577)"]
    work = tmp_path / "generate"
    work.mkdir()
    with pytest.raises(NeuralCaptureRefusalError, match="exceeds its allocation"):
        _executor(tmp_path, command=command).invoke("generate", work)


def _invocation(observation: dict[str, Any] | None) -> CheckerInvocation:
    """Return a completed invocation carrying one worker observation.

    Parameters
    ----------
    observation
        Worker observation under test.

    Returns
    -------
    CheckerInvocation
        Completed invocation.
    """
    return CheckerInvocation((), 0, 0, 1, 1, b"", b"", b"{}", observation, interrupted=False)


def _record(path: str, body: bytes) -> dict[str, Any]:
    """Return one observed file record.

    Parameters
    ----------
    path
        Namespace path.
    body
        Observed bytes.

    Returns
    -------
    dict[str, Any]
        Worker file record.
    """
    return {"path": path, "sha256": _sha(body), "byte_length": len(body)}


@pytest.mark.parametrize(
    ("observation", "digests", "expected"),
    [
        (
            {
                "files": [
                    _record("/src/model.py", b"model = 1\n"),
                    _record("/usr/bin/tool", b"tool"),
                    _record("/work/stimuli.txt", b"anything"),
                ],
                "modules": [
                    {"name": "sc_neurocore", "path": "/src/model.py"},
                    {"name": "json", "path": "/usr/bin/tool"},
                ],
            },
            [_sha(b"model = 1\n")],
            (),
        ),
        (None, [], ("Actual source checker opened-file observation is unavailable.",)),
        ({"files": "x"}, [], ("Actual source checker opened-file observation is unavailable.",)),
        (
            {"files": [{"path": "/src/model.py"}]},
            [],
            ("Actual source checker opened-file observation is unavailable.",),
        ),
        (
            {
                "files": [
                    _record("/src/model.py", b"model = 1\n"),
                    _record("/work/other.txt", b"x"),
                    _record("relative", b"x"),
                    _record("/usr/bin/tool", b"changed"),
                ],
                "modules": [{"name": "sc_neurocore.live", "path": "/elsewhere.py"}],
            },
            [_sha(b"other")],
            (
                "Checker image source closure differs from the admitted sources.",
                "Actual source checker opened a file outside its complete runtime binding.",
                "Actual source checker imported a live or unbound SC source fallback.",
            ),
        ),
        (
            {"files": [_record("/usr/bin/tool", b"tool")], "modules": "x"},
            [_sha(b"model = 1\n")],
            (
                "Actual source checker did not open its complete admitted source closure.",
                "Actual source checker imported a live or unbound SC source fallback.",
            ),
        ),
        (
            {"files": [_record("/src/model.py", b"model = 1\n")], "modules": [{"name": 1}]},
            [_sha(b"model = 1\n")],
            ("Actual source checker imported a live or unbound SC source fallback.",),
        ),
    ],
)
def test_closure_findings(
    tmp_path: Path,
    observation: dict[str, Any] | None,
    digests: list[str],
    expected: tuple[str, ...],
) -> None:
    """Report each independent closure failure without inferring success.

    Parameters
    ----------
    tmp_path
        Test allocation.
    observation
        Worker observation under test.
    digests
        Admitted source digests.
    expected
        Exact ordered findings.
    """
    assert _executor(tmp_path).closure_findings(_invocation(observation), digests) == expected


def test_image_profile_requires_operator_binding_and_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refuse the image registration without a reviewed operator binding.

    The reviewed binding names host files and is never packaged, so an
    unreviewed binding is refused before the image directory is consulted.

    Parameters
    ----------
    tmp_path
        Owned unreviewed binding file.
    monkeypatch
        Environment isolation.
    """
    monkeypatch.setenv(IMAGE_ROOT_VARIABLE, "/nonexistent/image")
    monkeypatch.delenv(IMAGE_BINDING_VARIABLE, raising=False)
    with pytest.raises(NeuralCaptureRefusalError, match="No immutable checker image binding"):
        image_neural_profile()
    monkeypatch.setenv(IMAGE_BINDING_VARIABLE, "relative/binding.json")
    with pytest.raises(NeuralCaptureRefusalError, match="No immutable checker image binding"):
        image_neural_profile()
    unreviewed = tmp_path / "binding.json"
    unreviewed.write_bytes(b"{}")
    monkeypatch.setenv(IMAGE_BINDING_VARIABLE, str(unreviewed))
    with pytest.raises(NeuralCaptureRefusalError, match="differs from its reviewed binding"):
        image_neural_profile()
