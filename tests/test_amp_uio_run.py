# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual IRQ-free Linux AMP entry and resource refusals

"""Build the actual Linux AMP logger and refuse invalid selections without fabricated devices."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from test_native_run import configuration

ROOT = Path(__file__).resolve().parents[1]
RESOURCE = (
    "uio4294967295 loop-timing-witness devicetree "
    "0 registers 1073741824 4096 1 telemetry 2148007936 65536 "
    "1000000000 1000000000 10000\n"
)


@pytest.fixture(scope="module")
def amp_uio_program(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Compile the production UIO logger through its public Make target with strict native warnings.

    Parameters
    ----------
    tmp_path_factory
        Owned native build directory outside other simultaneous build outputs.

    Returns
    -------
    Path
        Actual compiled Linux AMP logger executable.
    """
    directory = tmp_path_factory.mktemp("amp-uio-build")
    argv = ["make", "run-amp-uio", "LINUX_BUILD_DIRECTORY=" + str(directory)]
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=60, check=False)
    (directory / "build.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    return directory / "run_amp_uio"


def test_amp_uio_usage(amp_uio_program: Path) -> None:
    """Require explicit original run/resource paths before any kernel-device acquisition.

    Parameters
    ----------
    amp_uio_program
        Public production Linux AMP entry point.
    """
    result = subprocess.run([str(amp_uio_program)], capture_output=True, text=True, check=False)
    assert result.returncode == 1
    assert "resource_configuration" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize(
    ("index", "value", "finding"),
    [
        (0, "../uio0", "invalid AMP UIO identity"),
        (3, "-1", "invalid unsigned"),
        (3, "4294967296", "outside"),
        (5, "18446744073709551616", "stoull"),
        (5, "0", "extent or alignment"),
        (5, "1073741825", "extent or alignment"),
        (6, "4095", "extent or alignment"),
        (6, "8192", "overlap or lack"),
        (7, "0", "overlap or lack"),
        (9, "1073741824", "overlap or lack"),
        (10, "16384", "overlap or lack"),
        (11, "0", "polling and lifetime"),
        (11, "60000000001", "outside"),
        (12, "0", "polling and lifetime"),
        (12, "86400000000001", "outside"),
        (13, "0", "polling and lifetime"),
        (13, "1000001", "outside"),
        (13, "999999", "sample interval"),
    ],
)
def test_amp_uio_original_resource_refusal(
    amp_uio_program: Path, tmp_path: Path, index: int, value: str, finding: str
) -> None:
    """Refuse malformed real resource files before UIO acquisition or raw output creation.

    Parameters
    ----------
    amp_uio_program
        Actual public Linux AMP executable.
    tmp_path
        Owned actual configuration files and exclusive output paths.
    index
        Explicit native resource token to contradict.
    value
        Invalid physical extent, map index or polling bound.
    finding
        Required precise refusal from the public parser or mapping admission.
    """
    run = tmp_path / "run.conf"
    run.write_text(configuration("pid", "none"), encoding="ascii")
    resource = tmp_path / "resources.conf"
    fields = RESOURCE.split()
    fields[index] = value
    resource.write_text(" ".join(fields) + "\n", encoding="ascii")
    events, tracking = tmp_path / "events.bin", tmp_path / "tracking.csv"
    result = subprocess.run(
        [str(amp_uio_program), str(run), str(resource), str(events), str(tracking)],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 1
    assert finding in result.stderr
    assert result.stdout == ""
    assert not events.exists()
    assert not tracking.exists()


def test_amp_uio_actual_unavailable_device(amp_uio_program: Path, tmp_path: Path) -> None:
    """Parse valid originals then refuse the genuinely absent kernel UIO device without fallback.

    Parameters
    ----------
    amp_uio_program
        Actual public Linux AMP entry point.
    tmp_path
        Owned original files and prospective raw/metadata outputs.
    """
    assert not Path("/sys/class/uio/uio4294967295").exists()
    run, resource = tmp_path / "run.conf", tmp_path / "resources.conf"
    run.write_text(configuration("pid", "none"), encoding="ascii")
    resource.write_text(RESOURCE, encoding="ascii")
    events, tracking, metadata = (
        tmp_path / "events.bin",
        tmp_path / "tracking.csv",
        tmp_path / "metadata.json",
    )
    result = subprocess.run(
        [
            str(amp_uio_program),
            str(run),
            str(resource),
            str(events),
            str(tracking),
            "--metadata",
            str(metadata),
        ],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 1
    assert "cannot read AMP sysfs attribute" in result.stderr
    assert not events.exists()
    assert not tracking.exists()
    assert not metadata.exists()
