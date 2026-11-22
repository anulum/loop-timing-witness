# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — hermetic complete neural acquisition for tests

"""Build a complete neural acquisition and its own reviewed registry entry.

The simulation data are the original epoch-0 output of the selected cohort.
Sources, compiled objects, receipts and the checker image are test-owned, so
the whole consumer chain runs without host installations or another group's
files. The image checker really regenerates and compares the numerical files.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import shutil
import stat
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loop_timing_witness.neural_checker_execution import checker_environment, invoke_source_checker
from loop_timing_witness.neural_checker_image import IMAGE_EXECUTOR_SCHEMA, ImageCheckerExecutor
from loop_timing_witness.neural_checker_installation import (
    CheckerInstalledFile,
    NeuralCheckerInstallation,
)
from loop_timing_witness.neural_checker_trace import checker_opened_files
from loop_timing_witness.neural_run_manifest import NEURAL_SCHEMA_ID, NEURAL_SCHEMA_SHA256
from loop_timing_witness.neural_run_policy import PUBLIC_COHORT
from loop_timing_witness.strict_json import canonical_json_bytes

if TYPE_CHECKING:
    from collections.abc import Callable

    from loop_timing_witness.neural_run_policy import NeuralEntry, NeuralRegistry

type Change = Callable[[str, bytes], bytes]
"""Rewrite of one within-run file, given its path and original bytes."""

_DATA = Path(__file__).resolve().parent / "data"
_PACKAGE = Path(__file__).resolve().parents[1] / "src/loop_timing_witness"
_SC = "source/SC-NEUROCORE/"
_LTW = "source/LOOP-TIMING-WITNESS/"
ENTRY = f"{_SC}scripts/cosim_gen_and_check.py"
"""Acquisition path of the test-owned source checker program."""

REFERENCE = f"{_SC}tests/data/results_expected.txt"
"""Acquisition path of the checker's own expected-result data."""

BODY_PINS = (
    "hdl/sc_lif_neuron.v",
    "hdl/tb_sc_lif_neuron.v",
    "hdl/sc_aer_encoder.v",
    "src/sc_neurocore/neurons/fixed_point_lif.py",
    "src/sc_neurocore/constants.py",
    "scripts/cosim_gen_and_check.py",
    "tests/test_cosim_gen_and_check.py",
)
"""The seven SC body paths every manifest must pin."""

_RTL = (
    "native_neural_dut.sv",
    "source/proposed_neural_wrapper.sv",
    f"{_SC}hdl/sc_lif_neuron.v",
    f"{_SC}hdl/sc_aer_encoder.v",
    f"{_LTW}rtl/clock_reset_release.sv",
    f"{_LTW}rtl/shared_event_witness.sv",
    f"{_LTW}rtl/event_record_fifo.sv",
)
# Kind and command of each native build job, in order.
_NATIVE_BUILD: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "RTL_elaboration",
        (
            "verilator",
            "--cc",
            "--Wall",
            "--assert",
            "--language",
            "1800-2012",
            "+1800-2012ext+v",
            "+1800-2012ext+sv",
            *(f"/build/{name}" for name in _RTL),
        ),
    ),
    ("generated_model_archive", ("make", "archive")),
    (
        "native_CPP_compile",
        (
            "g++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wconversion",
            "-Wshadow",
            "/build/native/native_trial.cpp",
        ),
    ),
    ("native_CPP_link", ("g++", "-o", "native_trial")),
)
_ARTIFACTS = (
    "native_executable",
    "generated_model_archive",
    "generated_model_header",
    "verilated_runtime_object",
    "verilated_threads_object",
)
_GENERATE = ["--generate", "--steps", "1000", "--seed", "42"]
_CHECK = ["--check", "--steps", "1000", "--seed", "42"]
# Acquisition paths of the checker closure, in role order.
_CHECKER_SOURCES = (ENTRY, REFERENCE, "stimuli.txt")
_EXECUTION_CONTRACT = {
    "profile": "test-image-namespace.v1",
    "address_space_bytes": 805306368,
    "cpu_seconds": 30,
    "wall_seconds": 45,
    "file_bytes": 1048576,
    "python_site_initialisation": False,
    "bytecode_writes": False,
    "bytecode_reads": "owned-empty-prefix",
}

# The checker program compares whole files; it is the test stand-in for the
# source owner's generator and checker, run inside the bound image.
CHECKER = """import sys
from pathlib import Path

closure = Path(__file__).resolve().parents[3]
stimuli = (closure / "stimuli.txt").read_bytes()
expected = (closure / "source/SC-NEUROCORE/tests/data/results_expected.txt").read_bytes()
if sys.argv[1] == "--generate":
    Path("stimuli.txt").write_bytes(stimuli)
    Path("results_expected.txt").write_bytes(expected)
    print("generated 1000 rows")
elif Path("results_verilog.txt").read_bytes() == expected:
    print("check passed")
else:
    sys.exit(3)
"""

