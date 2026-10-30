# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual consumer-installed file binding controls

"""Exercise public installation-file bindings with an exact selected worker source."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from loop_timing_witness.neural_checker_installation import (
    CheckerInstalledFile,
    NeuralCheckerInstallation,
)
from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError

_ROOT = Path(__file__).resolve().parents[1]
_WORKER_SHA = "28f2a3d33c3278738b589035f95944800a8a31a58031888783f468b93685e001"


@pytest.fixture
def installed_source(tmp_path: Path) -> CheckerInstalledFile:
    """Bind a real copy of the complete source-owner-selected consumer worker.

    Parameters
    ----------
    tmp_path
        Owned regular source copy, separate from the canonical package.

    Returns
    -------
    CheckerInstalledFile
        Actual installation-file selection, without admitting a source registry entry.
    """
    raw = (_ROOT / "src/loop_timing_witness/neural_checker_worker.py").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == _WORKER_SHA
    assert len(raw) == 4789
    path = tmp_path / "worker.py"
    path.write_bytes(raw)
    return CheckerInstalledFile(
        "loop_timing_witness/neural_checker_worker.py", path, _WORKER_SHA, 4789
    )


@pytest.fixture
def verified_installation() -> NeuralCheckerInstallation:
    """Verify actual tool and worker metadata before testing installation fields.

    Returns
    -------
    NeuralCheckerInstallation
        Direct metadata selection for the running interpreter, actual tracer and
        source package. It is not attached to a source-contract registry entry.
    """
    tracer_path = shutil.which("strace")
    assert tracer_path is not None
    files = []
    for name, path in (
        ("interpreter/python", Path(sys.executable).resolve()),
        ("tracer/strace", Path(tracer_path).resolve()),
    ):
        raw = path.read_bytes()
        files.append(CheckerInstalledFile(name, path, hashlib.sha256(raw).hexdigest(), len(raw)))
    installation = NeuralCheckerInstallation(
        files[0],
        files[1],
        tuple(files),
        (_ROOT / "src",),
        platform.platform(),
        platform.release(),
    )
    installation.verify()
    return installation


def test_original_installed_file_reference_and_complete_verification(
    installed_source: CheckerInstalledFile,
) -> None:
    """Verify exact real source bytes and their portable inventory identity.

    Parameters
    ----------
    installed_source
        Actual selected worker copy with its reviewed source identity.
    """
    assert installed_source.reference() == {
        "path": "loop_timing_witness/neural_checker_worker.py",
        "sha256": _WORKER_SHA,
        "byte_length": 4789,
    }
    installed_source.verify()


@pytest.mark.parametrize(
    "worker", ["__init__.py", "neural_checker_worker.py", "neural_checker_isolation.py"]
)
def test_public_installation_constructor_bounds_actual_worker_sources(
    tmp_path: Path, verified_installation: NeuralCheckerInstallation, worker: str
) -> None:
    """Refuse a real oversized installed worker after a successful construction.

    Parameters
    ----------
    tmp_path
        Owned package copy required to change module-relative installed files.
    verified_installation
        Verified real interpreter, tracer and worker metadata; no source admission.
    worker
        One of the three worker bodies frozen by the public constructor.
    """
    original = _ROOT / "src/loop_timing_witness"
    installed = tmp_path / "installation/loop_timing_witness"
    shutil.copytree(original, installed, ignore=shutil.ignore_patterns("__pycache__"))
    module = "neural_checker_installation.py"
    assert (installed / module).read_bytes() == (original / module).read_bytes()
    payload = json.dumps(
        {
            "files": [
                [item.name, str(item.path), item.sha256, item.byte_length]
                for item in verified_installation.files
            ],
            "import_roots": [str(path) for path in verified_installation.import_roots],
            "baseline_id": verified_installation.baseline_id,
            "kernel_release": verified_installation.kernel_release,
        }
    )
    program = (
        "import json,sys;from pathlib import Path;"
        "sys.path.insert(0,sys.argv[1]);"
        "from loop_timing_witness.neural_checker_installation import "
        "CheckerInstalledFile,NeuralCheckerInstallation;"
        "from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError;"
        "data=json.load(sys.stdin);"
        "files=tuple(CheckerInstalledFile(name,Path(path),sha,size) "
        "for name,path,sha,size in data['files'])\n"
        "try:\n"
        " installation=NeuralCheckerInstallation(files[0],files[1],files,"
        "tuple(Path(p) for p in data['import_roots']),"
        "data['baseline_id'],data['kernel_release'])\n"
        " installation.verify()\n"
        "except NeuralCaptureRefusalError as exc:\n"
        " print(str(exc),file=sys.stderr);raise SystemExit(1)\n"
        "print('installation verified')"
    )
    command = [sys.executable, "-B", "-c", program, str(installed.parent)]
    baseline = subprocess.run(
        command, input=payload, capture_output=True, text=True, timeout=20, check=False
    )
    assert baseline.returncode == 0, baseline.stderr
    assert baseline.stdout == "installation verified\n"
    assert baseline.stderr == ""
    target = installed / worker
    raw = target.read_bytes()
    target.write_bytes(raw + b" " * (1048577 - len(raw)))
    refused = subprocess.run(
        command, input=payload, capture_output=True, text=True, timeout=20, check=False
    )
    assert refused.returncode == 1
    assert refused.stdout == ""
    assert refused.stderr == "Selected checker worker source exceeds its allocation.\n"
    assert (installed / module).read_bytes() == (original / module).read_bytes()


@pytest.mark.parametrize("kind", ["fifo", "directory", "symlink", "missing"])
def test_installed_file_kind_refuses_without_a_writer(
    installed_source: CheckerInstalledFile, tmp_path: Path, kind: str
) -> None:
    """Refuse actual nonregular, absent and final-linked runtime files.

    Parameters
    ----------
    installed_source
        Actual source binding whose file kind is changed.
    tmp_path
        Owned symlink target allocation.
    kind
        Concrete installed file-kind contradiction.
    """
    path = installed_source.path
    raw = path.read_bytes()
    path.unlink()
    if kind == "fifo":
        os.mkfifo(path)
    elif kind == "directory":
        path.mkdir()
    elif kind == "symlink":
        target = tmp_path / "original.py"
        target.write_bytes(raw)
        path.symlink_to(target)
    expected = (
        "Selected checker runtime requires a regular resolved file"
        if kind == "fifo"
        else "Selected checker runtime file is unavailable"
    )
    with pytest.raises(NeuralCaptureRefusalError, match=expected):
        installed_source.verify()


def test_empty_installed_file_requires_its_complete_declared_bytes(tmp_path: Path) -> None:
    """Verify an actual empty file and refuse a subsequently appended byte.

    Parameters
    ----------
    tmp_path
        Owned regular file whose declared zero-length binding is exercised.
    """
    path = tmp_path / "empty.dat"
    path.touch()
    binding = CheckerInstalledFile("empty.dat", path, hashlib.sha256(b"").hexdigest(), 0)
    binding.verify()
    path.write_bytes(b"\x00")
    with pytest.raises(NeuralCaptureRefusalError, match="differs from its reviewed binding"):
        binding.verify()


def test_installed_file_reports_actual_self_memory_read_error() -> None:
    """Refuse the real procfs read at this process's unmapped address zero."""
    binding = CheckerInstalledFile(
        "procfs-self-memory", Path("/proc/self/mem"), hashlib.sha256(b"").hexdigest(), 0
    )
    with pytest.raises(
        NeuralCaptureRefusalError, match="Selected checker runtime file is unavailable"
    ) as error:
        binding.verify()
    cause = error.value.__cause__
    assert isinstance(cause, OSError)
    assert cause.errno == errno.EIO


