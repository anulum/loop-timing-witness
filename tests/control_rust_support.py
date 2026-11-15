# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — control-run loading through both analysis implementations

"""Load one CONTROL or COMPUTE run through the Python and the native analysis.

Both outcomes have one shape: the loaded manifest, domain, input digests,
resolved directory, decoded events, events block and complete report, or the
refusal text. A refusal is compared as the command prints it, with unpaired
surrogates escaped.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from neural_rust_support import consumer

from loop_timing_witness.analyze_run import build_report, events_block
from loop_timing_witness.event_stream import Event, decode_events
from loop_timing_witness.host_profile import scaled
from loop_timing_witness.run_manifest import load_run

HANG_GUARD_SECONDS = 600
"""Policy hang guard for one child analysis: a stuck child fails its test instead of the run.

It is not a performance budget; no run is judged by its speed against it.
"""

# Writes python_outcome of a manifest, with optional root bytes, to an outcome file.
_OUTCOME_SCRIPT = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "from control_rust_support import python_outcome\n"
    "root = Path(sys.argv[2]).read_bytes() if sys.argv[3] == 'yes' else None\n"
    "Path(sys.argv[4]).write_text(json.dumps(python_outcome(Path(sys.argv[1]), root)))\n"
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from loop_timing_witness.run_manifest import RunInputs


def _printed(error: BaseException) -> str:
    """Return an exception's text as stderr prints it.

    Parameters
    ----------
    error
        Raised refusal.

    Returns
    -------
    str
        Text with unpaired surrogates as backslash escapes.
    """
    return str(error).encode("utf-8", "backslashreplace").decode("utf-8")


def python_outcome(manifest: Path, root: bytes | None = None) -> dict[str, Any]:
    """Load the run and decode its events through the Python analysis.

    Parameters
    ----------
    manifest
        Run manifest path.
    root
        Manifest bytes already read for the path, or ``None`` to read it.

    Returns
    -------
    dict[str, Any]
        Inputs and events, or ``{"refusal": text}``.
    """
    try:
        inputs = load_run(manifest, manifest_bytes=root)
    except (OSError, ValueError) as error:
        return {"refusal": _printed(error)}
    events, decoded, refusal = _decoded_events(inputs)
    summary, summary_refusal = _events_summary(inputs, events, refusal)
    report, report_refusal = _report_outcome(inputs)
    return {
        "manifest": inputs.manifest,
        "domain": inputs.domain,
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in inputs.files.items()},
        "directory": str(inputs.directory),
        "events": decoded,
        "events_refusal": refusal,
        "summary": summary,
        "summary_refusal": summary_refusal,
        "report": report,
        "report_refusal": report_refusal,
    }


def _decoded_events(
    inputs: RunInputs,
) -> tuple[tuple[Event, ...], list[list[object]] | None, str | None]:
    """Decode the run's events, or keep the decoder's refusal.

    Parameters
    ----------
    inputs
        Loaded run.

    Returns
    -------
    tuple[tuple[Event, ...], list[list[object]] | None, str | None]
        Events, their ``[name, cycle, ticks]`` rows and no refusal, or no events,
        ``None`` and the refusal text.
    """
    try:
        events = decode_events(
            inputs.files["events"],
            inputs.domain["design_contracts"],
            inputs.manifest["profile"],
            inputs.manifest["cycle_count"],
        )
    except ValueError as error:
        return (), None, _printed(error)
    return events, [[event.name, event.cycle, event.ticks] for event in events], None


def _events_summary(
    inputs: RunInputs, events: tuple[Event, ...], refusal: str | None
) -> tuple[dict[str, Any] | None, str | None]:
    """Return the events block and interval rows, or why they are absent.

    Parameters
    ----------
    inputs
        Loaded run.
    events
        Decoded events.
    refusal
        Decoder refusal, which the summary inherits.

    Returns
    -------
    tuple[dict[str, Any] | None, str | None]
        Block and ``[cycle, interval, ticks]`` rows, or ``None`` and the refusal.
    """
    if refusal is not None:
        return None, refusal
    try:
        block, rows = events_block(inputs.manifest, inputs.domain["design_contracts"], events)
    except ValueError as error:
        return None, _printed(error)
    return {
        "block": block,
        "rows": [[row["cycle"], row["interval"], row["ticks"]] for row in rows],
    }, None


def _report_outcome(inputs: RunInputs) -> tuple[dict[str, Any] | None, str | None]:
    """Return the complete report and its interval rows, or the report refusal.

    Parameters
    ----------
    inputs
        Loaded run.

    Returns
    -------
    tuple[dict[str, Any] | None, str | None]
        Report and ``[cycle, interval, ticks]`` rows, or ``None`` and the refusal.
    """
    try:
        built, report_rows = build_report(inputs)
    except (OSError, ValueError) as error:
        return None, _printed(error)
    rows_listed = [[row["cycle"], row["interval"], row["ticks"]] for row in report_rows]
    return {"report": built, "rows": rows_listed}, None


def python_outcome_under(
    manifest: Path, wrapper: Sequence[str], directory: Path, root: bytes | None = None
) -> dict[str, Any]:
    """Run :func:`python_outcome` in a child process under an argument-vector wrapper.

    Parameters
    ----------
    manifest
        Run manifest path.
    wrapper
        Leading argument vector, such as a fault-injecting tracer.
    directory
        Owned directory for the outcome file.
    root
        Manifest bytes already read for the path, or ``None``.

    Returns
    -------
    dict[str, Any]
        The child's outcome.
    """
    directory.mkdir(exist_ok=True)
    root_path = directory / "python-root.json"
    if root is not None:
        root_path.write_bytes(root)
    outcome = directory / "python-outcome.json"
    tests = Path(__file__).resolve().parent
    environment = {**os.environ, "PYTHONPATH": os.pathsep.join([str(tests), str(tests.parent)])}
    result = subprocess.run(
        [
            *wrapper,
            sys.executable,
            "-c",
            _OUTCOME_SCRIPT,
            str(manifest),
            str(root_path),
            "yes" if root is not None else "no",
            str(outcome),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=environment,
        timeout=scaled(HANG_GUARD_SECONDS),
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    loaded: dict[str, Any] = json.loads(outcome.read_text(encoding="utf-8"))
    return loaded


def rust_outcome(
    manifest: Path, directory: Path, root: bytes | None = None, wrapper: Sequence[str] = ()
) -> dict[str, Any]:
    """Load the run and decode its events through the native analysis.

    Parameters
    ----------
    manifest
        Run manifest path.
    directory
        Owned directory for the description and outcome, created when absent.
    root
        Manifest bytes already read for the path, or ``None`` to read it.
    wrapper
        Argument vector that runs the consumer under a host condition.

    Returns
    -------
    dict[str, Any]
        Inputs and events, or ``{"refusal": text}``.
    """
    environment = _spec_environment(manifest, directory, root)
    result = subprocess.run(
        [
            *wrapper,
            str(consumer()),
            "--exact",
            "control_run_acquisition",
            "--nocapture",
            "--test-threads=1",
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=environment,
        timeout=scaled(HANG_GUARD_SECONDS),
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    outcome: dict[str, Any] = json.loads((directory / "outcome.json").read_bytes())
    return outcome


def _spec_environment(manifest: Path, directory: Path, root: bytes | None) -> dict[str, str]:
    """Write the consumer's run description and return the environment that names it.

    Parameters
    ----------
    manifest
        Run manifest path.
    directory
        Owned directory for the description, the root bytes and the outcome, created
        when absent.
    root
        Manifest bytes already read for the path, or ``None``.

    Returns
    -------
    dict[str, str]
        This process's environment with the description and, when a profile
        directory is selected, the LLVM profile file pattern.
    """
    directory.mkdir(exist_ok=True)
    spec: dict[str, Any] = {
        "manifest": str(manifest),
        "outcome": str(directory / "outcome.json"),
        "root": None,
    }
    if root is not None:
        (directory / "root.json").write_bytes(root)
        spec["root"] = str(directory / "root.json")
    (directory / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    environment = {**os.environ, "CONTROL_RUN_SPEC": str(directory / "spec.json")}
    profiles = os.environ.get("WITNESS_RUST_PROFILE_DIRECTORY")
    if profiles:
        environment["LLVM_PROFILE_FILE"] = str(Path(profiles) / "registry-%p-%m.profraw")
    return environment


def canonical(outcome: dict[str, Any]) -> str:
    """Return one outcome as sorted JSON text, keeping integers apart from floats.

    Parameters
    ----------
    outcome
        Python or native outcome.

    Returns
    -------
    str
        Comparable text.
    """
    return json.dumps(outcome, sort_keys=True, ensure_ascii=True)


def python_command(
    arguments: Sequence[str],
    cwd: Path,
    wrapper: Sequence[str] = (),
    *,
    measured: bool = True,
    campaign: bool = False,
) -> dict[str, Any]:
    """Run the Python analysis or campaign command and return its status and printed text.

    Parameters
    ----------
    arguments
        Command arguments after the program name.
    cwd
        Working directory of the command.
    wrapper
        Leading argument vector that runs the command under a host condition.
    measured
        Whether a coverage run measures the command. Coverage starts and stops
        inside the command with directories and files of its own, so a command
        whose own system calls are counted for fault injection, or whose file
        size is limited, runs unmeasured.
    campaign
        Whether to run the repeat campaign command instead of the run analysis.

    Returns
    -------
    dict[str, Any]
        ``status``, ``stdout`` and ``stderr``.
    """
    module = (
        "loop_timing_witness.analyze_campaign" if campaign else "loop_timing_witness.analyze_run"
    )
    result = subprocess.run(
        [*wrapper, sys.executable, "-m", module, *arguments],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=_command_environment(measured=measured),
        timeout=scaled(HANG_GUARD_SECONDS),
        check=False,
    )
    return {"status": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def _command_environment(*, measured: bool) -> dict[str, str]:
    """Return the environment of a Python command run from the repository source tree.

    Parameters
    ----------
    measured
        Whether coverage measures the command; an unmeasured command drops the
        coverage variables.

    Returns
    -------
    dict[str, str]
        Environment with ``PYTHONPATH`` on the repository ``src``.
    """
    tests = Path(__file__).resolve().parent
    environment = {
        key: value
        for key, value in os.environ.items()
        if measured or not key.startswith(("COVERAGE_", "COV_CORE"))
    }
    environment["PYTHONPATH"] = str(tests.parent / "src")
    return environment


def rust_command(
    arguments: Sequence[str],
    cwd: Path,
    directory: Path,
    wrapper: Sequence[str] = (),
    file_size_limit: int | None = None,
) -> dict[str, Any]:
    """Run the native analysis command through the consumer and return its outcome.

    Parameters
    ----------
    arguments
        Command arguments after the program name.
    cwd
        Working directory of the command.
    directory
        Owned directory for the description and outcome, created when absent.
    wrapper
        Leading argument vector that runs the command under a host condition.
    file_size_limit
        Largest file, in bytes, the command may write, set by the consumer
        around the command only, or ``None``; the wrapper must ignore
        ``SIGXFSZ``.

    Returns
    -------
    dict[str, Any]
        ``status``, ``stdout`` and ``stderr``.
    """
    spec = {"arguments": list(arguments), "file_size_limit": file_size_limit}
    return _consumer_command("control_command", spec, cwd, directory, wrapper)


def rust_campaign_command(arguments: Sequence[str], cwd: Path, directory: Path) -> dict[str, Any]:
    """Run the native repeat campaign command through the consumer and return its outcome.

    Parameters
    ----------
    arguments
        Command arguments after the program name.
    cwd
        Working directory of the command.
    directory
        Owned directory for the description and outcome, created when absent.

    Returns
    -------
    dict[str, Any]
        ``status``, ``stdout`` and ``stderr``.
    """
    spec = {"arguments": list(arguments), "file_size_limit": None}
    return _consumer_command("campaign_command", spec, cwd, directory, ())


def _consumer_command(
    test: str, spec: dict[str, Any], cwd: Path, directory: Path, wrapper: Sequence[str]
) -> dict[str, Any]:
    """Run one command test of the consumer with its description and return the outcome.

    Parameters
    ----------
    test
        ``control_command`` or ``campaign_command``; the description is passed in
        the upper-case variable of that name with ``_SPEC`` appended.
    spec
        Arguments and file-size limit of the command.
    cwd
        Working directory of the command.
    directory
        Owned directory for the description and outcome, created when absent.
    wrapper
        Leading argument vector that runs the command under a host condition.

    Returns
    -------
    dict[str, Any]
        ``status``, ``stdout`` and ``stderr``.
    """
    directory.mkdir(exist_ok=True)
    described = {**spec, "outcome": str(directory / "command.json")}
    (directory / "command-spec.json").write_text(json.dumps(described), encoding="utf-8")
    environment = {**os.environ, f"{test.upper()}_SPEC": str(directory / "command-spec.json")}
    profiles = os.environ.get("WITNESS_RUST_PROFILE_DIRECTORY")
    if profiles:
        environment["LLVM_PROFILE_FILE"] = str(Path(profiles) / "registry-%p-%m.profraw")
    result = subprocess.run(
        [*wrapper, str(consumer()), "--exact", test, "--nocapture", "--test-threads=1"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=environment,
        timeout=scaled(HANG_GUARD_SECONDS),
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    outcome: dict[str, Any] = json.loads((directory / "command.json").read_bytes())
    return outcome
