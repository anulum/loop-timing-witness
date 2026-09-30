# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — verified dedicated-hart ISA capture command

"""Execute a verified original AMP image and retain actual logger completion and raw outputs."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from amp_build_toolchain import simulator_identity
from amp_capture_snapshot import snapshot_image
from amp_completion import completion_receipt, validate_capture
from amp_execution_custody import verify_execution
from amp_image_options import ImageRequest, add_image_arguments, image_request
from amp_platform import bind_platform
from amp_plugin_receipt import admit_plugin
from amp_plugin_snapshot import snapshot_plugin, validate_plugin_snapshot
from amp_run_input import read_amp_run
from amp_runtime_snapshot import snapshot_runtime
from amp_simulation_manifest import write_amp_manifest
from amp_spike_command import SpikePaths, SpikeTools, spike_command
from analyze_run import build_report
from device_tree_blob import decode_device_tree
from report_outputs import write_report
from run_manifest import load_run
from verify_amp_image import verify_image

from manifest_io import canonical_json_bytes, load_json_object, sha256_of_file

ROOT = Path(__file__).resolve().parents[1]
MAX_TIMEOUT_SECONDS = 3600


def capture_amp(
    image: Path, output: Path, request: ImageRequest, tools: SpikeTools, timeout: int
) -> Path:
    """Run actual Spike with source-bound immutable inputs and refuse incomplete final drain.

    Parameters
    ----------
    image
        Original prepared and compiled dedicated-hart ISA image.
    output
        New exclusive run directory; failed runs preserve their logs.
    request
        Original explicit RAM, PLIC, hart and stack selection.
    tools
        Actual installed simulator/plugin and explicit functional clock bounds.
    timeout
        Bounded host safety timeout in seconds; never an instruction-count exit substitute.

    Returns
    -------
    Path
        Successful hash-bound capture receipt, absent after any failed admission or run.

    Raises
    ------
    OSError
        If original artifacts, exclusive outputs or executable files cannot be accessed.
    ValueError
        If image, topology, completion or captured streams disagree.
    subprocess.SubprocessError
        If actual Spike fails or exceeds its host safety timeout.
    """
    if type(timeout) is not int or not 1 <= timeout <= MAX_TIMEOUT_SECONDS:
        message = "AMP host timeout must be an integer in [1,3600] seconds"
        raise ValueError(message)
    manifest = verify_image(image, image / "platform.dtb", image / "configuration.txt", request)
    admitted = load_json_object(manifest)
    if admitted["exit_mode"] != "isa_htif":
        message = "AMP ISA capture requires target HTIF completion, not a parked image"
        raise ValueError(message)
    tree = decode_device_tree((image / "platform.dtb").read_bytes())
    platform = bind_platform(tree, request.memory, request.device_path, request.plic)
    command = spike_command(
        tools,
        tree,
        platform,
        plic_path=request.plic.path,
        paths=SpikePaths(output / "image", output),
    )
    identities = {"spike": sha256_of_file(tools.executable), "plugin": sha256_of_file(tools.plugin)}
    if output.resolve().is_relative_to(image.resolve()):
        message = "AMP capture output must be outside the original image directory"
        raise ValueError(message)
    plugin_receipt, _ = admit_plugin(tools.plugin)
    runtime = simulator_identity(tools.executable, tools.plugin)
    output.mkdir()
    snapshot_runtime(output, runtime["runtime_libraries"])
    snapshot_plugin(output, plugin_receipt)
    snapshot = output / "image"
    expected = {name: digest for name, digest in admitted["inputs"].items() if name != "compiler"}
    if admitted.get("kernel_backend") == "rust":
        expected.update(admitted["rust_kernel"]["outputs"])
    expected.update(
        {
            "firmware.elf": admitted["firmware_sha256"],
            "image.json": sha256_of_file(manifest),
            "preparation.json": sha256_of_file(image / "preparation.json"),
        }
    )
    snapshot_image(image, snapshot, expected)
    shutil.copyfile(ROOT / "measurement-domain.json", output / "measurement-domain.json")
    (output / "command.json").write_bytes(
        canonical_json_bytes({"argv": command, "tools": identities, "runtime": runtime})
    )
    started = datetime.now(UTC).isoformat()
    with (output / "spike.log").open("xb") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=timeout)
    verify_execution(output, expected, tools, plugin_receipt, runtime)
    completion = completion_receipt((output / "spike.log").read_bytes())
    validate_plugin_snapshot(output, identities["plugin"], thermal=completion.thermal)
    run = read_amp_run((snapshot / "configuration.txt").read_bytes())
    validate_capture(
        completion,
        (output / "events.bin").read_bytes(),
        (output / "tracking_raw.csv").read_bytes(),
        (output / "measurement-domain.json").read_bytes(),
        run.cycles,
    )
    artifacts = [path for path in output.rglob("*") if path.is_file()]
    receipt = {
        "schema": "loop-timing-witness.amp-capture.v1",
        "simulation_only": True,
        "physical_verified": False,
        "started_utc": started,
        "completed_utc": datetime.now(UTC).isoformat(),
        "completion": asdict(completion),
        "tools": identities,
        "runtime": runtime,
        "files": {
            str(path.relative_to(output)): sha256_of_file(path) for path in sorted(artifacts)
        },
    }
    path = output / "capture.json"
    with path.open("xb") as stream:
        stream.write(canonical_json_bytes(receipt))
    run_manifest = write_amp_manifest(output)
    report, rows = build_report(load_run(run_manifest))
    write_report(output / "reports", report, rows)
    return path


def main(argv: list[str] | None = None) -> int:
    """Capture an actual verified ISA run through the public command line.

    Parameters
    ----------
    argv
        Explicit arguments or actual process arguments.

    Returns
    -------
    int
        Zero after observed final drain and stream validation, one after retained failure.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    add_image_arguments(parser)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--spike", type=Path, required=True)
    parser.add_argument("--plugin", type=Path, required=True)
    parser.add_argument("--rtc-nanoseconds", type=int, required=True)
    parser.add_argument("--time-limit", type=int, required=True)
    parser.add_argument("--timeout", type=int, required=True)
    args = parser.parse_args(argv)
    if (
        args.dtb.resolve() != (args.image / "platform.dtb").resolve()
        or args.configuration.resolve() != (args.image / "configuration.txt").resolve()
    ):
        print("AMP capture: FAIL: use the prepared original DTB and configuration", file=sys.stderr)
        return 1
    try:
        path = capture_amp(
            args.image,
            args.output,
            image_request(args),
            SpikeTools(args.spike, args.plugin, args.rtc_nanoseconds, args.time_limit),
            args.timeout,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"AMP capture: FAIL: {error}", file=sys.stderr)
        return 1
    print(f"AMP capture: PASS: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
