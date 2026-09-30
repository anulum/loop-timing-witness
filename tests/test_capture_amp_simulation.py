# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual public ISA capture and target-failure evidence

"""Execute the actual simulator and production plugin through the public capture command."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from amp_image_options import verification_arguments
from amp_spike_command import SpikeTools
from amp_tool_runtime import elf_interpreter
from capture_amp_simulation import capture_amp
from prepare_amp_image import BuildInputs, prepare_image
from test_amp_spike_command import REQUEST

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def capture_arguments(tmp_path: Path) -> list[str]:
    """Admit a private copy of an actually compiled source-bound firmware image.

    Parameters
    ----------
    tmp_path
        Exclusive original input copy and run staging.

    Returns
    -------
    list of str
        Public command arguments with actual simulator/plugin and explicit resource selection.
    """
    original = os.environ.get("WITNESS_AMP_IMAGE")
    executable = os.environ.get("WITNESS_SPIKE")
    plugin = os.environ.get("WITNESS_SPIKE_PLUGIN")
    assert original is not None, "actual publicly compiled RV64 AMP image is required"
    assert executable is not None
    assert plugin is not None
    image = tmp_path / "image"
    shutil.copytree(original, image)
    (image / "image.json").unlink()
    selection = verification_arguments(REQUEST)
    selection[selection.index("platform.dtb")] = str(image / "platform.dtb")
    selection[selection.index("configuration.txt")] = str(image / "configuration.txt")
    return [
        *selection,
        "--image",
        str(image),
        "--output",
        str(tmp_path / "capture"),
        "--spike",
        executable,
        "--plugin",
        plugin,
        "--rtc-nanoseconds",
        "100",
        "--time-limit",
        "100000000",
        "--timeout",
        "60",
    ]


def test_actual_public_capture(capture_arguments: list[str]) -> None:
    """Require observed completion, preserved sources and source-hashed raw output from actual ISA.

    Parameters
    ----------
    capture_arguments
        Actual source-bound image and installed simulator/plugin.
    """
    result = subprocess.run(
        [sys.executable, "tools/capture_amp_simulation.py", *capture_arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=75,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    output = Path(capture_arguments[capture_arguments.index("--output") + 1])
    receipt = json.loads((output / "capture.json").read_bytes())
    assert receipt["completion"] == {
        "samples": 10,
        "events": 40,
        "misses": 0,
        "overflow": 0,
        "safe": False,
        "thermal": False,
    }
    assert receipt["physical_verified"] is False
    assert "image/source/runtime/bare_metal/amp_controller.c" in receipt["files"]
    assert (output / "events.bin").stat().st_size == 640
    report = json.loads((output / "reports/report.json").read_bytes())
    assert report["evidence_status"] == "simulation_only"
    assert report["amp_completion"] == receipt["completion"]
    assert report["placement"] == "bare_metal_amp"
    assert report["invalid_reasons"] == ["power series unavailable"]


@pytest.mark.parametrize(
    "fault", ["short-limit", "image-output", "other-dtb", "timeout", "existing-output", "firmware"]
)
def test_public_failure_retains_evidence(capture_arguments: list[str], fault: str) -> None:
    """Exercise real input/ELF refusals and actual bounded simulator failure.

    Parameters
    ----------
    capture_arguments
        Actual image and installed simulator/plugin.
    fault
        Genuine invalid input, exclusive-output collision or insufficient target time budget.
    """
    output = Path(capture_arguments[capture_arguments.index("--output") + 1])
    image = Path(capture_arguments[capture_arguments.index("--image") + 1])
    if fault == "short-limit":
        capture_arguments[capture_arguments.index("--time-limit") + 1] = "1000000"
    elif fault == "image-output":
        output = image / "capture"
        capture_arguments[capture_arguments.index("--output") + 1] = str(output)
    elif fault == "other-dtb":
        capture_arguments[capture_arguments.index("--dtb") + 1] = str(image / "other.dtb")
    elif fault == "timeout":
        capture_arguments[capture_arguments.index("--timeout") + 1] = "0"
    elif fault == "existing-output":
        output.mkdir()
        (output / "retained").write_text("retained original", encoding="ascii")
    else:
        (image / "firmware.elf").write_bytes(b"invalid original ELF")
    result = subprocess.run(
        [sys.executable, "tools/capture_amp_simulation.py", *capture_arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=75,
        check=False,
    )
    assert result.returncode == 1
    assert "FAIL" in result.stderr
    assert not (output / "capture.json").exists()
    if fault == "short-limit":
        assert (output / "spike.log").exists()
        assert "time limit exceeded" in (output / "spike.log").read_text()
    if fault == "existing-output":
        assert (output / "retained").read_text() == "retained original"


@pytest.mark.parametrize(
    "fault", ["firmware", "plugin", "receipt", "runtime-library", "runtime-source"]
)
def test_live_input_mutation_refused(capture_arguments: list[str], fault: str) -> None:
    """Change a test-owned real executable input after target startup and require drift refusal.

    Parameters
    ----------
    capture_arguments
        Actual original image and installed tools.
    fault
        Actual input whose original bytes change while the target runs.
    """
    output = Path(capture_arguments[capture_arguments.index("--output") + 1])
    image = Path(capture_arguments[capture_arguments.index("--image") + 1])
    original_plugin = Path(capture_arguments[capture_arguments.index("--plugin") + 1])
    owned_plugin = image.parent / "actual-plugin.so"
    shutil.copyfile(original_plugin, owned_plugin)
    shutil.copyfile(original_plugin.with_name("plugin.json"), owned_plugin.with_name("plugin.json"))
    capture_arguments[capture_arguments.index("--plugin") + 1] = str(owned_plugin)
    environment = os.environ.copy()
    actual_library = image.parent / "actual-runtime-library"
    if fault == "runtime-library":
        executable = Path(capture_arguments[capture_arguments.index("--spike") + 1])
        listing = subprocess.check_output(
            [str(elf_interpreter(executable)), "--list", str(executable)], text=True, timeout=10
        )
        record = next(line for line in listing.splitlines() if "=>" in line)
        name, source = record.split("=>", 1)
        directory = image.parent / "actual-runtime"
        directory.mkdir()
        actual_library = directory / name.strip()
        shutil.copyfile(source.strip().rsplit(" (", 1)[0], actual_library)
        environment["LD_LIBRARY_PATH"] = (
            str(directory) + ":" + environment.get("LD_LIBRARY_PATH", "")
        )
    with subprocess.Popen(
        [sys.executable, "tools/capture_amp_simulation.py", *capture_arguments],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        deadline = time.monotonic() + 75
        try:
            while (
                not (output / "spike.log").exists()
                and process.poll() is None
                and time.monotonic() < deadline
            ):
                time.sleep(0.001)
            assert (output / "spike.log").exists()
            if fault == "receipt":
                receipt_path = owned_plugin.with_name("plugin.json")
                with receipt_path.open("ab") as stream:
                    stream.write(b"\n")
            elif fault in {"runtime-library", "runtime-source"}:
                if fault == "runtime-source":
                    index = json.loads((output / "runtime_source_index.json").read_bytes())
                    actual_library = output / next(iter(index.values()))["path"]
                with actual_library.open("ab") as stream:
                    stream.write(b"changed actual runtime library after target startup")
            else:
                path = output / "image/firmware.elf" if fault == "firmware" else owned_plugin
                with path.open("ab") as stream:
                    stream.write(b"observed post-start byte drift")
            stdout, stderr = process.communicate(timeout=max(0.001, deadline - time.monotonic()))
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
    assert process.returncode == 1, stdout
    assert (
        "runtime library bytes or paths changed"
        if fault == "runtime-source"
        else "changed during execution"
    ) in stderr
    assert not (output / "capture.json").exists()


def test_parked_image_refused(capture_arguments: list[str]) -> None:
    """Compile the actual parked exit and refuse using it as ISA target completion.

    Parameters
    ----------
    capture_arguments
        Actual source-bound compiled image and simulator/plugin.
    """
    image = Path(capture_arguments[capture_arguments.index("--image") + 1])
    compiler = Path(json.loads((image / "preparation.json").read_bytes())["compiler"])
    parked = image.parent / "parked"
    prepare_image(
        BuildInputs(ROOT, image / "platform.dtb", image / "configuration.txt", compiler, isa=False),
        parked,
        REQUEST,
    )
    environment = os.environ.copy()
    environment["PATH"] = str(compiler.parent) + os.pathsep + environment["PATH"]
    build = subprocess.run(
        ["make", "-C", str(parked), "-j2"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert build.returncode == 0, build.stderr + build.stdout
    tools = SpikeTools(
        Path(capture_arguments[capture_arguments.index("--spike") + 1]),
        Path(capture_arguments[capture_arguments.index("--plugin") + 1]),
        100,
        100000000,
    )
    with pytest.raises(ValueError, match="HTIF completion"):
        capture_amp(parked, image.parent / "parked-output", REQUEST, tools, 60)
