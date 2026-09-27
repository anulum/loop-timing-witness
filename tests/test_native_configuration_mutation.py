# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — configuration integrity during actual run execution

"""Observe real output creation and change the actual configuration during a run."""

from __future__ import annotations

import ctypes
import os
import select
import signal
import struct
import subprocess
import time
from typing import TYPE_CHECKING

import pytest
from test_native_run import configuration, native_run

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

__all__ = ["native_run"]


@pytest.fixture
def creation_watch(tmp_path: Path) -> Iterator[int]:
    """Watch real output creation before launching the native controller.

    Parameters
    ----------
    tmp_path
        Actual exclusive run directory observed through Linux inotify.

    Yields
    ------
    int
        Nonblocking kernel watch descriptor, closed after the test.
    """
    library = ctypes.CDLL(None, use_errno=True)
    library.inotify_init1.argtypes = [ctypes.c_int]
    library.inotify_init1.restype = ctypes.c_int
    library.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
    library.inotify_add_watch.restype = ctypes.c_int
    descriptor = library.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
    if descriptor < 0:
        raise OSError(ctypes.get_errno(), "cannot create actual inotify watch")
    try:
        if library.inotify_add_watch(descriptor, os.fsencode(tmp_path), 0x100) < 0:
            raise OSError(ctypes.get_errno(), "cannot watch actual output directory")
        yield descriptor
    finally:
        os.close(descriptor)


def wait_for_events(descriptor: int) -> None:
    """Wait for kernel evidence that the native event output was created.

    Parameters
    ----------
    descriptor
        Actual inotify descriptor monitoring the exclusive directory.
    """
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        ready, _, _ = select.select([descriptor], [], [], max(0, deadline - time.monotonic()))
        if not ready:
            break
        records = os.read(descriptor, 65536)
        offset = 0
        while offset < len(records):
            _, mask, _, length = struct.unpack_from("iIII", records, offset)
            name = records[offset + 16 : offset + 16 + length].rstrip(b"\0")
            if mask & 0x100 and name == b"events.bin":
                return
            offset += 16 + length
    pytest.fail("native controller did not create its actual event output")


@pytest.mark.parametrize("mutation", ["overwrite", "replace", "append", "symlink"])
def test_configuration_changed_during_run(
    native_run: Path, tmp_path: Path, creation_watch: int, mutation: str
) -> None:
    """Refuse changed configuration while retaining the actual completed run data.

    Parameters
    ----------
    native_run
        Production executable linked to an actual mechanical or thermal RTL plant.
    tmp_path
        Exclusive configuration, raw evidence and metadata allocation.
    creation_watch
        Kernel output-creation notification installed before process launch.
    mutation
        Actual overwrite, inode replacement, append or symlink substitution.
    """
    config = tmp_path / "run.conf"
    original = configuration("pid", "none").replace("pid 32", "pid 64")
    config.write_text(original, encoding="utf-8")
    events, raw, metadata = (tmp_path / name for name in ("events.bin", "raw.csv", "metadata.json"))
    process = subprocess.Popen(
        [str(native_run), str(config), str(events), str(raw), "--metadata", str(metadata)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_for_events(creation_watch)
        os.kill(process.pid, signal.SIGSTOP)
        observed, status = os.waitpid(process.pid, os.WUNTRACED)
        assert observed == process.pid
        assert os.WIFSTOPPED(status)
        assert os.WSTOPSIG(status) == signal.SIGSTOP
        assert events.exists()
        if mutation == "overwrite":
            config.write_text(original.replace("pid", "lqr", 1), encoding="utf-8")
        elif mutation == "replace":
            replacement = tmp_path / "replacement.conf"
            replacement.write_text(original.replace("pid", "lqr", 1), encoding="utf-8")
            replacement.replace(config)
        elif mutation == "append":
            with config.open("a", encoding="utf-8") as stream:
                stream.write(" ")
        else:
            saved = tmp_path / "original.conf"
            config.rename(saved)
            config.symlink_to(saved)
        os.kill(process.pid, signal.SIGCONT)
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 1
        assert stdout == ""
        expected = (
            "cannot hash actual regular artifact"
            if mutation == "symlink"
            else "native configuration changed during execution"
        )
        assert stderr.strip() == expected
        assert events.stat().st_size > 0
        assert events.stat().st_size % 16 == 0
        assert len(raw.read_text().splitlines()) == 65
        assert not metadata.exists()
    finally:
        if process.poll() is None:
            os.kill(process.pid, signal.SIGCONT)
            process.kill()
            process.communicate(timeout=5)
