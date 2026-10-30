# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — exclusive neural report publication

"""Publish one neural report atomically and refuse unsafe destinations."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from loop_timing_witness.manifest_io import canonical_json_bytes
from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError
from loop_timing_witness.neural_run_publication import write_neural_report

if TYPE_CHECKING:
    from pathlib import Path


def test_report_lands_as_one_canonical_file(tmp_path: Path) -> None:
    """Publish the canonical report and leave no staging directory.

    Parameters
    ----------
    tmp_path
        Exclusive report parent.
    """
    write_neural_report(tmp_path / "report", {"b": 1, "a": [2]})
    expected = canonical_json_bytes({"a": [2], "b": 1})
    assert (tmp_path / "report/report.json").read_bytes() == expected
    assert [item.name for item in tmp_path.iterdir()] == ["report"]


def test_unsafe_destinations_and_excessive_reports_refuse(tmp_path: Path) -> None:
    """Refuse a NUL destination, an existing link and an excessive report.

    Parameters
    ----------
    tmp_path
        Exclusive parent holding the dangling link.
    """
    with pytest.raises(NeuralCaptureRefusalError, match="Invalid neural report destination"):
        write_neural_report(tmp_path / "bad\x00name", {})
    link = tmp_path / "linked"
    link.symlink_to(tmp_path / "absent")
    with pytest.raises(NeuralCaptureRefusalError, match="already exists"):
        write_neural_report(link, {})
    with pytest.raises(NeuralCaptureRefusalError, match="exceeds its byte allocation"):
        write_neural_report(tmp_path / "large", {"data": "x" * (8 * 1024 * 1024)})
    assert [item.name for item in tmp_path.iterdir()] == ["linked"]


def test_failed_staging_write_removes_the_staging_directory(tmp_path: Path) -> None:
    """Remove the staging tree when the report write itself fails.

    Parameters
    ----------
    tmp_path
        Exclusive report parent for the limited child process.
    """
    client = (
        "import json, resource, signal, sys\n"
        "from pathlib import Path\n"
        "from loop_timing_witness.neural_run_publication import write_neural_report\n"
        "signal.signal(signal.SIGXFSZ, signal.SIG_IGN)\n"
        "_, hard = resource.getrlimit(resource.RLIMIT_FSIZE)\n"
        "resource.setrlimit(resource.RLIMIT_FSIZE, (64, hard))\n"
        "try:\n"
        "    write_neural_report(Path(sys.argv[1]) / 'report', {'data': 'x' * 1000})\n"
        "except OSError as error:\n"
        "    print(json.dumps(error.errno))\n"
        "resource.setrlimit(resource.RLIMIT_FSIZE, (hard, hard))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", client, str(tmp_path)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == 27
    assert list(tmp_path.iterdir()) == []
