# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — native artifact SHA-256 receipts

"""Verify hashes of actual native captures through the production run entry."""

from __future__ import annotations

import ctypes
import ctypes.util
import errno
import hashlib
import json
import os
import stat
import subprocess
from typing import TYPE_CHECKING

import pytest
from test_native_run import configuration, native_run

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["native_run"]


@pytest.mark.parametrize("padding", [0, 131073])
def test_actual_artifact_digests(native_run: Path, tmp_path: Path, padding: int) -> None:
    """Compare actual complete configuration/event/raw receipts to independent SHA-256.

    Parameters
    ----------
    native_run
        Native controller linked to the actual production RTL plant.
    tmp_path
        Exclusive actual run directory.
    padding
        Valid trailing whitespace exercising single and multiple hash reads.
    """
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none") + " " * padding, encoding="utf-8")
    events, raw, metadata = (tmp_path / name for name in ("events.bin", "raw.csv", "metadata.json"))
    result = subprocess.run(
        [str(native_run), str(config), str(events), str(raw), "--metadata", str(metadata)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    facts = json.loads(metadata.read_text())
    library = ctypes.util.find_library("crypto")
    assert library is not None
    crypto = ctypes.CDLL(library)
    crypto.OpenSSL_version_num.restype = ctypes.c_ulong
    assert facts["crypto_library"]["algorithm"] == "sha256"
    assert facts["crypto_library"]["runtime_version_number"] == crypto.OpenSSL_version_num()
    assert facts["crypto_library"]["header_version_number"] >= 0x30000000
    assert set(facts["artifacts"]) == {"configuration", "events", "tracking_raw"}
    for role, path in [("configuration", config), ("events", events), ("tracking_raw", raw)]:
        content = path.read_bytes()
        assert facts["artifacts"][role] == {
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
        }


@pytest.mark.parametrize("kind", ["symlink", "directory", "fifo", "empty"])
def test_configuration_hash_refusal(native_run: Path, tmp_path: Path, kind: str) -> None:
    """Refuse unavailable/nonregular configurations without writing run outputs.

    Parameters
    ----------
    native_run
        Actual native controller binary.
    tmp_path
        Exclusive filesystem allocation.
    kind
        Actual filesystem/configuration condition under test.
    """
    original = tmp_path / "original.conf"
    original.write_text(configuration("pid", "none"), encoding="utf-8")
    config = tmp_path / "run.conf"
    if kind == "symlink":
        config.symlink_to(original)
    elif kind == "directory":
        config.mkdir()
    elif kind == "fifo":
        os.mkfifo(config)
    else:
        config.write_bytes(b"")
    events, raw, metadata = (tmp_path / name for name in ("events.bin", "raw.csv", "metadata.json"))
    result = subprocess.run(
        [str(native_run), str(config), str(events), str(raw), "--metadata", str(metadata)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 1
    assert (
        "controller must be pid or lqr" if kind == "empty" else "regular artifact"
    ) in result.stderr
    assert not any(path.exists() for path in (events, raw, metadata))


def test_unavailable_sha256_provider(native_run: Path, tmp_path: Path) -> None:
    """Refuse a real OpenSSL environment with no SHA-256 implementation.

    Parameters
    ----------
    native_run
        Actual controller binary linked to the production RTL model.
    tmp_path
        Exclusive process configuration and output allocation.
    """
    config = tmp_path / "run.conf"
    config.write_text(configuration("pid", "none"), encoding="utf-8")
    provider = tmp_path / "openssl.cnf"
    provider.write_text(
        "openssl_conf = openssl_init\n[openssl_init]\nproviders = providers\n"
        "[providers]\nnull = null_section\n[null_section]\nactivate = 1\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["OPENSSL_CONF"] = str(provider)
    events, raw, metadata = (tmp_path / name for name in ("events.bin", "raw.csv", "metadata.json"))
    result = subprocess.run(
        [str(native_run), str(config), str(events), str(raw), "--metadata", str(metadata)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        env=environment,
    )
    assert result.returncode == 1
    assert "cannot initialize native SHA-256" in result.stderr
    assert not any(path.exists() for path in (events, raw, metadata))
    assert os.environ.get("OPENSSL_CONF") != str(provider)


def test_actual_kernel_read_error(native_run: Path, tmp_path: Path) -> None:
    """Refuse a genuine Linux EIO while hashing the child's own process memory file.

    Parameters
    ----------
    native_run
        Actual production CLI with the linked OpenSSL artifact reader.
    tmp_path
        Exclusive event, trace and metadata destinations.
    """
    descriptor = os.open("/proc/self/mem", os.O_RDONLY | os.O_CLOEXEC)
    try:
        assert stat.S_ISREG(os.fstat(descriptor).st_mode)
        with pytest.raises(OSError, match=rf"\[Errno {errno.EIO}\]") as error:
            os.read(descriptor, 1)
        assert error.value.errno == errno.EIO
    finally:
        os.close(descriptor)
    events, raw, metadata = (tmp_path / name for name in ("events.bin", "raw.csv", "metadata.json"))
    result = subprocess.run(
        [str(native_run), "/proc/self/mem", str(events), str(raw), "--metadata", str(metadata)],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    assert result.returncode == 1
    assert result.stderr.strip() == "cannot read native artifact bytes"
    assert result.stdout == ""
    assert not any(path.exists() for path in (events, raw, metadata))
