# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual checker opened-file closure

"""Reconcile successful traced file opens with the complete source/runtime selection."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import TYPE_CHECKING

from .neural_event_stream import NeuralCaptureRefusalError

if TYPE_CHECKING:
    from .neural_checker_execution import CheckerInvocation
    from .neural_checker_installation import NeuralCheckerInstallation

_OPEN = re.compile(
    r'^(?:\d+\s+)?openat(?:2)?\(([^,]+), ("(?:[^"\\]|\\.)*"), (.*?)\)\s+=\s+(\d+)(?:<.*>)?\s*$'
)
_DYNAMIC_READS = frozenset({"/proc/self/maps", "/sys/devices/system/cpu/possible", "/dev/urandom"})


def checker_opened_files(raw: bytes, directory: Path) -> frozenset[Path]:
    """Decode complete successful openat/openat2 observations without executing trace data.

    Parameters
    ----------
    raw
        Complete bounded strace output with hex strings and descriptor path decoding.
    directory
        Actual fixed working directory of the checker process.

    Returns
    -------
    frozenset[Path]
        Resolved successfully opened regular-file paths, retaining every dependency.

    Raises
    ------
    NeuralCaptureRefusalError
        If a successful relative open cannot be resolved or trace records are partial.
    """
    paths = set()
    for line in raw.decode("utf-8").splitlines():
        if "<unfinished ...>" in line or " resumed>" in line:
            message = "Checker file trace contains an incomplete open observation."
            raise NeuralCaptureRefusalError(message)
        match = _OPEN.fullmatch(line)
        if match is None:
            continue
        descriptor, encoded, flags, _ = match.groups()
        name = ast.literal_eval("b" + encoded).decode("utf-8")
        if name in _DYNAMIC_READS or "O_DIRECTORY" in flags:
            continue
        path = Path(name)
        if not path.is_absolute():
            if descriptor.startswith("AT_FDCWD"):
                path = directory / path
            else:
                base = re.fullmatch(r"\d+<([^>]+)>", descriptor)
                if base is None:
                    message = "Checker file trace has an unbound relative descriptor."
                    raise NeuralCaptureRefusalError(message)
                path = Path(base[1]) / path
        path = path.resolve(strict=True)
        if path.is_file():
            paths.add(path)
    return frozenset(paths)


def checker_trace_findings(
    invocation: CheckerInvocation,
    directory: Path,
    source_files: frozenset[Path],
    installation: NeuralCheckerInstallation,
) -> tuple[str, ...]:
    """Compare actual opened files and loaded SC modules with the complete reviewed closure.

    Parameters
    ----------
    invocation
        Complete actual process result and bounded original trace.
    directory
        Owned invocation working directory.
    source_files
        Exact frozen copies of every source-owned checker dependency.
    installation
        Selected interpreter, runtime, worker and explicit platform baseline.

    Returns
    -------
    tuple[str, ...]
        Independent source/runtime closure failures; no absence is inferred as success.
    """
    if not invocation.trace or invocation.observation is None:
        return ("Actual source checker opened-file observation is unavailable.",)
    opened = checker_opened_files(invocation.trace, directory)
    runtime = {item.path.resolve() for item in (*installation.files, *installation.worker_files())}
    data = {
        directory / name
        for name in (
            "stimuli.txt",
            "results_expected.txt",
            "results_verilog.txt",
            "checker-observation.json",
        )
    }
    failures = []
    if not source_files.issubset(opened):
        failures.append("Actual source checker did not open its complete admitted source closure.")
    if opened - source_files - runtime - data:
        failures.append("Actual source checker opened a file outside its complete runtime binding.")
    modules = invocation.observation["modules"]
    if any(
        item["name"].startswith("sc_neurocore") and Path(item["path"]) not in source_files
        for item in modules
    ):
        failures.append("Actual source checker imported a live or unbound SC source fallback.")
    return tuple(failures)