# The worker runs the checker and records every opened image file under the
# namespace paths that the real isolated launcher reports.
_WORKER = """import hashlib, json, runpy, sys, time
from pathlib import Path

root, work, operation = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
entry = root / "source/SC-NEUROCORE/scripts/cosim_gen_and_check.py"
argv = [str(entry), f"--{operation}", "--steps", "1000", "--seed", "42"]
started = time.time_ns()
monotonic = time.monotonic_ns()
status = 0
sys.argv = argv
try:
    runpy.run_path(str(entry), run_name="__main__")
except SystemExit as exc:
    status = exc.code if type(exc.code) is int else 1
def record(name, raw):
    return {"path": name, "sha256": hashlib.sha256(raw).hexdigest(), "byte_length": len(raw)}
records = []
for path in sorted(p for p in root.rglob("*") if p.is_file()):
    records.append(record("/" + path.relative_to(root).as_posix(), path.read_bytes()))
for name in ("stimuli.txt", "results_expected.txt", "results_verilog.txt"):
    if (work / name).is_file():
        records.append(record("/work/" + name, (work / name).read_bytes()))
observation = {
    "schema_id": "loop-timing-witness.sc-checker-worker-observation.v1",
    "operation": operation,
    "actual_argv": argv,
    "native_returncode": status,
    "phase": "source",
    "started_ns": started,
    "completed_ns": time.time_ns(),
    "elapsed_ns": time.monotonic_ns() - monotonic,
    "modules": [],
    "files": records,
}
(work / "checker-observation.json").write_text(json.dumps(observation))
sys.exit(status)
"""

_BOOTSTRAP = (
    "import runpy,sys; runpy.run_path(sys.argv[1] + '/checker/worker.py', run_name='__main__')"
)


def sha(raw: bytes) -> str:
    """Return the lowercase SHA-256 of complete bytes.

    Parameters
    ----------
    raw
        Complete file bytes.

    Returns
    -------
    str
        Hexadecimal digest.
    """
    return hashlib.sha256(raw).hexdigest()


def simulation_file(name: str) -> bytes:
    """Return one original simulation file after verifying its recorded digest.

    Parameters
    ----------
    name
        Original acquisition file name.

    Returns
    -------
    bytes
        Exact original bytes.
    """
    document = json.loads((_DATA / "neural-simulation-original.json").read_text(encoding="utf-8"))
    item = document["files"][name]
    raw = base64.b64decode(item["base64"]) if "base64" in item else item["text"].encode("ascii")
    assert sha(raw) == item["sha256"]
    return raw


def _epoch(raw: bytes, epoch: int) -> bytes:
    """Rewrite the epoch column of an original trace.

    Parameters
    ----------
    raw
        Original epoch-0 trace.
    epoch
        Declared epoch.

    Returns
    -------
    bytes
        Trace whose rows carry the declared epoch.
    """
    lines = raw.decode("ascii").splitlines()
    return "".join(f"{epoch} {line.split(' ', 1)[1]}\n" for line in lines).encode("ascii")


def _sources() -> dict[str, bytes]:
    """Return the complete test-owned source population.

    Returns
    -------
    dict[str, bytes]
        Acquisition path to source bytes.
    """
    sources = {
        name: f"// test-owned stand-in for {name}\n".encode()
        for name in (
            *_RTL,
            "native/native_trial.cpp",
            "native/capture_receipts.h",
            f"{_SC}hdl/tb_sc_lif_neuron.v",
        )
    }
    for name in (
        "src/sc_neurocore/neurons/fixed_point_lif.py",
        "src/sc_neurocore/constants.py",
        "tests/test_cosim_gen_and_check.py",
    ):
        sources[_SC + name] = f"# test-owned stand-in for {name}\n".encode()
    sources[ENTRY] = CHECKER.encode()
    sources[REFERENCE] = simulation_file("results_expected.txt")
    sources["stimuli.txt"] = simulation_file("stimuli.txt")
    return sources


@dataclass(frozen=True, slots=True)
class NeuralAcquisition:
    """A written acquisition and the registry that admits it.

    Attributes
    ----------
    manifest
        Root manifest path.
    directory
        Acquisition root.
    image
        Extracted checker image selected by the consumer.
    entry
        Reviewed policy, checker policy and executor.
    """

    manifest: Path
    directory: Path
    image: Path
    entry: NeuralEntry

    @property
    def registry(self) -> NeuralRegistry:
        """Return the consumer registry that admits only this acquisition.

        Returns
        -------
        NeuralRegistry
            One reviewed entry keyed by the exact source-contract digest.
        """
        policy, checker, executor = self.entry
        key = (NEURAL_SCHEMA_ID, NEURAL_SCHEMA_SHA256, PUBLIC_COHORT, sha(policy))
        factory: Callable[[], NeuralEntry] = lambda: (policy, checker, executor)  # noqa: E731
        return {key: factory}


