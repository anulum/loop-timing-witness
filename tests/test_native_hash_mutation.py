# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — stable artifacts during actual native SHA reads

"""Modify actual configuration files while the production SHA reader is in progress."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

import pytest
from test_native_run import configuration, native_run

__all__ = ["native_run"]


def stop_reader(process: subprocess.Popen[str], config: Path) -> int:
    """Confirm the real child stopped with its configuration read still in progress.

    Parameters
    ----------
    process
        Owned native subprocess whose lifecycle remains under the test's control.
    config
        Actual file whose open descriptor must remain present.

    Returns
    -------
    int
        Kernel-reported byte offset of the actual configuration descriptor.
    """
    deadline = time.monotonic() + 5
    original_size = config.stat().st_size
    position = 0
    while not 0 < position < original_size:
        assert time.monotonic() < deadline, "native configuration read did not start"
        assert process.poll() is None, "native reader exited before its configuration read"
        os.kill(process.pid, signal.SIGSTOP)
        observed, status = os.waitpid(process.pid, os.WUNTRACED)
        assert observed == process.pid
        assert os.WIFSTOPPED(status)
        assert os.WSTOPSIG(status) == signal.SIGSTOP
        descriptors = Path(f"/proc/{process.pid}/fd")
        matches = [entry for entry in descriptors.iterdir() if entry.readlink() == config]
        if matches:
            assert len(matches) == 1
            info = Path(f"/proc/{process.pid}/fdinfo/{matches[0].name}").read_text()
            fields = dict(line.split(":", 1) for line in info.splitlines())
            position = int(fields["pos"].strip())
        if not 0 < position < original_size:
            process.send_signal(signal.SIGCONT)
            time.sleep(0.001)
    return position


@pytest.mark.parametrize("mutation", ["append", "truncate", "replace", "unlink"])
def test_actual_configuration_changed_during_hash(
    native_run: Path, tmp_path: Path, mutation: str
) -> None:
    """Refuse file growth or changed identity/content during actual initial SHA reads.

    Parameters
    ----------
    native_run
        Production native CLI with actual OpenSSL EVP SHA-256 implementation.
    tmp_path
        Exclusive configuration and output allocation.
    mutation
        Real append, truncation, path replacement or unlink while the child is stopped.
    """
    config = tmp_path / "run.conf"
    with config.open("wb") as stream:
        stream.write(configuration("pid", "none").encode())
        padding = b" " * (1024 * 1024)
        for _ in range(128):
            stream.write(padding)
    original_size = config.stat().st_size
    events, raw, metadata = (tmp_path / name for name in ("events.bin", "raw.csv", "metadata.json"))
    process = subprocess.Popen(
        [str(native_run), str(config), str(events), str(raw), "--metadata", str(metadata)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        position = stop_reader(process, config)
        assert 0 < position < original_size
        assert not events.exists()
        if mutation == "append":
            with config.open("ab") as stream:
                stream.write(b" ")
        elif mutation == "truncate":
            with config.open("r+b") as stream:
                stream.truncate(0)
        elif mutation == "replace":
            replacement = tmp_path / "replacement.conf"
            replacement.write_text(configuration("pid", "none"), encoding="utf-8")
            replacement.replace(config)
        else:
            config.unlink()
        os.kill(process.pid, signal.SIGCONT)
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 1
        assert stdout == ""
        expected = (
            "native artifact grew during hashing"
            if mutation == "append"
            else "native artifact changed during hashing"
        )
        assert stderr.strip() == expected
        assert not any(path.exists() for path in (events, raw, metadata))
    finally:
        process.send_signal(signal.SIGCONT)
        process.kill()
        process.communicate(timeout=5)
