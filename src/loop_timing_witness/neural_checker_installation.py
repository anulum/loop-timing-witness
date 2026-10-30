# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — consumer-selected checker runtime installation

"""Bind reviewed runtime installation files independently of acquisition declarations."""

from __future__ import annotations

import hashlib
import os
import platform
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .manifest_io import canonical_json_bytes
from .neural_event_stream import NeuralCaptureRefusalError

_RUNTIME_FILE_LIMIT = 256 * 1024 * 1024
_RUNTIME_FILE_COUNT_LIMIT = 4096
_WORKER_FILE_LIMIT = 1048576


def _read_installed_file(path: Path, limit: int) -> bytes:
    """Read a bounded installation prefix from the inspected regular descriptor.

    Parameters
    ----------
    path
        Consumer-selected file, never an acquisition-selected executable path.
    limit
        Expected allocation; one extra byte distinguishes an excessive file.

    Returns
    -------
    bytes
        At most limit plus one bytes; the caller must verify complete size and identity.

    Raises
    ------
    NeuralCaptureRefusalError
        If the file is unavailable, a final symlink or nonregular.
    """
    try:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        with os.fdopen(os.open(path, flags), "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                message = "Selected checker runtime requires a regular resolved file."
                raise NeuralCaptureRefusalError(message)
            return stream.read(limit + 1)
    except OSError as exc:
        message = "Selected checker runtime file is unavailable."
        raise NeuralCaptureRefusalError(message) from exc


@dataclass(frozen=True, slots=True)
class CheckerInstalledFile:
    """One consumer-owned installation binding, never selected by run data.

    Attributes
    ----------
    name
        Portable logical name in the reviewed runtime inventory.
    path
        Actual installed regular file selected by this consumer.
    sha256, byte_length
        Complete reviewed file identity.
    """

    name: str
    path: Path
    sha256: str
    byte_length: int

    def reference(self) -> dict[str, Any]:
        """Return the portable file identity without its host installation path.

        Returns
        -------
        dict[str, Any]
            Closed runtime inventory reference.
        """
        return {"path": self.name, "sha256": self.sha256, "byte_length": self.byte_length}

    def verify(self) -> None:
        """Verify a complete selected installation file within a finite allocation.

        Raises
        ------
        NeuralCaptureRefusalError
            If the reviewed installation is unavailable, altered or unbounded.
        """
        if type(self.byte_length) is not int or not 0 <= self.byte_length <= _RUNTIME_FILE_LIMIT:
            message = "Selected checker runtime file exceeds its allocation."
            raise NeuralCaptureRefusalError(message)
        raw = _read_installed_file(self.path, self.byte_length)
        if len(raw) != self.byte_length or hashlib.sha256(raw).hexdigest() != self.sha256:
            message = "Selected checker runtime file differs from its reviewed binding."
            raise NeuralCaptureRefusalError(message)


@dataclass(frozen=True, slots=True)
class NeuralCheckerInstallation:
    """Complete immutable runtime selection attached to a consumer registry entry.

    Attributes
    ----------
    interpreter
        Actual reviewed interpreter, including its portable runtime identity.
    tracer
        Reviewed process tracer used for actual opened-file observations.
    files
        Complete reviewed interpreter, import, extension and platform inventory.
    import_roots
        Consumer-selected installation roots for the isolated Python worker.
    baseline_id, kernel_release
        Explicit reviewed platform baseline and required kernel release.
    """

    interpreter: CheckerInstalledFile
    tracer: CheckerInstalledFile
    files: tuple[CheckerInstalledFile, ...]
    import_roots: tuple[Path, ...]
    baseline_id: str
    kernel_release: str
    _worker_sources: tuple[CheckerInstalledFile, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Freeze exact worker bindings once, before the runtime is admitted.

        Raises
        ------
        NeuralCaptureRefusalError
            If a worker source is unavailable, nonregular, a final link or excessive.
        """
        result = []
        for name in ("__init__.py", "neural_checker_worker.py", "neural_checker_isolation.py"):
            path = Path(__file__).with_name(name)
            raw = _read_installed_file(path, _WORKER_FILE_LIMIT)
            if len(raw) > _WORKER_FILE_LIMIT:
                message = "Selected checker worker source exceeds its allocation."
                raise NeuralCaptureRefusalError(message)
            path = path.resolve()
            result.append(
                CheckerInstalledFile(
                    f"loop_timing_witness/{name}", path, hashlib.sha256(raw).hexdigest(), len(raw)
                )
            )
        object.__setattr__(self, "_worker_sources", tuple(result))

    def contract_bytes(self) -> bytes:
        """Serialise the closed portable contract for this reviewed installation.

        Returns
        -------
        bytes
            Complete canonical runtime contract, without executable host paths.
        """
        return canonical_json_bytes(
            {
                "schema_id": "loop-timing-witness.sc-checker-runtime.v1",
                "interpreter": self.interpreter.reference(),
                "tracer": self.tracer.reference(),
                "import_namespaces": [
                    f"imports/{index}" for index in range(len(self.import_roots))
                ],
                "worker_sources": [item.reference() for item in self.worker_files()],
                "files": [item.reference() for item in self.files],
                "platform_baseline": {
                    "id": self.baseline_id,
                    "system": "Linux",
                    "machine": "x86_64",
                    "kernel_release": self.kernel_release,
                },
                "execution_contract": {
                    "profile": "linux-x86_64-seccomp-no-network.v1",
                    "address_space_bytes": 768 * 1024 * 1024,
                    "cpu_seconds": 30,
                    "wall_seconds": 45,
                    "file_bytes": 1048576,
                    "python_site_initialisation": False,
                    "bytecode_writes": False,
                    "bytecode_reads": "owned-empty-prefix",
                },
            }
        )

    def worker_files(self) -> tuple[CheckerInstalledFile, ...]:
        """Return the frozen identities of the consumer-owned worker sources.

        Returns
        -------
        tuple[CheckerInstalledFile, ...]
            Exact worker, isolation and package initialisation bindings frozen at construction.
        """
        return self._worker_sources

    def runtime_references(self) -> dict[str, dict[str, Any]]:
        """Return the runtime and worker roles that original receipts must observe.

        Returns
        -------
        dict[str, dict[str, Any]]
            Portable references keyed by logical runtime name.
        """
        return {item.name: item.reference() for item in (*self.files, *self.worker_files())}

    def verify(self) -> None:
        """Verify every selected file and the explicit runtime platform baseline.

        Raises
        ------
        NeuralCaptureRefusalError
            If the complete installation inventory or selected platform differs,
            or a runtime file aliases a worker's logical name or physical path.
        """
        if (
            not self.baseline_id
            or platform.system() != "Linux"
            or platform.machine() != "x86_64"
            or platform.release() != self.kernel_release
            or not 1 <= len(self.files) <= _RUNTIME_FILE_COUNT_LIMIT
            or len({item.name for item in self.files}) != len(self.files)
            or len({item.path for item in self.files}) != len(self.files)
            or self.interpreter not in self.files
            or self.tracer not in self.files
        ):
            message = "Selected checker runtime inventory or platform baseline differs."
            raise NeuralCaptureRefusalError(message)
        workers = self.worker_files()
        for item in (*self.files, *workers):
            item.verify()
        runtime_names = {item.name for item in self.files}
        runtime_paths = {item.path for item in self.files}
        if any(item.name in runtime_names or item.path in runtime_paths for item in workers):
            message = "Selected checker worker/runtime roles contain an alias."
            raise NeuralCaptureRefusalError(message)
        if not self.import_roots or any(
            not path.is_dir() or path.is_symlink() for path in self.import_roots
        ):
            message = "Selected checker runtime import roots are unavailable."
            raise NeuralCaptureRefusalError(message)
