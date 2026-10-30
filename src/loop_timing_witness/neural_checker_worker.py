# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — isolated source-owned numerical checker worker

"""Run one fixed source-owned checker operation in a finite isolated child process."""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import sys
import time
from pathlib import Path

from .neural_checker_isolation import isolate_checker

_MAP_FIELDS = 6
_OBSERVED_FILE_LIMIT = 256 * 1024 * 1024


class CheckerWorkerError(RuntimeError):
    """An unexpected checker failure whose public diagnostic is deliberately fixed."""


def _observed_files(script: str) -> dict[str, list[dict[str, object]]]:
    """Record actual loaded module and mapped-file identities after execution.

    Parameters
    ----------
    script
        Actual source-owned program entry point.

    Returns
    -------
    dict[str, list[dict[str, object]]]
        Full observed module and mapped regular-file records, not a platform attestation.
    """
    modules: list[dict[str, object]] = []
    paths = {Path(script).resolve()}
    for name, module in sorted(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if isinstance(filename, str) and Path(filename).is_file():
            path = Path(filename).resolve()
            paths.add(path)
            modules.append({"name": name, "path": str(path)})
    for line in Path("/proc/self/maps").read_text(encoding="ascii").splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) == _MAP_FIELDS and fields[5].startswith("/"):
            path = Path(fields[5]).resolve()
            if path.is_file():
                paths.add(path)
    records = []
    for path in sorted(paths):
        if path.stat().st_size > _OBSERVED_FILE_LIMIT:
            message = "Observed checker runtime file exceeds its allocation."
            raise CheckerWorkerError(message)
        raw = path.read_bytes()
        records.append(
            {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "byte_length": len(raw)}
        )
    return {"modules": modules, "files": records}


def main(argv: list[str] | None = None) -> int:
    """Execute a source checker operation and retain actual process observations.

    Parameters
    ----------
    argv
        Parent-owned script path, operation and reviewed import roots. The full
        verifier constructs this vector after immutable source admission;
        acquisition receipt arguments are never executed.

    Returns
    -------
    int
        Source-owned checker status, or one for an unavailable worker boundary.

    Raises
    ------
    CheckerWorkerError
        If execution fails unexpectedly; the command prints only authored text.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script")
    parser.add_argument("operation", choices=("generate", "check"))
    parser.add_argument("import_roots", nargs="*")
    args = parser.parse_args(argv)
    started = time.time_ns()
    monotonic = time.monotonic_ns()
    status = 1
    phase = "refused"
    source_argv = [args.script, f"--{args.operation}", "--steps", "1000", "--seed", "42"]
    try:
        isolate_checker()
        sys.path[:0] = args.import_roots
        sys.argv = source_argv
        phase = "source"
        runpy.run_path(args.script, run_name="__main__")
        status = 0
    except SystemExit as exc:
        status = exc.code if type(exc.code) is int else 1
    except (OSError, ValueError):
        print("Source checker execution or isolation was refused.", file=sys.stderr)
        status = 1
    except Exception as exc:
        message = "Source checker execution failed."
        raise CheckerWorkerError(message) from exc
    finally:
        observation = {
            "schema_id": "loop-timing-witness.sc-checker-worker-observation.v1",
            "operation": args.operation,
            "actual_argv": source_argv,
            "native_returncode": status,
            "phase": phase,
            "started_ns": started,
            "completed_ns": time.time_ns(),
            "elapsed_ns": time.monotonic_ns() - monotonic,
            **_observed_files(args.script),
        }
        Path("checker-observation.json").write_text(json.dumps(observation), encoding="utf-8")
    return status


if __name__ == "__main__":
    try:
        result = main()
    except (CheckerWorkerError, OSError, ValueError):
        print("Source checker execution failed.", file=sys.stderr)
        result = 1
    sys.exit(result)
