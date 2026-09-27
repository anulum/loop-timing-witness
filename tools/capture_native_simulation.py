# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — source-bound native simulation capture command

"""Snapshot, compile and run the native controller against production RTL."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from analyze_run import build_report
from linux_load import LoadExecution, execute_with_load
from linux_load_config import PROFILES, LoadConfiguration
from native_simulation_manifest import native_metadata, write_native_manifest
from native_source_snapshot import snapshot_native_sources
from report_outputs import write_report
from run_manifest import load_run

from manifest_io import canonical_json_bytes

ROOT = Path(__file__).resolve().parents[1]
MAX_FIFO_ADDRESS_BITS = 14


@dataclass(frozen=True)
class CaptureOptions:
    """Build capacity and optional real host load for a source-bound capture.

    Parameters
    ----------
    fifo_address_bits
        Actual compiled FIFO log2 capacity, between one and fourteen.
    host_load
        Explicit bounded worker request, or no extra host workload.
    """

    fifo_address_bits: int = 8
    host_load: LoadConfiguration | None = None


def capture_simulation(
    configuration: Path,
    output: Path,
    thermal: int,
    native_arguments: list[str] | None = None,
    options: CaptureOptions | None = None,
) -> Path:
    """Compile a frozen source snapshot and retain real binary events and reports.

    Parameters
    ----------
    configuration
        Complete native whitespace run configuration.
    output
        New run directory; failed builds/runs retain their evidence here.
    thermal
        Actual compile-time plant mode, zero or one.
    native_arguments
        Explicit native CPU/scheduler options; parsed and checked by the actual executable.
    options
        Actual FIFO build capacity and optional bounded host workload.

    Returns
    -------
    Path
        New validated hash-bound manifest.

    Raises
    ------
    OSError
        If an artifact cannot be read, copied or created.
    ValueError
        If native output contradicts the actual decoded capture.
    subprocess.CalledProcessError
        If a real compiler or native run fails.
    """
    options = options or CaptureOptions()
    fifo_address_bits = options.fifo_address_bits
    if options.host_load is not None:
        options.host_load.validate()
    if thermal not in (0, 1):
        message = "thermal must be zero or one"
        raise ValueError(message)
    if not 1 <= fifo_address_bits <= MAX_FIFO_ADDRESS_BITS:
        message = "FIFO address bits must be in [1,14]"
        raise ValueError(message)
    config_bytes = configuration.read_bytes()
    output.mkdir()
    source = output / "source"
    snapshots = snapshot_native_sources(ROOT, output, host_load=options.host_load is not None)
    (output / "configuration.txt").write_bytes(config_bytes)
    (output / "build_parameters.json").write_bytes(
        canonical_json_bytes(
            {
                "fifo_address_bits": fifo_address_bits,
                "group_address_bits": 4,
                "period_ticks": 32768,
                "thermal": thermal,
            }
        )
    )
    shutil.copyfile(ROOT / "measurement-domain.json", output / "measurement-domain.json")
    versions = {}
    for tool in ["verilator", "gcc", "g++", "make"]:
        versions[tool] = subprocess.run(
            [tool, "--version"], check=True, text=True, capture_output=True, timeout=10
        ).stdout.splitlines()[0]
    (output / "build_versions.json").write_bytes(canonical_json_bytes(versions))
    with (output / "build.log").open("wb") as log:
        subprocess.run(
            [
                "make",
                "run-simulation",
                f"SIMULATION_THERMAL={thermal}",
                f"SIMULATION_FIFO_ADDRESS_BITS={fifo_address_bits}",
            ],
            cwd=source,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=90,
        )
    binary = source / f"build/run_simulation_{thermal}/run_simulation"
    started = datetime.now(UTC).isoformat()
    with (output / "native.log").open("wb") as log:
        command = [
            str(binary.resolve()),
            str((output / "configuration.txt").resolve()),
            str((output / "events.bin").resolve()),
            str((output / "tracking_raw.csv").resolve()),
            "--metadata",
            str((output / "native_metadata.json").resolve()),
            *(native_arguments or []),
        ]
        if options.host_load is None:
            native_result = subprocess.run(
                command, stdout=log, stderr=subprocess.STDOUT, check=False, timeout=120
            )
        else:
            native_result = execute_with_load(
                command,
                options.host_load,
                LoadExecution(
                    output / "host_load.json",
                    output / "host_load_workspace",
                    worker_path=source / "tools/linux_load_worker.py",
                ),
                log,
            )
            snapshots.extend(
                [output / "host_load.json", *(output / "host_load_workspace").glob("*")]
            )
    if native_result.returncode:
        native = native_metadata(output)
        if native_result.returncode != 1 or not native["result"]["overflow"]:
            native_result.check_returncode()
    manifest = write_native_manifest(
        output,
        started,
        [
            *snapshots,
            binary,
            *(
                output / name
                for name in [
                    "configuration.txt",
                    "build_versions.json",
                    "build_parameters.json",
                    "build.log",
                    "native.log",
                    "native_metadata.json",
                    "tracking_raw.csv",
                ]
            ),
        ],
        versions["verilator"],
    )
    inputs = load_run(manifest)
    report, rows = build_report(inputs)
    write_report(output / "reports", report, rows)
    return manifest


def _load_configuration(args: argparse.Namespace) -> LoadConfiguration | None:
    """Refuse incomplete capture load requests before output allocation.

    Parameters
    ----------
    args
        Parsed CLI namespace with profile, CPU and working-set options.

    Returns
    -------
    LoadConfiguration or None
        Complete explicit request, or no additional workload.
    """
    if args.load_profile is None and (
        args.load_cpu is not None or args.load_working_set_bytes is not None
    ):
        message = "load CPU and working set require --load-profile"
        raise ValueError(message)
    if args.load_profile is not None and args.load_cpu is None:
        message = "--load-profile requires an explicit --load-cpu"
        raise ValueError(message)
    return (
        None
        if args.load_profile is None
        else LoadConfiguration(
            args.load_profile,
            args.load_cpu,
            4096 if args.load_working_set_bytes is None else args.load_working_set_bytes,
        )
    )


def main(argv: list[str] | None = None) -> int:
    """Run source-bound native simulation capture from its public command line.

    Parameters
    ----------
    argv
        Arguments or process command line.

    Returns
    -------
    int
        Zero after validated capture/report, one after a retained failed run.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("configuration", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--thermal", choices=[0, 1], default=0, type=int)
    parser.add_argument("--fifo-address-bits", choices=range(1, 15), default=8, type=int)
    parser.add_argument("--cpu", type=int)
    parser.add_argument("--scheduler", choices=["normal", "fifo"])
    parser.add_argument("--priority", type=int)
    parser.add_argument("--load-profile", choices=PROFILES)
    parser.add_argument("--load-cpu", type=int)
    parser.add_argument("--load-working-set-bytes", type=int)
    args = parser.parse_args(argv)
    native_arguments = []
    for name in ["cpu", "scheduler", "priority"]:
        value = getattr(args, name)
        if value is not None:
            native_arguments.extend([f"--{name}", str(value)])
    try:
        host_load = _load_configuration(args)
        path = capture_simulation(
            args.configuration,
            args.output_dir,
            args.thermal,
            native_arguments,
            CaptureOptions(args.fifo_address_bits, host_load),
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"native capture: FAIL: {exc}", file=sys.stderr)
        return 1
    if native_metadata(path.parent)["result"]["overflow"]:
        print(f"native capture: INVALID: FIFO overflow; retained {path}", file=sys.stderr)
        return 1
    print(f"native capture: PASS: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
