# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual checker opened-file closure

"""Reconcile successful traced file opens with the complete source/runtime selection."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from .neural_event_stream import NeuralCaptureRefusalError

if TYPE_CHECKING:
    from .neural_checker_execution import CheckerInvocation
    from .neural_checker_installation import NeuralCheckerInstallation

_OPEN = re.compile(
    r'^(?:\d+\s+)?openat(?:2)?\(([^,]+), ("(?:[^"\\]|\\.)*"), (.*?)\)\s+=\s+(\d+)(?:<.*>)?\s*$',
    re.ASCII,
)
_BASE = re.compile(r"\d+<([^>]+)>", re.ASCII)
_PIECE = re.compile(r"\\x([0-9a-fA-F]{2})|([^\\])")
_DYNAMIC_READS = frozenset({"/proc/self/maps", "/sys/devices/system/cpu/possible", "/dev/urandom"})


def _quoted_path(encoded: str) -> str:
    """Decode one quoted trace path of plain characters and hexadecimal byte escapes.

    Parameters
    ----------
    encoded
        Quoted path field, including both quotes.

    Returns
    -------
    str
        Exact UTF-8 path.

    Raises
    ------
    NeuralCaptureRefusalError
        If another escape occurs or the decoded bytes are not UTF-8.
    """
    content = encoded[1:-1]
    decoded = bytearray()
    index = 0
    while index < len(content):
        piece = _PIECE.match(content, index)
        if piece is None:
            message = "Checker file trace has an invalid quoted path."
            raise NeuralCaptureRefusalError(message)
        escaped, plain = piece.groups()
        decoded += bytes.fromhex(escaped) if plain is None else plain.encode()
        index = piece.end()
    try:
        return decoded.decode("utf-8")
    except UnicodeDecodeError as exc:
        message = "Checker observed path requires exact UTF-8."
        raise NeuralCaptureRefusalError(message) from exc


def _opened_path(descriptor: str, name: str, directory: Path) -> Path:
    """Resolve one successfully opened name against its directory descriptor.

    Parameters
    ----------
    descriptor
        Directory descriptor field, ``AT_FDCWD`` or ``N<path>``.
    name
        Decoded opened name.
    directory
        Actual fixed working directory of the checker process.

    Returns
    -------
    Path
        Resolved existing path.

    Raises
    ------
    NeuralCaptureRefusalError
        If a relative name has no bound base or the path does not exist.
    """
    path = Path(name)
    if not path.is_absolute():
        if descriptor.startswith("AT_FDCWD"):
            path = directory / path
        else:
            base = _BASE.fullmatch(descriptor)
            if base is None:
                message = "Checker file trace has an unbound relative descriptor."
                raise NeuralCaptureRefusalError(message)
            path = Path(base[1]) / path
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        message = "Actual checker observed file is unavailable."
        raise NeuralCaptureRefusalError(message) from exc


def checker_opened_files(raw: bytes, directory: Path) -> frozenset[Path]:
    """Decode complete successful openat/openat2 observations without executing trace data.

    Lines end only at a line feed. A record is
    ``[PID ]openat[2](BASE, "NAME", FLAGS) = FD[<...>]`` with ASCII digits and
    whitespace; any other line, including a failed open, is not an observation.
    The name holds plain characters and hexadecimal byte escapes.

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
        If the trace or a name is not exact UTF-8, a name has another escape, a
        relative name has no bound base, an opened file is unavailable, or a
        record is partial.
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        message = "Checker file trace requires exact UTF-8."
        raise NeuralCaptureRefusalError(message) from exc
    paths = set()
    for line in text.split("\n"):
        if "<unfinished ...>" in line or " resumed>" in line:
            message = "Checker file trace contains an incomplete open observation."
            raise NeuralCaptureRefusalError(message)
        match = _OPEN.fullmatch(line)
        if match is None:
            continue
        descriptor, encoded, flags, _ = match.groups()
        name = _quoted_path(encoded)
        if name in _DYNAMIC_READS or "O_DIRECTORY" in flags:
            continue
        path = _opened_path(descriptor, name, directory)
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
