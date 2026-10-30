# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — atomic complete neural report publication

"""Publish a complete neural report through the existing no-replacement primitive."""

from __future__ import annotations

import ctypes
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .manifest_io import canonical_json_bytes
from .neural_event_stream import NeuralCaptureRefusalError
from .report_publication import DirectoryPublication


def write_neural_report(directory: Path, report: dict[str, Any]) -> None:
    """Create one complete bounded report atomically without replacing any path.

    Parameters
    ----------
    directory
        New output directory below an existing parent on the selected filesystem.
    report
        Complete report returned by the whole public neural analysis API.

    Raises
    ------
    NeuralCaptureRefusalError
        If the destination already exists or the report exceeds its finite allocation.
    OSError
        If complete staging or the native no-replacement publication fails.
    """
    if "\x00" in os.fspath(directory):
        message = "Invalid neural report destination."
        raise NeuralCaptureRefusalError(message)
    target = directory.parent.resolve() / directory.name
    if os.path.lexists(target):
        message = "Neural report output directory already exists."
        raise NeuralCaptureRefusalError(message)
    raw = canonical_json_bytes(report)
    if len(raw) > 8 * 1024 * 1024:
        message = "Complete neural report exceeds its byte allocation."
        raise NeuralCaptureRefusalError(message)
    publisher = DirectoryPublication(ctypes.CDLL(None, use_errno=True))
    publisher.check(target.parent)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    try:
        (staging / "report.json").write_bytes(raw)
        publisher.publish(staging, target)
    except BaseException:
        shutil.rmtree(staging)
        raise
