# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — traced host checker opened-file closure

"""Interpret traced open calls and compare them with the reviewed closure."""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from loop_timing_witness.neural_checker_execution import CheckerInvocation
from loop_timing_witness.neural_checker_installation import (
    CheckerInstalledFile,
    NeuralCheckerInstallation,
)
from loop_timing_witness.neural_checker_trace import checker_opened_files, checker_trace_findings
from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError

_CORPUS: dict[str, Any] = json.loads(
    (
        Path(__file__).resolve().parents[1] / "analysis/rust/tests/data/neural-checker-traces.json"
    ).read_text(encoding="utf-8")
)


def _installation(root: Path) -> NeuralCheckerInstallation:
    """Select the running interpreter and the actual tracer.

    Parameters
    ----------
    root
        Existing import root.

    Returns
    -------
    NeuralCheckerInstallation
        Minimal real host installation.
    """
    tracer = shutil.which("strace")
    assert tracer is not None
    files = []
    for name, path in (
        ("interpreter/python", Path(sys.executable).resolve()),
        ("tracer/strace", Path(tracer).resolve()),
    ):
        raw = path.read_bytes()
        files.append(CheckerInstalledFile(name, path, hashlib.sha256(raw).hexdigest(), len(raw)))
    return NeuralCheckerInstallation(
        files[0], files[1], tuple(files), (root,), platform.platform(), platform.release()
    )


def _open(path: Path | str, descriptor: str = "AT_FDCWD", flags: str = "O_RDONLY") -> str:
    """Return one successful traced open line.

    Parameters
    ----------
    path
        Opened name as the program passed it.
    descriptor
        Directory descriptor field.
    flags
        Open flags field.

    Returns
    -------
    str
        Trace line.
    """
    return f'123 openat({descriptor}, "{path}", {flags}) = 3\n'


def _invocation(trace: str, observation: dict[str, Any] | None) -> CheckerInvocation:
    """Return a completed invocation with the given trace and observation.

    Parameters
    ----------
    trace
        Original trace text.
    observation
        Worker observation.

    Returns
    -------
    CheckerInvocation
        Completed invocation record.
    """
    return CheckerInvocation(
        ("python",), 0, 1, 2, 1, b"", b"", trace.encode(), observation, interrupted=False
    )


def test_opened_files_resolve_relative_names_and_skip_dynamic_reads(tmp_path: Path) -> None:
    """Resolve relative and descriptor-based names; skip directories and dynamic reads.

    Parameters
    ----------
    tmp_path
        Owned files named by the trace.
    """
    base = tmp_path / "base"
    base.mkdir()
    (base / "inner.py").write_bytes(b"")
    (tmp_path / "local.txt").write_bytes(b"")
    absolute = tmp_path / "absolute.py"
    absolute.write_bytes(b"")
    trace = "".join(
        [
            _open(absolute),
            _open("local.txt"),
            _open("inner.py", descriptor=f"5<{base}>"),
            _open("/dev/urandom"),
            _open(tmp_path, flags="O_RDONLY|O_DIRECTORY"),
            _open(base),
            '123 execve("/usr/bin/true", [], []) = 0\n',
        ]
    )
    opened = checker_opened_files(trace.encode(), tmp_path)
    assert opened == {absolute, tmp_path / "local.txt", base / "inner.py"}


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ('123 openat(AT_FDCWD, "a", O_RDONLY <unfinished ...>\n', "incomplete open"),
        ("123 <... openat resumed>) = 3\n", "incomplete open"),
        (_open("relative.txt", descriptor="7"), "unbound relative descriptor"),
    ],
)
def test_ambiguous_trace_lines_refuse(tmp_path: Path, line: str, message: str) -> None:
    """Refuse interrupted observations and relative names without a bound base.

    Parameters
    ----------
    tmp_path
        Run directory.
    line
        Ambiguous trace line.
    message
        Expected refusal fragment.
    """
    with pytest.raises(NeuralCaptureRefusalError, match=message):
        checker_opened_files(line.encode(), tmp_path)


def test_trace_findings_compare_sources_runtime_data_and_modules(tmp_path: Path) -> None:
    """Report each independent closure difference of one traced invocation.

    Parameters
    ----------
    tmp_path
        Run directory with source, data and outside files.
    """
    installation = _installation(tmp_path)
    source = tmp_path / "model.py"
    missing = tmp_path / "unopened.py"
    outside = tmp_path / "outside.py"
    data = tmp_path / "stimuli.txt"
    for path in (source, missing, outside, data):
        path.write_bytes(b"")
    sources = frozenset({source})
    observation: dict[str, Any] = {"modules": [{"name": "sc_neurocore.model", "path": str(source)}]}
    runtime = installation.interpreter.path
    clean = _invocation(_open(source) + _open(data) + _open(runtime), observation)
    assert checker_trace_findings(clean, tmp_path, sources, installation) == ()
    fallback = {"modules": [{"name": "sc_neurocore.live", "path": str(outside)}]}
    damaged = _invocation(_open(outside), fallback)
    assert checker_trace_findings(damaged, tmp_path, sources | {missing}, installation) == (
        "Actual source checker did not open its complete admitted source closure.",
        "Actual source checker opened a file outside its complete runtime binding.",
        "Actual source checker imported a live or unbound SC source fallback.",
    )


@pytest.mark.parametrize(("trace", "observation"), [("", {"modules": []}), (_open("x"), None)])
def test_unavailable_trace_or_observation_is_a_finding(
    tmp_path: Path, trace: str, observation: dict[str, Any] | None
) -> None:
    """Report an absent trace or worker observation instead of an empty closure.

    Parameters
    ----------
    tmp_path
        Run directory.
    trace
        Original trace text.
    observation
        Worker observation.
    """
    findings = checker_trace_findings(
        _invocation(trace, observation), tmp_path, frozenset(), _installation(tmp_path)
    )
    assert findings == ("Actual source checker opened-file observation is unavailable.",)


@pytest.mark.parametrize("case", _CORPUS["cases"], ids=[case["name"] for case in _CORPUS["cases"]])
def test_shared_trace_corpus_reads_alike(tmp_path: Path, case: dict[str, Any]) -> None:
    """Read each shared trace case exactly as the Rust verifier's unit test does.

    Parameters
    ----------
    tmp_path
        Working directory holding the corpus files.
    case
        Trace lines with their opened files or refusal.
    """
    root = tmp_path.resolve()
    for name in _CORPUS["files"]:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(b"")
    escaped = "".join(f"\\x{byte:02x}" for byte in str(root).encode())
    text = "".join(
        line.replace("{root_hex}", escaped).replace("{root}", str(root)) + "\n"
        for line in case["lines"]
    )
    raw = text.encode() + (b"\xff\n" if case.get("invalid_utf8") else b"")
    if "refusal" in case:
        with pytest.raises(NeuralCaptureRefusalError) as refused:
            checker_opened_files(raw, root)
        assert str(refused.value) == case["refusal"]
    else:
        assert checker_opened_files(raw, root) == {root / name for name in case["opened"]}
