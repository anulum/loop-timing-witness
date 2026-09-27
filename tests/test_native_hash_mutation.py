# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — stable artifacts during actual native SHA reads

"""Modify actual configuration files while the production SHA reader is in progress."""

from __future__ import annotations

import ctypes
import os
import select
import signal
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from test_native_run import configuration, native_run

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = ["native_run"]


@contextmanager
def watch_access(path: Path) -> Iterator[int]:
    """Observe real Linux reads of one file without reading its content in the test.

    Parameters
    ----------
    path
        Existing configuration file to watch with IN_ACCESS.

    Yields
    ------
    int
        Kernel notification descriptor closed on every exit.
    """
    library = ctypes.CDLL(None, use_errno=True)
    library.inotify_init1.argtypes = [ctypes.c_int]
    library.inotify_init1.restype = ctypes.c_int
    library.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
    library.inotify_add_watch.restype = ctypes.c_int
    descriptor = library.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
    if descriptor < 0:
        raise OSError(ctypes.get_errno(), "cannot create read notification watch")
    try:
        if library.inotify_add_watch(descriptor, os.fsencode(path), 1) < 0:
            raise OSError(ctypes.get_errno(), "cannot watch actual configuration reads")
        yield descriptor
    finally:
        os.close(descriptor)


def stop_reader(pid: int, config: Path) -> int:
    """Confirm the real child stopped with its configuration read still in progress.

    Parameters
    ----------
    pid
        Owned native subprocess ID.
    config
        Actual file whose open descriptor must remain present.

    Returns
    -------
    int
        Kernel-reported byte offset of the actual configuration descriptor.
    """
    os.kill(pid, signal.SIGSTOP)
    observed, status = os.waitpid(pid, os.WUNTRACED)
    assert observed == pid
    assert os.WIFSTOPPED(status)
    assert os.WSTOPSIG(status) == signal.SIGSTOP
    descriptors = Path(f"/proc/{pid}/fd")
    matches = [entry for entry in descriptors.iterdir() if entry.readlink() == config]
    assert len(matches) == 1
    info = Path(f"/proc/{pid}/fdinfo/{matches[0].name}").read_text()
    fields = dict(line.split(":", 1) for line in info.splitlines())
    return int(fields["pos"].strip())


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
    with watch_access(config) as descriptor:
        process = subprocess.Popen(
            [str(native_run), str(config), str(events), str(raw), "--metadata", str(metadata)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            ready, _, _ = select.select([descriptor], [], [], 5)
            assert ready == [descriptor]
            notification = os.read(descriptor, 65536)
            assert int.from_bytes(notification[4:8], byteorder="little") & 1
            position = stop_reader(process.pid, config)
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
            if process.poll() is None:
                os.kill(process.pid, signal.SIGCONT)
                process.kill()
                process.communicate(timeout=5)