@pytest.mark.parametrize("change", ["same-length", "truncated", "extra"])
def test_changed_complete_installed_bytes_refuse(
    installed_source: CheckerInstalledFile, change: str
) -> None:
    """Bind the whole source length and digest instead of a readable prefix.

    Parameters
    ----------
    installed_source
        Real reviewed source copy.
    change
        Actual complete-byte or size contradiction.
    """
    raw = installed_source.path.read_bytes()
    if change == "same-length":
        altered = raw[:-1] + b" "
    elif change == "truncated":
        altered = raw[:-1]
    else:
        altered = raw + b"\n"
    installed_source.path.write_bytes(altered)
    with pytest.raises(NeuralCaptureRefusalError, match="differs from its reviewed binding"):
        installed_source.verify()


@pytest.mark.parametrize("length", [True, 1.0, -1, 268435457])
def test_installed_file_allocation_requires_a_finite_exact_integer(
    installed_source: CheckerInstalledFile, length: object
) -> None:
    """Refuse non-integer or unsupported consumer metadata before file reading.

    Parameters
    ----------
    installed_source
        Actual worker source whose trusted binding is deliberately contradicted.
    length
        Unsupported public dataclass field supplied by this negative caller.
    """
    client = (
        "import json\n"
        "import sys\n"
        "from pathlib import Path\n"
        "from loop_timing_witness.neural_checker_installation import CheckerInstalledFile\n"
        "from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError\n"
        "try:\n"
        " binding = CheckerInstalledFile(\n"
        "  'loop_timing_witness/neural_checker_worker.py',\n"
        "  Path(sys.argv[1]), sys.argv[2], json.loads(sys.argv[3]))\n"
        " binding.verify()\n"
        "except NeuralCaptureRefusalError as error:\n"
        " print(error)\n"
        " sys.exit(0)\n"
        "sys.exit(2)\n"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            client,
            str(installed_source.path),
            installed_source.sha256,
            json.dumps(length),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert result.returncode == 0
    assert "exceeds its allocation" in result.stdout
    assert result.stderr == ""


@pytest.mark.parametrize(
    "kind", ["baseline", "kernel", "empty", "excess", "names", "paths", "interpreter", "tracer"]
)
def test_actual_selected_installation_metadata_contradictions_refuse(
    kind: str, verified_installation: NeuralCheckerInstallation
) -> None:
    """Refuse invalid consumer metadata derived from a real verified installation.

    Parameters
    ----------
    kind
        Deliberate contradiction of the actual selected platform or complete inventory.
    verified_installation
        Running interpreter, actual tracer and source package.
    """
    original = verified_installation
    if kind == "baseline":
        selected = replace(original, baseline_id="")
    elif kind == "kernel":
        selected = replace(original, kernel_release="unsupported-kernel")
    elif kind == "empty":
        selected = replace(original, files=())
    elif kind == "excess":
        selected = replace(original, files=(original.files[0],) * 4097)
    elif kind == "names":
        duplicate = replace(original.files[1], name=original.files[0].name)
        selected = replace(original, files=(original.files[0], duplicate, *original.files[2:]))
    elif kind == "paths":
        duplicate = replace(original.files[1], path=original.files[0].path)
        selected = replace(original, files=(original.files[0], duplicate, *original.files[2:]))
    elif kind == "interpreter":
        selected = replace(original, interpreter=replace(original.interpreter, name="unlisted"))
    else:
        selected = replace(original, tracer=replace(original.tracer, name="unlisted"))
    with pytest.raises(
        NeuralCaptureRefusalError,
        match="Selected checker runtime inventory or platform baseline differs",
    ):
        selected.verify()


@pytest.mark.parametrize("kind", ["empty", "missing", "symlink"])
def test_installation_import_roots_require_actual_resolved_directories(
    tmp_path: Path, kind: str, verified_installation: NeuralCheckerInstallation
) -> None:
    """Refuse real absent or linked consumer import roots without running source code.

    Parameters
    ----------
    tmp_path
        Owned root-kind contradiction.
    kind
        Actual empty selection, missing directory or final symlink.
    verified_installation
        Actual tool/worker metadata whose intact bindings pass before root damage.
    """
    root = tmp_path / "import-root"
    roots: tuple[Path, ...] = (root,)
    if kind == "empty":
        roots = ()
    elif kind == "symlink":
        target = tmp_path / "resolved-root"
        target.mkdir()
        root.symlink_to(target, target_is_directory=True)
    selected = replace(verified_installation, import_roots=roots)
    with pytest.raises(
        NeuralCaptureRefusalError, match="Selected checker runtime import roots are unavailable"
    ):
        selected.verify()


def test_excessive_worker_source_refuses_installation(tmp_path: Path) -> None:
    """Refuse an installation whose package worker source exceeds its allocation.

    Parameters
    ----------
    tmp_path
        Owned package copy with an oversized worker source.
    """
    installed = tmp_path / "installation/loop_timing_witness"
    shutil.copytree(
        _ROOT / "src/loop_timing_witness", installed, ignore=shutil.ignore_patterns("__pycache__")
    )
    worker = installed / "neural_checker_worker.py"
    worker.write_bytes(worker.read_bytes() + b"#" * 1048576)
    client = (
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from loop_timing_witness.neural_checker_installation import (\n"
        "    CheckerInstalledFile, NeuralCheckerInstallation)\n"
        "from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError\n"
        "item = CheckerInstalledFile('interpreter', Path(sys.executable), '0' * 64, 0)\n"
        "try:\n"
        "    NeuralCheckerInstallation(item, item, (item,), (Path('.'),), 'id', 'kernel')\n"
        "except NeuralCaptureRefusalError as error:\n"
        "    print(error)\n"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", client, str(installed.parent)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "worker source exceeds its allocation" in result.stdout
