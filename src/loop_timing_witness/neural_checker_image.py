# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — immutable source-checker image executor

"""Run the admitted source checker inside a verified read-only executor image.

The source owner supplies a sealed root filesystem and a fixed launcher
command. This consumer binds every image file, directory and symbolic link,
the host launcher files and required host absences, and verifies them before
and after each operation. Only the image root, the owned working directory and
the fixed operation are substituted into the command; acquisition data cannot
select any of them.
"""

from __future__ import annotations

import hashlib
import os
import platform
import signal
import stat
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from .manifest_io import JsonInputRefusalError, canonical_json_bytes, parse_json_object
from .neural_checker_execution import (
    CheckerInvocation,
    bounded_output,
    exact_text,
    read_observation,
)
from .neural_checker_installation import CheckerInstalledFile
from .neural_event_stream import NeuralCaptureRefusalError
from .neural_json_shapes import EXECUTION_FIELDS, REFERENCE_FIELDS, record, records, texts, typed

if TYPE_CHECKING:
    from collections.abc import Sequence

IMAGE_EXECUTOR_SCHEMA = "loop-timing-witness.sc-checker-image-executor.v1"
_BOUNDARY_SCHEMA = "loop-timing-witness.sc-checker-image-boundary.v1"
_PLACEHOLDERS = ("{image_root}", "{work_directory}", "{operation}")
_FILE_LIMIT = 1048576
_DEADLINE_LIMIT = 300
_IMAGE_FILE_LIMIT = 256 * 1024 * 1024
_WORK = PurePosixPath("/work")
_WORK_DATA = frozenset(
    {"stimuli.txt", "results_expected.txt", "results_verilog.txt", "checker-observation.json"}
)
_BINDING_FIELDS = frozenset(
    {
        "schema_id",
        "supplier",
        "historical_contracts",
        "command",
        "bootstrap_environment",
        "deadline_seconds",
        "host_boundary",
        "image",
        "source_files",
        "worker_files",
    }
)


def _refuse(message: str) -> NeuralCaptureRefusalError:
    """Return the public refusal raised for an unusable executor image.

    Parameters
    ----------
    message
        Fixed authored diagnostic.

    Returns
    -------
    NeuralCaptureRefusalError
        Refusal carrying only authored text.
    """
    return NeuralCaptureRefusalError(message)


_RUNTIME_FIELDS = frozenset(
    {
        "schema_id",
        "interpreter",
        "tracer",
        "import_namespaces",
        "worker_sources",
        "files",
        "platform_baseline",
        "execution_contract",
    }
)
_PLATFORM_NAMES = ("id", "system", "machine", "kernel_release")
_PLATFORM_FIELDS: dict[str, type] = dict.fromkeys(_PLATFORM_NAMES, str)


def _runtime_closed(runtime: dict[str, Any]) -> bool:
    """Tell whether a historical runtime has the complete closed descriptor form.

    Parameters
    ----------
    runtime
        Decoded runtime contract.

    Returns
    -------
    bool
        Whether every field is present, typed and nothing else is declared.
    """
    if set(runtime) != _RUNTIME_FIELDS:
        return False
    return (
        typed(runtime["schema_id"], str)
        and record(runtime["interpreter"], REFERENCE_FIELDS)
        and record(runtime["tracer"], REFERENCE_FIELDS)
        and texts(runtime["import_namespaces"])
        and records(runtime["worker_sources"], REFERENCE_FIELDS)
        and records(runtime["files"], REFERENCE_FIELDS)
        and record(runtime["platform_baseline"], _PLATFORM_FIELDS)
        and record(runtime["execution_contract"], EXECUTION_FIELDS)
    )


def _placeholders_closed(values: Sequence[object]) -> bool:
    """Require each placeholder to be a whole value and no other braces.

    Parameters
    ----------
    values
        Command arguments or environment values from the consumer binding.

    Returns
    -------
    bool
        Whether every value is text and braces appear only as whole placeholders.
    """
    return all(
        isinstance(value, str) and (value in _PLACEHOLDERS or "{" not in value) for value in values
    )


