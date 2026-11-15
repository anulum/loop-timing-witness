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
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
    from amp_completion import AmpCompletion

ROOT = Path(__file__).resolve().parents[1]
MAX_TIMEOUT_SECONDS = 3600


def _admitted_image(
    image: Path, request: ImageRequest, timeout: int
) -> tuple[Path, dict[str, Any]]:
    """Check the timeout and admit an ISA image that completes through HTIF.

    Parameters
    ----------
    image
        Original image build directory.
    request
        Explicit original resource and stack selection.
    timeout
        Host timeout in seconds.

    Returns
    -------
    tuple[Path, dict[str, Any]]
        The verified image manifest and its decoded declarations.

    Raises
    ------
    ValueError
        If the timeout is out of range, the image fails verification or it parks.
    """
    if type(timeout) is not int or not 1 <= timeout <= MAX_TIMEOUT_SECONDS:
        message = "AMP host timeout must be an integer in [1,3600] seconds"
        raise ValueError(message)
    manifest = verify_image(image, image / "platform.dtb", image / "configuration.txt", request)
    admitted = load_json_object(manifest)
    if admitted["exit_mode"] != "isa_htif":
        message = "AMP ISA capture requires target HTIF completion, not a parked image"
        raise ValueError(message)
    return manifest, admitted


def _expected_image(image: Path, manifest: Path, admitted: dict[str, Any]) -> dict[str, str]:
    """Return the digest every snapshotted image file must have.

    Parameters
    ----------
    image
        Original image build directory.
    manifest
        Verified image manifest.
    admitted
        Its decoded declarations.

    Returns
    -------
    dict[str, str]
        Inputs except the compiler, Rust kernel outputs when built, firmware,
        manifest and preparation digests.
    """
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
    return expected


@dataclass(frozen=True)
class _Prepared:
    """Admitted inputs and staged outputs of one capture, before the simulator runs.

    Attributes
    ----------
    command
        Spike command vector.
    identities
        Simulator and plugin digests.
    plugin_receipt
        Admitted plugin build receipt bytes.
    runtime
        Simulator runtime identity.
    expected
        Digest of every snapshotted image file.
    """

    command: list[str]
    identities: dict[str, str]
    plugin_receipt: bytes
    runtime: dict[str, Any]
    expected: dict[str, str]


def _snapshot_image_files(
    image: Path, output: Path, manifest: Path, admitted: dict[str, Any]
) -> dict[str, str]:
    """Snapshot the image into the capture and copy the measurement domain.

    Parameters
    ----------
    image
        Original image build directory.
    output
        Capture directory.
    manifest, admitted
        Verified image manifest and its declarations.

    Returns
    -------
    dict[str, str]
        Digest every snapshotted image file must have.
    """
    expected = _expected_image(image, manifest, admitted)
    snapshot_image(image, output / "image", expected)
    shutil.copyfile(ROOT / "measurement-domain.json", output / "measurement-domain.json")
    return expected


def _spike_vector(image: Path, output: Path, request: ImageRequest, tools: SpikeTools) -> list[str]:
    """Return the Spike command for the image's admitted topology.

    Parameters
    ----------
    image
        Original image build directory holding ``platform.dtb``.
    output
        Capture directory; the image is snapshotted beneath it.
    request
        Original explicit RAM, PLIC, hart and stack selection.
    tools
        Installed simulator and plugin with the clock bounds.

    Returns
    -------
    list[str]
        Spike command vector.
    """
    tree = decode_device_tree((image / "platform.dtb").read_bytes())
    platform = bind_platform(tree, request.memory, request.device_path, request.plic)
    return spike_command(
        tools,
        tree,
        platform,
        plic_path=request.plic.path,
        paths=SpikePaths(output / "image", output),
    )


def _prepare(
    image: Path, output: Path, request: ImageRequest, tools: SpikeTools, timeout: int
) -> _Prepared:
    """Admit the image and tools, then create and stage the capture directory.

    Parameters
    ----------
    image
        Original prepared and compiled ISA image.
    output
        New exclusive capture directory.
    request
        Original explicit RAM, PLIC, hart and stack selection.
    tools
        Installed simulator and plugin with the clock bounds.
    timeout
        Host safety timeout in seconds.

    Returns
    -------
    _Prepared
        Command, identities, plugin receipt, runtime and expected image digests.

    Raises
    ------
    ValueError
        If the timeout, image, output placement or plugin is not admitted.
    """
    manifest, admitted = _admitted_image(image, request, timeout)
    command = _spike_vector(image, output, request, tools)
    identities = {"spike": sha256_of_file(tools.executable), "plugin": sha256_of_file(tools.plugin)}
    if output.resolve().is_relative_to(image.resolve()):
        message = "AMP capture output must be outside the original image directory"
        raise ValueError(message)
    plugin_receipt, _ = admit_plugin(tools.plugin)
    runtime = simulator_identity(tools.executable, tools.plugin)
    output.mkdir()
    snapshot_runtime(output, runtime["runtime_libraries"])
    snapshot_plugin(output, plugin_receipt)
    expected = _snapshot_image_files(image, output, manifest, admitted)
    (output / "command.json").write_bytes(
        canonical_json_bytes({"argv": command, "tools": identities, "runtime": runtime})
    )
    return _Prepared(command, identities, plugin_receipt, runtime, expected)


def _check_logged_run(output: Path, plugin_sha256: str) -> AmpCompletion:
    """Read the logger's completion and check the plugin and captured streams with it.

    Parameters
    ----------
    output
        Capture directory.
    plugin_sha256
        Digest of the simulator plugin.

    Returns
    -------
    AmpCompletion
        The logger's completion receipt.

    Raises
    ------
    ValueError
        If the plugin snapshot or the captured events and tracking contradict it.
    """
    completion = completion_receipt((output / "spike.log").read_bytes())
    validate_plugin_snapshot(output, plugin_sha256, thermal=completion.thermal)
    run = read_amp_run((output / "image" / "configuration.txt").read_bytes())
    validate_capture(
        completion,
        (output / "events.bin").read_bytes(),
        (output / "tracking_raw.csv").read_bytes(),
        (output / "measurement-domain.json").read_bytes(),
        run.cycles,
    )
    return completion


def _write_receipt(
    output: Path,
    started: str,
    completion: AmpCompletion,
    identities: dict[str, str],
    runtime: dict[str, Any],
) -> Path:
    """Write the capture receipt with the digest of every captured file.

    Parameters
    ----------
    output
        Capture directory.
    started
        UTC start of the simulator run.
    completion
        The logger's completion receipt.
    identities
        Simulator and plugin digests.
    runtime
        Simulator runtime identity.

    Returns
    -------
    Path
        The new ``capture.json``.
    """
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
    return path


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
    prepared = _prepare(image, output, request, tools, timeout)
    started = datetime.now(UTC).isoformat()
    with (output / "spike.log").open("xb") as log:
        subprocess.run(
            prepared.command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=timeout
        )
    verify_execution(output, prepared.expected, tools, prepared.plugin_receipt, prepared.runtime)
    completion = _check_logged_run(output, prepared.identities["plugin"])
    path = _write_receipt(output, started, completion, prepared.identities, prepared.runtime)
    report, rows = build_report(load_run(write_amp_manifest(output)))
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