class _Writer:
    """Write acquisition files and return their closed references."""

    def __init__(self, root: Path, change: Change | None) -> None:
        """Select the acquisition root and an optional deliberate file change.

        Parameters
        ----------
        root
            Empty acquisition directory.
        change
            Rewrites a file's bytes before it is written and referenced.
        """
        self.root = root
        self.change = change

    def put(self, name: str, raw: bytes) -> dict[str, Any]:
        """Write one file and return its reference.

        Parameters
        ----------
        name
            Within-run path.
        raw
            Complete bytes.

        Returns
        -------
        dict[str, Any]
            Path, digest and length.
        """
        if self.change is not None:
            raw = self.change(name, raw)
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return {"path": name, "sha256": sha(raw), "byte_length": len(raw)}

    def json(self, name: str, value: dict[str, Any]) -> dict[str, Any]:
        """Write canonical JSON and return its reference.

        Parameters
        ----------
        name
            Within-run path.
        value
            JSON object.

        Returns
        -------
        dict[str, Any]
            Path, digest and length.
        """
        return self.put(name, canonical_json_bytes(value))


def _image(root: Path, sources: dict[str, bytes], checker_sources: tuple[str, ...]) -> bytes:
    """Write the checker image and return its executor binding.

    Parameters
    ----------
    root
        Empty image root.
    sources
        Complete source population.
    checker_sources
        Acquisition paths of the checker closure.

    Returns
    -------
    bytes
        Canonical executor binding.
    """
    contents = {"checker/worker.py": _WORKER.encode()}
    contents.update({name: sources[name] for name in checker_sources})
    files, directories = _write_image_files(root, contents)
    binding = {
        "schema_id": IMAGE_EXECUTOR_SCHEMA,
        "supplier": {"name": "test image"},
        "historical_contracts": {},
        "command": [
            sys.executable,
            "-I",
            "-B",
            "-c",
            _BOOTSTRAP,
            "{image_root}",
            "{work_directory}",
            "{operation}",
        ],
        "bootstrap_environment": {"LANG": "C.UTF-8"},
        "deadline_seconds": 60,
        "host_boundary": {
            "system": platform.system(),
            "machine": platform.machine(),
            "kernel_release": platform.release(),
            "uid": os.getuid(),
            "gid": os.getgid(),
            "files": [],
            "absent_paths": [],
        },
        "image": {"files": files, "directories": sorted(directories), "symlinks": []},
        "source_files": list(checker_sources),
        "worker_files": ["checker/worker.py"],
    }
    return canonical_json_bytes(binding)


def _write_image_files(
    root: Path, contents: dict[str, bytes]
) -> tuple[list[dict[str, Any]], set[str]]:
    """Write read-only image files and return their records and parent directories.

    Parameters
    ----------
    root
        Image root.
    contents
        File bytes by image path.

    Returns
    -------
    tuple[list[dict[str, Any]], set[str]]
        Path, digest, length and mode of each file in path order, and every parent
        directory.
    """
    files = []
    directories: set[str] = set()
    for name, raw in sorted(contents.items()):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        path.chmod(0o444)
        files.append({"path": name, "sha256": sha(raw), "byte_length": len(raw), "mode": 0o444})
        directories.update(parent.as_posix() for parent in Path(name).parents if parent.parts)
    return files, directories


def _runtime(image: Path) -> bytes:
    """Return the historical runtime contract of the test image.

    Parameters
    ----------
    image
        Written image root.

    Returns
    -------
    bytes
        Canonical runtime contract.
    """
    worker = (image / "checker/worker.py").read_bytes()
    reviewed = json.loads(
        (_PACKAGE / "data/neural-image-checker-runtime.json").read_text(encoding="utf-8")
    )
    return canonical_json_bytes(
        {
            **{
                name: reviewed[name]
                for name in ("interpreter", "tracer", "import_namespaces", "platform_baseline")
            },
            "schema_id": "loop-timing-witness.sc-checker-runtime.v1",
            "files": [
                {"path": "checker/worker.py", "sha256": sha(worker), "byte_length": len(worker)}
            ],
            "worker_sources": [],
            "execution_contract": _EXECUTION_CONTRACT,
        }
    )


def _inventory(
    writer: _Writer, name: str, roles: dict[str, dict[str, Any]], prefix: str
) -> dict[str, Any]:
    """Write one observed inventory over the reviewed roles.

    Parameters
    ----------
    writer
        Acquisition writer.
    name
        Within-run inventory path.
    roles
        Reviewed role references keyed by path.
    prefix
        Actual installation prefix recorded for each role.

    Returns
    -------
    dict[str, Any]
        Inventory reference.
    """
    files = [{**reference, "actual_path": prefix + path} for path, reference in roles.items()]
    return writer.json(
        name, {"schema_id": "loop-timing-witness.checker-observed-inventory.v1", "files": files}
    )