@dataclass(frozen=True, slots=True)
class ImageCheckerExecutor:
    """Consumer-selected immutable checker image with its fixed launcher contract.

    Attributes
    ----------
    image_root
        Consumer-selected absolute directory holding the extracted image.
    binding_bytes
        Exact consumer executor binding: command, host boundary and image inventory.
    runtime_bytes
        Exact historical checker runtime contract the admitted acquisitions declare.
    """

    image_root: Path
    binding_bytes: bytes
    runtime_bytes: bytes
    _binding: dict[str, Any] = field(init=False, repr=False)
    _runtime: dict[str, Any] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Decode and close the binding once, before any image is used.

        Raises
        ------
        NeuralCaptureRefusalError
            If the binding or runtime contract is not the closed reviewed form.
        """
        binding = parse_json_object(self.binding_bytes, "checker image executor binding")
        try:
            runtime = parse_json_object(self.runtime_bytes, "checker image historical runtime")
        except JsonInputRefusalError as exc:
            message = "Invalid original checker image historical runtime."
            raise _refuse(message) from exc
        if not _runtime_closed(runtime):
            message = "Invalid original checker image historical runtime."
            raise _refuse(message)
        command = binding.get("command")
        environment = binding.get("bootstrap_environment")
        if (
            set(binding) != _BINDING_FIELDS
            or binding["schema_id"] != IMAGE_EXECUTOR_SCHEMA
            or not isinstance(command, list)
            or not command
            or not isinstance(environment, dict)
            or not _placeholders_closed(command)
            or not _placeholders_closed(list(environment.values()))
            or type(binding["deadline_seconds"]) is not int
            or not 0 < binding["deadline_seconds"] <= _DEADLINE_LIMIT
            or not binding["source_files"]
            or not binding["worker_files"]
        ):
            message = "Checker image executor binding is not its closed reviewed form."
            raise _refuse(message)
        object.__setattr__(self, "_binding", binding)
        object.__setattr__(self, "_runtime", runtime)

    def contract_bytes(self) -> bytes:
        """Return the historical runtime contract that acquisitions must carry.

        Returns
        -------
        bytes
            Exact source-owner historical runtime declaration. The image is its
            qualified successor; the declaration is compared, never executed.
        """
        return self.runtime_bytes

    def runtime_references(self) -> dict[str, dict[str, Any]]:
        """Return the historical runtime and worker roles that original receipts observed.

        Returns
        -------
        dict[str, dict[str, Any]]
            Portable references keyed by logical runtime name.
        """
        return {
            item["path"]: item
            for item in (*self._runtime["files"], *self._runtime["worker_sources"])
        }

    def verify(self) -> None:
        """Verify the host launcher boundary and the complete image inventory.

        Raises
        ------
        NeuralCaptureRefusalError
            If the platform, account, launcher files, required absences or any
            image file, directory, link, mode or byte differs.
        """
        self._verify_host()
        self._verify_image()

    def _verify_host(self) -> None:
        """Verify the explicit host kernel, account, launcher files and absences.

        Raises
        ------
        NeuralCaptureRefusalError
            If any host boundary input differs.
        """
        host = self._binding["host_boundary"]
        if (
            platform.system() != host["system"]
            or platform.machine() != host["machine"]
            or platform.release() != host["kernel_release"]
            or os.getuid() != host["uid"]
            or os.getgid() != host["gid"]
        ):
            message = "Checker image host platform or account differs from its boundary."
            raise _refuse(message)
        for item in host["files"]:
            CheckerInstalledFile(
                item["path"], Path(item["path"]), item["sha256"], item["byte_length"]
            ).verify()
        if any(os.path.lexists(path) for path in host["absent_paths"]):
            message = "Checker image host contains a path its boundary requires absent."
            raise _refuse(message)

    def _verify_image(self) -> None:
        """Verify that the image tree holds exactly the bound entries and bytes.

        Raises
        ------
        NeuralCaptureRefusalError
            If the root is unusable or any entry is missing, extra or altered.
        """
        root = self.image_root
        if not root.is_absolute() or root.is_symlink() or not root.is_dir():
            message = "Checker image root must be an absolute real directory."
            raise _refuse(message)
        image = self._binding["image"]
        files: dict[str, dict[str, Any]] = {item["path"]: item for item in image["files"]}
        links = {item["path"]: item["target"] for item in image["symlinks"]}
        found_files: set[str] = set()
        found_dirs: set[str] = set()
        found_links: dict[str, str] = {}
        for current, directories, names in os.walk(root):
            base = Path(current).relative_to(root)
            for name in [*directories, *names]:
                path = Path(current) / name
                relative = (base / name).as_posix()
                if path.is_symlink():
                    found_links[relative] = str(path.readlink())
                elif path.is_dir():
                    found_dirs.add(relative)
                else:
                    found_files.add(relative)
        if found_files != set(files) or found_dirs != set(image["directories"]):
            message = "Checker image entries differ from the bound image inventory."
            raise _refuse(message)
        if found_links != links:
            message = "Checker image links differ from the bound image inventory."
            raise _refuse(message)
        for relative, item in files.items():
            _verify_image_file(root / relative, item)

    def invoke(self, operation: str, directory: Path) -> CheckerInvocation:
        """Run one fixed operation in the image and verify it stayed unchanged.

        Parameters
        ----------
        operation
            Fixed ``generate`` or ``check`` operation chosen by the verifier.
        directory
            Owned private working directory bound as the payload's ``/work``.

        Returns
        -------
        CheckerInvocation
            Actual command, status, timing, logs, boundary record and observation.
            A deadline stops and reaps the whole process group without restart.

        Raises
        ------
        NeuralCaptureRefusalError
            If the operation is unsupported, or the image or host boundary
            differs before or after execution.
        """
        if operation not in {"generate", "check"}:
            message = "Unsupported fixed source-checker operation."
            raise _refuse(message)
        self.verify()
        values = {
            "{image_root}": exact_text(self.image_root),
            "{work_directory}": exact_text(directory),
            "{operation}": operation,
        }
        command = tuple(values.get(item, item) for item in self._binding["command"])
        environment = {
            key: values.get(value, value)
            for key, value in self._binding["bootstrap_environment"].items()
        }
        stdout_path = directory.parent / f"{directory.name}.stdout"
        stderr_path = directory.parent / f"{directory.name}.stderr"
        started = time.time_ns()
        monotonic = time.monotonic_ns()
        interrupted = False
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            process = subprocess.Popen(
                command,
                cwd=directory,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                close_fds=True,
                start_new_session=True,
            )
            try:
                process.wait(timeout=self._binding["deadline_seconds"])
            except subprocess.TimeoutExpired:
                interrupted = True
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            except BaseException:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise
        completed = time.time_ns()
        elapsed = time.monotonic_ns() - monotonic
        self.verify()
        observation = read_observation(directory / "checker-observation.json")
        boundary = canonical_json_bytes(
            {
                "schema_id": _BOUNDARY_SCHEMA,
                "executor_binding_sha256": hashlib.sha256(self.binding_bytes).hexdigest(),
                "image_and_host_boundary": "verified-before-and-after",
                "environment": environment,
            }
        )
        return CheckerInvocation(
            command,
            process.returncode,
            started,
            completed,
            elapsed,
            bounded_output(stdout_path, _FILE_LIMIT),
            bounded_output(stderr_path, _FILE_LIMIT),
            boundary,
            observation,
            interrupted,
        )

    def closure_findings(
        self, invocation: CheckerInvocation, source_digests: Sequence[str]
    ) -> tuple[str, ...]:
        """Compare loaded files and SC modules with the image and admitted source closure.

        Parameters
        ----------
        invocation
            Complete actual image execution and worker observation.
        source_digests
            SHA-256 of every source file in the admitted checker closure.

        Returns
        -------
        tuple[str, ...]
            Independent source/runtime closure failures; absence is never success.
        """
        observation = invocation.observation
        records = _observed_records(observation)
        if observation is None or records is None:
            return ("Actual source checker opened-file observation is unavailable.",)
        files = {item["path"]: item for item in self._binding["image"]["files"]}
        sources = set(self._binding["source_files"])
        failures = []
        if sorted(files[path]["sha256"] for path in sources) != sorted(source_digests):
            failures.append("Checker image source closure differs from the admitted sources.")
        observed: set[str] = set()
        outside = False
        for path, digest, length in records:
            pure = PurePosixPath(path)
            if pure.parent == _WORK and pure.name in _WORK_DATA:
                continue
            relative = path.removeprefix("/")
            item = files.get(relative)
            if (
                not pure.is_absolute()
                or item is None
                or (item["sha256"], item["byte_length"]) != (digest, length)
            ):
                outside = True
            observed.add(relative)
        if not sources.issubset(observed):
            failures.append(
                "Actual source checker did not open its complete admitted source closure."
            )
        if outside:
            failures.append(
                "Actual source checker opened a file outside its complete runtime binding."
            )
        modules = observation.get("modules")
        if not isinstance(modules, list) or any(
            not isinstance(item, dict)
            or not isinstance(item.get("name"), str)
            or (
                item["name"].startswith("sc_neurocore")
                and str(item.get("path", "")).removeprefix("/") not in sources
            )
            for item in modules
        ):
            failures.append("Actual source checker imported a live or unbound SC source fallback.")
        return tuple(failures)


def _observed_records(
    observation: dict[str, Any] | None,
) -> list[tuple[str, str, int]] | None:
    """Decode the worker's observed file records without trusting their shape.

    Parameters
    ----------
    observation
        Parsed worker observation, if one was written.

    Returns
    -------
    list[tuple[str, str, int]] | None
        Path, digest and length of each record, or ``None`` if malformed.
    """
    if observation is None or not isinstance(observation.get("files"), list):
        return None
    records = []
    for item in observation["files"]:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("path"), str)
            or not isinstance(item.get("sha256"), str)
            or type(item.get("byte_length")) is not int
        ):
            return None
        records.append((item["path"], item["sha256"], item["byte_length"]))
    return records


def _verify_image_file(path: Path, item: dict[str, Any]) -> None:
    """Verify one image file's type, mode, length and digest without following links.

    Parameters
    ----------
    path
        Image file path under the verified root.
    item
        Bound identity with ``sha256``, ``byte_length`` and integer ``mode``.

    Raises
    ------
    NeuralCaptureRefusalError
        If the entry is unavailable, nonregular, or differs in any bound property.
    """
    try:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        with os.fdopen(os.open(path, flags), "rb") as stream:
            status = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(status.st_mode)
                or stat.S_IMODE(status.st_mode) != item["mode"]
                or status.st_size != item["byte_length"]
                or status.st_size > _IMAGE_FILE_LIMIT
            ):
                message = "Checker image file type, mode or length differs from its binding."
                raise _refuse(message)
            digest = hashlib.sha256()
            for block in iter(lambda: stream.read(1 << 20), b""):
                digest.update(block)
    except OSError as exc:
        message = "Checker image file is unavailable."
        raise _refuse(message) from exc
    if digest.hexdigest() != item["sha256"]:
        message = "Checker image file bytes differ from its binding."
        raise _refuse(message)
