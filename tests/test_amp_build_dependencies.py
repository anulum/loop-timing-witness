# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original ISA logger completion and corruption regression tests

"""Read genuine GCC dependency closure and refuse damaged original records."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from amp_build_dependencies import dependency_hashes

from manifest_io import sha256_of_file

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def compiled_dependencies(tmp_path: Path) -> tuple[Path, Path]:
    """Compile actual production C source with spaces and dollars in its owned directory name.

    Parameters
    ----------
    tmp_path
        Exclusive copy and real compiler output.

    Returns
    -------
    tuple of Path and Path
        Actual compiler working directory and original dependency record.
    """
    source = tmp_path / "original $ controller"
    source.mkdir()
    for name in ("witness_controller.c", "witness_controller.h"):
        shutil.copyfile(ROOT / "controllers/c" / name, source / name)
    record = tmp_path / "controller.d"
    subprocess.run(
        [
            "gcc",
            "-std=gnu11",
            "-MD",
            "-MF",
            str(record),
            "-c",
            str(source / "witness_controller.c"),
            "-o",
            str(tmp_path / "controller.o"),
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        timeout=30,
    )
    return tmp_path, record


def test_actual_source_system_closure(compiled_dependencies: tuple[Path, Path]) -> None:
    """Require all compiler-reported original production and system-header identities.

    Parameters
    ----------
    compiled_dependencies
        Genuine GCC compilation and escaped dependency record.
    """
    directory, record = compiled_dependencies
    digests = dependency_hashes((record,), directory)
    assert any(name.endswith("witness_controller.c") for name in digests)
    assert any(name.endswith("stdint.h") for name in digests)
    assert all(
        Path(name).is_absolute() and sha256_of_file(Path(name)) == digest
        for name, digest in digests.items()
    )
    relative = record.read_text().replace(str(directory) + "/", "")
    record.write_text(relative)
    assert dependency_hashes((record,), directory) == digests


@pytest.mark.parametrize("fault", ["absent", "target", "separator", "empty"])
def test_broken_original_records_refused(
    compiled_dependencies: tuple[Path, Path], fault: str
) -> None:
    """Refuse absent or corrupted genuine compiler records without substituting headers.

    Parameters
    ----------
    compiled_dependencies
        Original actual compilation.
    fault
        Missing complete record set, missing target, missing separator or empty source list.
    """
    directory, record = compiled_dependencies
    records: tuple[Path, ...]
    if fault == "absent":
        records = ()
    else:
        records = (record,)
        if fault == "target":
            content = ":" + record.read_text().partition(":")[2]
        elif fault == "separator":
            content = record.read_text().replace(":", "", 1)
        else:
            content = record.read_text().partition(":")[0] + ":"
        record.write_text(content)
    with pytest.raises(ValueError, match="dependency record"):
        dependency_hashes(records, directory)