def _checker_receipt(
    writer: _Writer,
    operation: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Write one original checker invocation and its referenced files.

    Parameters
    ----------
    writer
        Acquisition writer.
    operation
        Fixed checker operation.
    context
        References shared by both invocations.

    Returns
    -------
    dict[str, Any]
        Invocation receipt reference.
    """
    base = f"checker/{operation}/"
    data, observed = _checker_files(writer, base)
    environment = {**checker_environment(writer.root.resolve()), "TMPDIR": "/work"}
    receipt = {
        "schema_id": "loop-timing-witness.sc-checker-execution.v1",
        "source_contract_ref": context["source_contract_ref"],
        "checker_policy_ref": context["checker_policy_ref"],
        "operation": operation,
        "actual_argv": ["/image/" + ENTRY, *(_GENERATE if operation == "generate" else _CHECK)],
        "environment_ref": writer.json(base + "environment.json", environment),
        "inputs": {**data, "observed": observed} if operation == "check" else {},
        "outputs": data if operation == "generate" else {},
        "observed_source_inventory_ref": _inventory(
            writer, base + "source-inventory.json", context["source_roles"], "/image/"
        ),
        "observed_runtime_inventory_ref": _inventory(
            writer, base + "runtime-inventory.json", context["runtime_roles"], "/image/"
        ),
        "stdout_ref": writer.put(base + "checker.stdout", b"done\n"),
        "stderr_ref": writer.put(base + "checker.stderr", b""),
        "native_returncode": 0,
        "started_ns": 1_000_000_000,
        "completed_ns": 2_000_000_000,
        "elapsed_ns": 1_000_000_000,
        "cleanup": "reaped",
    }
    return writer.json(base + "execution.json", receipt)


def _checker_files(writer: _Writer, base: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Write one invocation's stimuli, reference and observed projection.

    Parameters
    ----------
    writer
        Acquisition writer.
    base
        Invocation directory within the run.

    Returns
    -------
    tuple[dict[str, dict[str, Any]], dict[str, Any]]
        Stimuli and reference references, and the observed projection reference.
    """
    data = {
        "stimuli": writer.put(base + "stimuli.txt", simulation_file("stimuli.txt")),
        "reference": writer.put(
            base + "results_expected.txt", simulation_file("results_expected.txt")
        ),
    }
    return data, writer.put(
        base + "results_verilog.txt", simulation_file("observed-projection.txt")
    )


def _native_runtime(
    writer: _Writer, epoch: int, source_files: list[dict[str, Any]], artifacts: dict[str, Any]
) -> dict[str, Any]:
    """Write the native build and execution receipt.

    Parameters
    ----------
    writer
        Acquisition writer.
    epoch
        Declared epoch.
    source_files
        Root source references.
    artifacts
        Compiled artifact references of this epoch.

    Returns
    -------
    dict[str, Any]
        Native runtime receipt reference.
    """
    actual = {f"/build/{item['path']}": item["path"] for item in source_files}
    jobs = _native_jobs(writer, epoch)
    return writer.json(
        "native-runtime.json",
        {
            "scope": "test-owned native receipt",
            "backend": "verilator-native-cpp",
            "dialect": "1800-2012",
            "epoch": epoch,
            "steps": 1000,
            "parameters": {
                "EXTRA_STATE_REGISTER": 0,
                "TIMESTAMP_OFFSET": 0,
                "DROP_ENCODER_FEED": 0,
                "ADDRESS_BITS": 10,
            },
            "tool_versions": {"verilator": "test-verilator", "g++": "test-g++"},
            "source_files": source_files,
            "actual_source_paths": actual,
            "jobs": jobs,
            "compiled_artifacts": artifacts,
            "runtime_object_source_scope": "test-owned objects",
        },
    )


def _native_jobs(writer: _Writer, epoch: int) -> list[dict[str, Any]]:
    """Write the build and execution logs and return the native jobs.

    Parameters
    ----------
    writer
        Acquisition writer.
    epoch
        Declared epoch, selecting the original or reset execution.

    Returns
    -------
    list[dict[str, Any]]
        Elaboration, archive, compile and link jobs, then the execution.
    """
    jobs: list[dict[str, Any]] = [
        {
            "kind": kind,
            "command": list(command),
            "returncode": 0,
            "log": writer.put(f"build-logs/job-{index}.log", b""),
        }
        for index, (kind, command) in enumerate(_NATIVE_BUILD)
    ]
    jobs.append(
        {
            "kind": "native_execution",
            "command": ["native_trial", "original" if epoch == 0 else "reset"],
            "returncode": 0,
            "stdout": writer.put("stdout.log", b"NATIVE_JOINT_EXPORT_COMPLETE\n"),
            "stderr": writer.put("stderr.log", b""),
        }
    )
    return jobs


def _reset(writer: _Writer) -> dict[str, Any]:
    """Write the reset receipt and the four abandoned prefix traces.

    Parameters
    ----------
    writer
        Acquisition writer.

    Returns
    -------
    dict[str, Any]
        Tool-receipt fields for the reset roles.
    """
    prefixes = {
        "input": (b"".join(simulation_file("input.txt").splitlines(keepends=True)[:4])),
        "numerical": (b"".join(simulation_file("numerical.txt").splitlines(keepends=True)[:3])),
        "raw_spike": (b"".join(simulation_file("raw-spikes.txt").splitlines(keepends=True)[:3])),
        "service": b"",
    }
    receipt = {
        "abandoned_epoch": 0,
        "next_epoch": 1,
        "prefix_inputs": 4,
        "prefix_states": 3,
        "prefix_raw_rows": 3,
        "prefix_raw_spikes": 1,
        "prefix_services": 0,
        "counter_before_reset": 24,
        "uncommitted_input_records_before_reset": 1,
        "reset_counter": 0,
        "reset_service_ordinal": 0,
        "encoder_pending_before_reset": True,
        "all_three_fifos_queued_before_reset": True,
        "all_three_fifos_empty_after_reset": True,
        "model_and_encoder_quiescent_after_reset": True,
        "prefix_attempts": [4, 3, 1],
        "prefix_accepted": [4, 3, 1],
        "reset_attempts": [0, 0, 0],
        "reset_accepted": [0, 0, 0],
    }
    return {
        "reset_epoch_receipt": writer.json("reset-epoch.json", receipt),
        "abandoned_prefix_traces": {
            name: writer.put(f"prefix/{name}.txt", raw) for name, raw in prefixes.items()
        },
    }


def build_neural_acquisition(
    root: Path,
    *,
    epoch: int = 0,
    installation: NeuralCheckerInstallation | None = None,
    change: Change | None = None,
    program: bytes | None = None,
) -> NeuralAcquisition:
    """Write a complete passing acquisition, its checker image and registry entry.

    Parameters
    ----------
    root
        Empty owned directory; the acquisition and image become subdirectories.
    epoch
        Zero for the original run, one for the run after the joint reset.
    installation
        Reviewed host installation; the test image executor when omitted.
    change
        Deliberate rewrite of named file bytes; the registry adopts changed policies.
    program
        Replacement source checker program, bound consistently everywhere.

    Returns
    -------
    NeuralAcquisition
        Manifest, image and reviewed entry.
    """
    writer = _Writer(root / "acquisition", change)
    image_root = root / "image"
    sources = _sources()
    if program is not None:
        sources[ENTRY] = program
    source_files = [writer.put(name, raw) for name, raw in sorted(sources.items())]
    binding = _image(image_root, sources, _CHECKER_SOURCES)
    runtime = _runtime(image_root) if installation is None else installation.contract_bytes()
    by_path = {item["path"]: item for item in source_files}
    checker_ref, checker_policy = _write_checker_policy(writer, by_path, runtime)
    compiled = _write_compiled(writer)
    contract_ref, policy = _write_source_contract(writer, source_files, compiled, checker_ref)
    executor = (
        ImageCheckerExecutor(image_root, binding, runtime) if installation is None else installation
    )
    context = _checker_context(contract_ref, checker_ref, by_path, executor)
    clock_ref = _write_clock(writer, sources)
    traces = _write_traces(writer, epoch, clock_ref)
    written = _Written(source_files, by_path, compiled, contract_ref, context, clock_ref, traces)
    tool = _write_tool_receipt(writer, epoch, sources, written)
    path = _write_manifest(writer, epoch, sources, written, tool)
    return NeuralAcquisition(path, writer.root, image_root, (policy, checker_policy, executor))


def _checker_context(
    contract_ref: dict[str, Any],
    checker_ref: dict[str, Any],
    by_path: dict[str, dict[str, Any]],
    executor: ImageCheckerExecutor | NeuralCheckerInstallation,
) -> dict[str, Any]:
    """Return the references both checker invocations share.

    Parameters
    ----------
    contract_ref, checker_ref
        Source contract and checker policy references.
    by_path
        Root source references by path.
    executor
        Image executor or reviewed host installation, naming its runtime roles.

    Returns
    -------
    dict[str, Any]
        Contract and policy references with the source and runtime roles.
    """
    return {
        "source_contract_ref": contract_ref,
        "checker_policy_ref": checker_ref,
        "source_roles": {name: by_path[name] for name in _CHECKER_SOURCES},
        "runtime_roles": executor.runtime_references(),
    }


@dataclass(frozen=True, slots=True)
class _Written:
    """References of the acquisition files written before the tool receipt.

    Attributes
    ----------
    source_files
        Root source references in path order.
    by_path
        The same references by path.
    compiled
        Compiled artifact references of both epochs.
    contract_ref
        Source contract reference.
    context
        References both checker invocations share.
    clock_ref
        Clock schedule reference.
    traces
        Trace and projection references with the clock schedule.
    """

    source_files: list[dict[str, Any]]
    by_path: dict[str, dict[str, Any]]
    compiled: dict[str, Any]
    contract_ref: dict[str, Any]
    context: dict[str, Any]
    clock_ref: dict[str, Any]
    traces: dict[str, Any]


def _write_checker_policy(
    writer: _Writer, by_path: dict[str, dict[str, Any]], runtime: bytes
) -> tuple[dict[str, Any], bytes]:
    """Write the checker runtime contract and the checker policy that binds it.

    Parameters
    ----------
    writer
        Acquisition writer.
    by_path
        Root source references by path.
    runtime
        Checker runtime contract bytes.

    Returns
    -------
    tuple[dict[str, Any], bytes]
        Checker policy reference and the policy bytes as written.
    """
    execution = json.loads(runtime)["execution_contract"]
    runtime_ref = writer.put("checker-runtime.json", runtime)
    checker_policy = canonical_json_bytes(
        {
            "schema_id": "loop-timing-witness.sc-checker-policy.v1",
            "entry_point": by_path[ENTRY],
            "source_files": [by_path[name] for name in _CHECKER_SOURCES],
            "runtime_contract_ref": runtime_ref,
            "generate_arguments": _GENERATE,
            "check_arguments": _CHECK,
            "execution_contract": execution,
        }
    )
    checker_ref = writer.put("checker-policy.json", checker_policy)
    return checker_ref, (writer.root / "checker-policy.json").read_bytes()


def _write_compiled(writer: _Writer) -> dict[str, Any]:
    """Write the compiled artifacts of both epochs.

    Parameters
    ----------
    writer
        Acquisition writer.

    Returns
    -------
    dict[str, Any]
        Artifact references by build key and name.
    """
    return {
        f"0,0,0,10:{index}": {
            name: writer.put(f"compiled/{index}/{name}", f"{name} {index}\n".encode())
            for name in _ARTIFACTS
        }
        for index in (0, 1)
    }


def _write_source_contract(
    writer: _Writer,
    source_files: list[dict[str, Any]],
    compiled: dict[str, Any],
    checker_ref: dict[str, Any],
) -> tuple[dict[str, Any], bytes]:
    """Write the source contract over the sources, compiled artifacts and checker policy.

    Parameters
    ----------
    writer
        Acquisition writer.
    source_files
        Root source references.
    compiled
        Compiled artifact references.
    checker_ref
        Checker policy reference.

    Returns
    -------
    tuple[dict[str, Any], bytes]
        Source contract reference and the contract bytes as written.
    """
    policy = canonical_json_bytes(
        {
            "schema_id": NEURAL_SCHEMA_ID,
            "schema_sha256": NEURAL_SCHEMA_SHA256,
            "cohort": PUBLIC_COHORT,
            "tool_versions": {"verilator": "test-verilator", "g++": "test-g++"},
            "sources": {
                item["path"]: {"sha256": item["sha256"], "byte_length": item["byte_length"]}
                for item in source_files
            },
            "compiled_artifacts": compiled,
            "checker_policy_ref": checker_ref,
        }
    )
    contract_ref = writer.put("source-contract.json", policy)
    return contract_ref, (writer.root / "source-contract.json").read_bytes()


def _write_clock(writer: _Writer, sources: dict[str, bytes]) -> dict[str, Any]:
    """Write the test-owned clock schedule, bound to the native producer source.

    Parameters
    ----------
    writer
        Acquisition writer.
    sources
        Complete source population.

    Returns
    -------
    dict[str, Any]
        Clock schedule reference.
    """
    native = sources["native/native_trial.cpp"]
    clock = {
        "capture_half_period_units": 5,
        "capture_horizon_edges": 4096,
        "dedicated_end_marker_tick": 1030,
        "dedicated_start_marker_tick": 10,
        "drain_half_period_units": 5,
        "driver_half_period_precision_ticks": 5000,
        "expected_state_observation_offset_ticks": 1,
        "first_input_tick": 20,
        "observed_final_counter": json.loads(simulation_file("completion.json"))["final_counter"],
        "requested_contiguous_steps": 1000,
        "scope": "test-owned clock schedule",
        "simulation_time_precision": "1ps",
        "simulation_time_unit": "1ns",
        "source_producer": {
            "path": "native/native_trial.cpp",
            "sha256": sha(native),
            "byte_length": len(native),
        },
        "tail_checked_after_edge_tick": 1023,
    }
    return writer.json("clock-schedule.json", clock)


def _write_traces(writer: _Writer, epoch: int, clock_ref: dict[str, Any]) -> dict[str, Any]:
    """Write the epoch's input, numerical and service traces and both projections.

    Parameters
    ----------
    writer
        Acquisition writer.
    epoch
        Declared epoch.
    clock_ref
        Clock schedule reference.

    Returns
    -------
    dict[str, Any]
        Manifest trace fields.
    """
    return {
        "input_trace": writer.put("input.txt", _epoch(simulation_file("input.txt"), epoch)),
        "numerical_trace": writer.put(
            "numerical.txt", _epoch(simulation_file("numerical.txt"), epoch)
        ),
        "service_trace": writer.put("service.txt", _epoch(simulation_file("service.txt"), epoch)),
        "numerical_projection": writer.put(
            "observed-projection.txt", simulation_file("observed-projection.txt")
        ),
        "reference_projection": writer.put(
            "results_expected.txt", simulation_file("results_expected.txt")
        ),
        "clock_schedule_ref": clock_ref,
    }


def _model_checker(sources: dict[str, bytes]) -> dict[str, Any]:
    """Return the source-owned public model checker record.

    Parameters
    ----------
    sources
        Complete source population.

    Returns
    -------
    dict[str, Any]
        Rows, spikes and the digests of its inputs, model and constants.
    """
    return {
        "rows": 1000,
        "spikes": 54,
        "original_input_sha256": sha(simulation_file("stimuli.txt")),
        "reference_sha256": sha(simulation_file("results_expected.txt")),
        "actual_projection_sha256": sha(simulation_file("observed-projection.txt")),
        "model_module": "sc_neurocore.neurons.fixed_point_lif",
        "model_sha256": sha(sources[f"{_SC}src/sc_neurocore/neurons/fixed_point_lif.py"]),
        "constants_module": "sc_neurocore.constants",
        "constants_sha256": sha(sources[f"{_SC}src/sc_neurocore/constants.py"]),
        "source_owned_public_checker_pass": True,
    }


def _write_tool_receipt(
    writer: _Writer, epoch: int, sources: dict[str, bytes], written: _Written
) -> dict[str, Any]:
    """Write the checker, native, model, counter, spike and completion receipts.

    Parameters
    ----------
    writer
        Acquisition writer.
    epoch
        Declared epoch; epoch one adds the reset receipt and prefix traces.
    sources
        Complete source population.
    written
        References written before the tool receipt.

    Returns
    -------
    dict[str, Any]
        Tool receipt, written later with the manifest.
    """
    return {
        "schema_id": "loop-timing-witness.neural-tool-receipt.v1",
        "scope": "test-owned acquisition",
        "checker_receipts": {
            "generation": _checker_receipt(writer, "generate", written.context),
            "check": _checker_receipt(writer, "check", written.context),
        },
        "compiler_simulator_runtime": _native_runtime(
            writer, epoch, written.source_files, written.compiled[f"0,0,0,10:{epoch}"]
        ),
        "source_owned_public_model_checker": writer.json(
            "original-model-checker.json", _model_checker(sources)
        ),
        "counter_receipt": writer.put(
            "capture-counts.json", simulation_file("capture-counts.json")
        ),
        "raw_spike_trace": writer.put(
            "raw-spikes.txt", _epoch(simulation_file("raw-spikes.txt"), epoch)
        ),
        "original_stimulus": written.by_path["stimuli.txt"],
        "actual_completion": writer.put("completion.json", simulation_file("completion.json")),
        "existing_trial_analysis": writer.json("export-verification.json", {"test": True}),
        "declared_clock_schedule": written.clock_ref,
        **(_reset(writer) if epoch else {}),
    }


def _write_manifest(
    writer: _Writer,
    epoch: int,
    sources: dict[str, bytes],
    written: _Written,
    tool: dict[str, Any],
) -> Path:
    """Write the channel captures, the tool receipt and the run manifest.

    Parameters
    ----------
    writer
        Acquisition writer.
    epoch
        Declared epoch.
    sources
        Complete source population.
    written
        References written before the tool receipt.
    tool
        Tool receipt.

    Returns
    -------
    Path
        Written ``run.json``.
    """
    template = json.loads((_DATA / "neural-selected-original.run.json").read_text(encoding="utf-8"))
    channels = _write_channels(writer, template["channels"])
    manifest = {
        **template,
        "run_id": f"test-epoch-{epoch}",
        "epoch": epoch,
        "source_files": written.source_files,
        "sc_body_pins": {name: sha(sources[_SC + name]) for name in BODY_PINS},
        "tool_receipt": writer.json("tool-receipt.json", tool),
        **written.traces,
        "channels": channels,
        "source_contract_ref": written.contract_ref,
    }
    writer.json("run.json", manifest)
    return writer.root / "run.json"


def _write_channels(writer: _Writer, declarations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Write each channel's capture, payload and markers and add them to its declaration.

    Parameters
    ----------
    writer
        Acquisition writer.
    declarations
        Channel declarations of the template, in order.

    Returns
    -------
    list[dict[str, Any]]
        Declarations with their capture, payload and marker references.
    """
    channels = []
    for index, declaration in enumerate(declarations):
        channels.append(
            {
                **declaration,
                **{
                    role: writer.put(f"{stem}-{index}.bin", simulation_file(f"{stem}-{index}.bin"))
                    for role, stem in (
                        ("capture", "channel"),
                        ("payload", "payload"),
                        ("markers", "markers"),
                    )
                },
            }
        )
    return channels


def _installed(name: str, path: Path) -> CheckerInstalledFile:
    """Bind one actual host file by its complete bytes.

    Parameters
    ----------
    name
        Logical runtime name.
    path
        Actual resolved file.

    Returns
    -------
    CheckerInstalledFile
        Complete identity of the file.
    """
    raw = path.read_bytes()
    return CheckerInstalledFile(name, path, sha(raw), len(raw))


def _host(root: Path, runtime: tuple[Path, ...]) -> NeuralCheckerInstallation:
    """Select the running interpreter, the actual tracer and extra runtime files.

    Parameters
    ----------
    root
        Existing import root for the checker.
    runtime
        Further files the interpreter opens.

    Returns
    -------
    NeuralCheckerInstallation
        Host installation on the current platform.
    """
    tracer = shutil.which("strace")
    assert tracer is not None
    interpreter = _installed("interpreter/python", Path(sys.executable).resolve())
    strace = _installed("tracer/strace", Path(tracer).resolve())
    files = (
        interpreter,
        strace,
        *(_installed(f"runtime/{index}", path) for index, path in enumerate(runtime)),
    )
    return NeuralCheckerInstallation(
        interpreter, strace, files, (root,), platform.platform(), platform.release()
    )


def checker_runs(root: Path) -> tuple[NeuralCheckerInstallation, Path, list[tuple[Path, bytes]]]:
    """Run the real traced checker for both operations on a minimal host installation.

    Parameters
    ----------
    root
        Empty owned directory for the runs.

    Returns
    -------
    tuple[NeuralCheckerInstallation, Path, list[tuple[Path, bytes]]]
        The minimal installation, the frozen source closure, and each run's
        working directory with its complete trace.
    """
    sources = _sources()
    closure = root / "closure"
    for name in (ENTRY, REFERENCE, "stimuli.txt"):
        (closure / name).parent.mkdir(parents=True, exist_ok=True)
        (closure / name).write_bytes(sources[name])
    minimal = _host(root, ())
    runs = []
    for operation in ("generate", "check"):
        directory = root / operation
        directory.mkdir()
        (directory / "results_verilog.txt").write_bytes(simulation_file("observed-projection.txt"))
        invocation = invoke_source_checker(minimal, closure / ENTRY, operation, directory)
        assert invocation.returncode == 0, invocation.stderr
        runs.append((directory, invocation.trace))
    return minimal, closure, runs


def calibrated_host_installation(root: Path) -> NeuralCheckerInstallation:
    """Select every host file the real traced checker opens, as a consumer review would.

    Parameters
    ----------
    root
        Empty owned directory for the calibration runs.

    Returns
    -------
    NeuralCheckerInstallation
        Host installation whose inventory covers the observed runtime closure.
    """
    minimal, closure, runs = checker_runs(root)
    known = {item.path for item in (*minimal.files, *minimal.worker_files())}
    opened: set[Path] = set()
    for directory, trace in runs:
        data = {
            directory / name
            for name in (
                "stimuli.txt",
                "results_expected.txt",
                "results_verilog.txt",
                "checker-observation.json",
            )
        }
        opened |= checker_opened_files(trace, directory) - data
    runtime = sorted(opened - known - {path.resolve() for path in closure.rglob("*")})
    return _host(root, tuple(runtime))


def edit_json(target: str, edit: Callable[[Any], object]) -> Change:
    """Return a change that edits one JSON document in place.

    Parameters
    ----------
    target
        Within-run path of the document.
    edit
        Mutates the decoded value in place; its result is ignored.

    Returns
    -------
    Change
        Rewrite that leaves every other file unchanged.
    """

    def change(name: str, raw: bytes) -> bytes:
        """Edit the target document only.

        Parameters
        ----------
        name, raw
            File path and original bytes.

        Returns
        -------
        bytes
            Edited canonical JSON, or the original bytes.
        """
        if name != target:
            return raw
        value = json.loads(raw)
        edit(value)
        return canonical_json_bytes(value)

    return change


def replace_file(target: str, body: bytes) -> Change:
    """Return a change that replaces one file's bytes.

    Parameters
    ----------
    target
        Within-run path.
    body
        Replacement bytes.

    Returns
    -------
    Change
        Rewrite that leaves every other file unchanged.
    """
    return lambda name, raw: body if name == target else raw


def make_writable(root: Path) -> None:
    """Restore owner write permission so a test directory can be removed.

    Parameters
    ----------
    root
        Directory tree containing read-only image files.
    """
    for path in root.rglob("*"):
        if not path.is_symlink():
            path.chmod(path.stat().st_mode | stat.S_IWUSR)


def rebind_image(
    acquisition: NeuralAcquisition, edit: Callable[[dict[str, Any]], object]
) -> NeuralAcquisition:
    """Return the acquisition admitted by an image executor with an edited binding.

    The binding belongs to the consumer, so the acquisition's own files stay
    unchanged; only the reviewed entry's executor is rebuilt.

    Parameters
    ----------
    acquisition
        Acquisition admitted by the test image executor.
    edit
        Mutates the decoded executor binding in place; its result is ignored.

    Returns
    -------
    NeuralAcquisition
        The same acquisition with the rebuilt executor.
    """
    policy, checker, executor = acquisition.entry
    assert isinstance(executor, ImageCheckerExecutor)
    binding = json.loads(executor.binding_bytes)
    edit(binding)
    rebuilt = ImageCheckerExecutor(
        executor.image_root, canonical_json_bytes(binding), executor.runtime_bytes
    )
    return replace(acquisition, entry=(policy, checker, rebuilt))
