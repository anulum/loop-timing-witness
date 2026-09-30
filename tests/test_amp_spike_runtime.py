# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — native Spike plugin admission through the actual executable

"""Exercise native argument and resource refusals before target execution."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from amp_platform import bind_platform
from amp_spike_command import SpikePaths, SpikeTools, spike_command
from device_tree_blob import decode_device_tree
from prepare_amp_image import BuildInputs, prepare_image
from test_amp_spike_command import REQUEST, SOURCE

ROOT = Path(__file__).resolve().parents[1]
ARGUMENT = "Witness device arguments must be unsigned decimal integers"
CONTRACT = "Witness device simulation contract outside bounds"
MAILBOX = "Witness AMP mailbox or run files outside bounds"


@pytest.mark.parametrize(
    "plugin_environment", ["WITNESS_SPIKE_PLUGIN", "WITNESS_SPIKE_THERMAL_PLUGIN"]
)
@pytest.mark.parametrize(
    ("field", "value", "finding"),
    [
        (0, "", ARGUMENT),
        (0, "+1", ARGUMENT),
        (0, "-1", ARGUMENT),
        (0, " 1", ARGUMENT),
        (0, "1x", ARGUMENT),
        (0, "18446744073709551616", ARGUMENT),
        (0, "0", CONTRACT),
        (0, "1", CONTRACT),
        (0, "18446744073709551615", CONTRACT),
        (1, "0", CONTRACT),
        (1, "4294967296", CONTRACT),
        (2, "0", CONTRACT),
        (2, "1000001", CONTRACT),
        (3, "999999", CONTRACT),
        (3, "1000000", "Witness ISA simulation time limit exceeded"),
        (4, "0", MAILBOX),
        (4, "1", MAILBOX),
        (4, "18446744073709551608", MAILBOX),
        (5, "", MAILBOX),
        (6, "", MAILBOX),
        (7, "", MAILBOX),
        (-1, "extra", "Witness device requires base, IRQ, RTC nanoseconds"),
        (-2, "missing", "Witness device requires base, IRQ, RTC nanoseconds"),
        (1, "1024", "Witness device requires an available architectural PLIC source"),
        (0, "2147483648", "Witness device overlaps an existing simulator device"),
        (4, "8", "AMP mailbox does not fit actual simulator RAM"),
        (4, "ram-end", "AMP mailbox does not fit actual simulator RAM"),
        (4, "beyond-ram", "AMP mailbox does not fit actual simulator RAM"),
        (4, "near-ram-end", "AMP mailbox does not fit actual simulator RAM"),
        (2, "1000000", "Witness ISA clock advance outside bounds"),
    ],
)
def test_native_plugin_refusal(
    tmp_path: Path, plugin_environment: str, field: int, value: str, finding: str
) -> None:
    """Pass one invalid native field directly to the actual Spike plugin parser.

    Parameters
    ----------
    tmp_path
        Exclusive argument records and native diagnostic outputs.
    plugin_environment
        Mechanical or thermal production RTL plugin selection.
    field
        Native positional field, or negative selection for argument count faults.
    value
        Actual malformed text or original-RAM-relative address selection.
    finding
        Required native refusal before a completed capture can be claimed.
    """
    image = Path(os.environ["WITNESS_AMP_IMAGE"])
    tree = decode_device_tree((image / "platform.dtb").read_bytes())
    platform = bind_platform(tree, REQUEST.memory, REQUEST.device_path, REQUEST.plic)
    output = tmp_path / "execution"
    output.mkdir()
    argv = spike_command(
        SpikeTools(
            Path(os.environ["WITNESS_SPIKE"]), Path(os.environ[plugin_environment]), 100, 1000000000
        ),
        tree,
        platform,
        plic_path=REQUEST.plic.path,
        paths=SpikePaths(image, output),
    )
    index = next(i for i, text in enumerate(argv) if text.startswith("--device=witness_axi,"))
    fields = argv[index].split(",")[1:]
    assert len(fields) == 8
    if field == -1:
        fields.append(value)
    elif field == -2:
        fields.pop()
    else:
        if value.endswith(("ram", "ram-end")):
            memory = next(text for text in argv if text.startswith("-m"))
            start, size = map(int, memory[2:].split(":"))
            value = str(start + size + {"ram-end": 0, "beyond-ram": 8, "near-ram-end": -8}[value])
        fields[field] = value
    argv[index] = "--device=witness_axi," + ",".join(fields)
    (output / "command.json").write_text(json.dumps(argv, indent=2))
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
    (output / "spike.log").write_text(result.stdout + result.stderr)
    assert result.returncode != 0
    assert finding in result.stderr
    assert "WITNESS_AMP_COMPLETION" not in result.stdout
    assert not (output / "capture.json").exists()
    assert not (output / "manifest.json").exists()


@pytest.mark.parametrize(
    "plugin_environment", ["WITNESS_SPIKE_PLUGIN", "WITNESS_SPIKE_THERMAL_PLUGIN"]
)
def test_actual_selected_small_ram(tmp_path: Path, plugin_environment: str) -> None:
    """Run unchanged firmware and RTL with an original 1 MiB DTB-backed allocation.

    Parameters
    ----------
    tmp_path
        Exclusive original image copy, actual compiled DTB and raw execution.
    plugin_environment
        Mechanical or thermal production plant selected for actual execution.
    """
    image = tmp_path / "image"
    shutil.copytree(os.environ["WITNESS_AMP_IMAGE"], image)
    source = image / "selected-ram.dts"
    source.write_text(
        SOURCE.replace(
            "reg = <0x00 0x80000000 0x00 0x80000000>;", "reg = <0 0x80000000 0 0x100000>;"
        )
    )
    compiler = shutil.which("dtc")
    assert compiler is not None
    command = [compiler, "-I", "dts", "-O", "dtb", "-o", str(image / "platform.dtb"), str(source)]
    (image / "dtc.argv.json").write_text(json.dumps(command, indent=2))
    compiled = subprocess.run(command, capture_output=True, text=True, check=False)
    (image / "dtc.log").write_text(compiled.stdout + compiled.stderr)
    assert compiled.returncode == 0, compiled.stderr
    tree = decode_device_tree((image / "platform.dtb").read_bytes())
    platform = bind_platform(tree, REQUEST.memory, REQUEST.device_path, REQUEST.plic)
    output = tmp_path / "execution"
    output.mkdir()
    argv = spike_command(
        SpikeTools(
            Path(os.environ["WITNESS_SPIKE"]), Path(os.environ[plugin_environment]), 100, 10000000
        ),
        tree,
        platform,
        plic_path=REQUEST.plic.path,
        paths=SpikePaths(image, output),
    )
    assert "-m2147483648:1048576" in argv
    (output / "command.json").write_text(json.dumps(argv, indent=2))
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
    (output / "spike.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"samples":10,"events":40,"misses":0,"overflow":0,"safe":false' in result.stdout
    assert (output / "events.bin").stat().st_size == 640
    assert len((output / "tracking_raw.csv").read_text().splitlines()) == 11
    assert not (output / "capture.json").exists()
    assert not (output / "manifest.json").exists()


@pytest.mark.parametrize(
    "plugin_environment", ["WITNESS_SPIKE_PLUGIN", "WITNESS_SPIKE_THERMAL_PLUGIN"]
)
def test_actual_original_device_tree(tmp_path: Path, plugin_environment: str) -> None:
    """Retain the original supplied topology through real Spike construction and its dump command.

    Parameters
    ----------
    tmp_path
        Exclusive native arguments and generated original text.
    plugin_environment
        Mechanical or thermal production plugin selection.
    """
    image = Path(os.environ["WITNESS_AMP_IMAGE"])
    tree = decode_device_tree((image / "platform.dtb").read_bytes())
    platform = bind_platform(tree, REQUEST.memory, REQUEST.device_path, REQUEST.plic)
    argv = spike_command(
        SpikeTools(
            Path(os.environ["WITNESS_SPIKE"]), Path(os.environ[plugin_environment]), 100, 10000000
        ),
        tree,
        platform,
        plic_path=REQUEST.plic.path,
        paths=SpikePaths(image, tmp_path),
    )
    argv.insert(-1, "--dump-dts")
    (tmp_path / "command.json").write_text(json.dumps(argv, indent=2))
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
    (tmp_path / "device-tree.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    compiler = shutil.which("dtc")
    assert compiler is not None
    compiled = subprocess.run(
        [compiler, "-I", "dts", "-O", "dtb"],
        input=result.stdout.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    (tmp_path / "dumped.dtb").write_bytes(compiled.stdout)
    (tmp_path / "dumped-dtc.log").write_bytes(compiled.stderr)
    assert compiled.returncode == 0, compiled.stderr
    dumped = decode_device_tree(compiled.stdout)
    assert (
        dumped.nodes["/witness@40000000"].properties == tree.nodes["/witness@40000000"].properties
    )
    assert (
        dumped.nodes[REQUEST.memory.ram_path].properties
        == tree.nodes[REQUEST.memory.ram_path].properties
    )
    assert "WITNESS_AMP_COMPLETION" not in result.stdout


@pytest.mark.parametrize(
    "plugin_environment", ["WITNESS_SPIKE_PLUGIN", "WITNESS_SPIKE_THERMAL_PLUGIN"]
)
def test_native_synthetic_overload_refused(tmp_path: Path, plugin_environment: str) -> None:
    """Refuse native host-only time advance before the dedicated firmware can execute.

    Parameters
    ----------
    tmp_path
        Exclusive changed run file and actual native diagnostic outputs.
    plugin_environment
        Mechanical or thermal production plugin selection.
    """
    image = Path(os.environ["WITNESS_AMP_IMAGE"])
    configuration = tmp_path / "configuration.txt"
    words = (image / "configuration.txt").read_text().split()
    words[19:24] = ["overload", "2", "1", "0", "1"]
    configuration.write_text(" ".join(words) + "\n")
    tree = decode_device_tree((image / "platform.dtb").read_bytes())
    platform = bind_platform(tree, REQUEST.memory, REQUEST.device_path, REQUEST.plic)
    argv = spike_command(
        SpikeTools(
            Path(os.environ["WITNESS_SPIKE"]), Path(os.environ[plugin_environment]), 100, 10000000
        ),
        tree,
        platform,
        plic_path=REQUEST.plic.path,
        paths=SpikePaths(image, tmp_path),
    )
    index = next(i for i, text in enumerate(argv) if text.startswith("--device=witness_axi,"))
    fields = argv[index].split(",")
    fields[6] = str(configuration)
    argv[index] = ",".join(fields)
    (tmp_path / "command.json").write_text(json.dumps(argv, indent=2))
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
    (tmp_path / "spike.log").write_text(result.stdout + result.stderr)
    assert result.returncode != 0
    assert "AMP overload must execute actual target instructions" in result.stderr
    assert "WITNESS_AMP_COMPLETION" not in result.stdout
    assert not (tmp_path / "capture.json").exists()
    assert not (tmp_path / "manifest.json").exists()


@pytest.mark.parametrize(
    "plugin_environment", ["WITNESS_SPIKE_PLUGIN", "WITNESS_SPIKE_THERMAL_PLUGIN"]
)
@pytest.mark.parametrize(
    ("old", "new", "finding"),
    [
        (
            'compatible = "riscv,plic0";',
            'compatible = "unavailable,plic";',
            "Assertion `plic.get()' failed",
        ),
        (
            "reg = <0x00 0x10000000 0x00 0x100>;",
            "reg = <0 0x40000080 0 0x100>;",
            "overlaps an existing simulator device",
        ),
    ],
)
def test_actual_native_topology_refusal(
    tmp_path: Path, plugin_environment: str, old: str, new: str, finding: str
) -> None:
    """Refuse missing real PLIC wiring or a real UART inside the Witness aperture.

    Parameters
    ----------
    tmp_path
        Exclusive actual dtc source, DTB, arguments and native diagnostics.
    plugin_environment
        Mechanical or thermal production plugin selection.
    old
        Exact original controller or UART declaration.
    new
        Actual conflicting declaration compiled into the executed DTB.
    finding
        Required native admission refusal before target execution.
    """
    image = Path(os.environ["WITNESS_AMP_IMAGE"])
    original = decode_device_tree((image / "platform.dtb").read_bytes())
    platform = bind_platform(original, REQUEST.memory, REQUEST.device_path, REQUEST.plic)
    assert SOURCE.count(old) == 1
    source = tmp_path / "native-topology.dts"
    source.write_text(SOURCE.replace(old, new))
    compiler = shutil.which("dtc")
    assert compiler is not None
    dtb = tmp_path / "native-topology.dtb"
    compiled = subprocess.run(
        [compiler, "-I", "dts", "-O", "dtb", "-o", str(dtb), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    (tmp_path / "dtc.log").write_text(compiled.stdout + compiled.stderr)
    assert compiled.returncode == 0, compiled.stderr
    argv = spike_command(
        SpikeTools(
            Path(os.environ["WITNESS_SPIKE"]), Path(os.environ[plugin_environment]), 100, 10000000
        ),
        original,
        platform,
        plic_path=REQUEST.plic.path,
        paths=SpikePaths(image, tmp_path),
    )
    argv = ["--dtb=" + str(dtb) if text.startswith("--dtb=") else text for text in argv]
    (tmp_path / "command.json").write_text(json.dumps(argv, indent=2))
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
    (tmp_path / "spike.log").write_text(result.stdout + result.stderr)
    assert result.returncode != 0
    assert finding in result.stderr
    assert "WITNESS_AMP_COMPLETION" not in result.stdout
    assert not (tmp_path / "capture.json").exists()
    assert not (tmp_path / "manifest.json").exists()


@pytest.mark.parametrize(
    "plugin_environment", ["WITNESS_SPIKE_PLUGIN", "WITNESS_SPIKE_THERMAL_PLUGIN"]
)
def test_actual_completion_output_refusal(tmp_path: Path, plugin_environment: str) -> None:
    """Refuse a real completion receipt write failure after actual stream drain.

    Parameters
    ----------
    tmp_path
        Exclusive native arguments, streams and retained diagnostic output.
    plugin_environment
        Mechanical or thermal original RTL plugin selection.
    """
    image = Path(os.environ["WITNESS_AMP_IMAGE"])
    tree = decode_device_tree((image / "platform.dtb").read_bytes())
    platform = bind_platform(tree, REQUEST.memory, REQUEST.device_path, REQUEST.plic)
    argv = spike_command(
        SpikeTools(
            Path(os.environ["WITNESS_SPIKE"]), Path(os.environ[plugin_environment]), 100, 10000000
        ),
        tree,
        platform,
        plic_path=REQUEST.plic.path,
        paths=SpikePaths(image, tmp_path),
    )
    (tmp_path / "command.json").write_text(json.dumps(argv, indent=2))
    with Path("/dev/full").open("wb") as refused_output:
        result = subprocess.run(
            argv,
            cwd=ROOT,
            stdout=refused_output,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
            check=False,
        )
    (tmp_path / "spike.log").write_text(result.stderr)
    assert result.returncode != 0
    assert "AMP completion receipt write failed" in result.stderr
    assert (tmp_path / "events.bin").stat().st_size == 640
    assert len((tmp_path / "tracking_raw.csv").read_text().splitlines()) == 11
    assert not (tmp_path / "capture.json").exists()
    assert not (tmp_path / "manifest.json").exists()


@pytest.mark.parametrize(
    "plugin_environment", ["WITNESS_SPIKE_PLUGIN", "WITNESS_SPIKE_THERMAL_PLUGIN"]
)
def test_actual_native_safe_completion(tmp_path: Path, plugin_environment: str) -> None:
    """Observe the actual safe-state completion after a compiled four-period freeze.

    Parameters
    ----------
    tmp_path
        Exclusive prepared firmware, original configuration and raw native execution.
    plugin_environment
        Mechanical or thermal actual production RTL selection.
    """
    original = Path(os.environ["WITNESS_AMP_IMAGE"])
    words = (original / "configuration.txt").read_text().split()
    words[19:24] = ["freeze", "3", "4", "0", "0"]
    configuration = tmp_path / "configuration.txt"
    configuration.write_text(" ".join(words) + "\n")
    image = tmp_path / "image"
    prepare_image(
        BuildInputs(
            ROOT,
            original / "platform.dtb",
            configuration,
            Path(os.environ["WITNESS_RV64_CC"]),
            isa=True,
        ),
        image,
        REQUEST,
    )
    build = subprocess.run(
        ["make", "-C", str(image), "-j2"], capture_output=True, text=True, timeout=60, check=False
    )
    (tmp_path / "build.log").write_text(build.stdout + build.stderr)
    assert build.returncode == 0, build.stdout + build.stderr
    output = tmp_path / "execution"
    output.mkdir()
    tree = decode_device_tree((image / "platform.dtb").read_bytes())
    platform = bind_platform(tree, REQUEST.memory, REQUEST.device_path, REQUEST.plic)
    argv = spike_command(
        SpikeTools(
            Path(os.environ["WITNESS_SPIKE"]), Path(os.environ[plugin_environment]), 100, 10000000
        ),
        tree,
        platform,
        plic_path=REQUEST.plic.path,
        paths=SpikePaths(image, output),
    )
    (output / "command.json").write_text(json.dumps(argv, indent=2))
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
    (output / "spike.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    completion = json.loads(
        next(
            line.removeprefix("WITNESS_AMP_COMPLETION ")
            for line in result.stdout.splitlines()
            if line.startswith("WITNESS_AMP_COMPLETION ")
        )
    )
    assert completion["safe"] is True
    assert completion["samples"] == 6
    assert completion["events"] == 32
    assert completion["misses"] == 7
    assert completion["overflow"] == 0
    assert not (output / "capture.json").exists()
    assert not (output / "manifest.json").exists()
