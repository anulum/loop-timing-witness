# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — compiled original Spike topology and exact execution arguments

"""Exercise actual simulator topology through dtc and public command admission."""

from __future__ import annotations

import os
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from amp_image_options import ImageRequest
from amp_memory import MemorySelection
from amp_platform import bind_platform
from amp_spike_command import SpikePaths, SpikeTools, original_harts, spike_command
from device_tree_interrupts import PlicSelection
from test_device_tree_resources import CompileTree, compile_tree

__all__ = ["compile_tree"]
ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    "/dts-v1/;"
    + (ROOT / "tests/platforms/spike_multihart.dts").read_text().split("/dts-v1/;", 1)[1]
)
PLIC = "/soc/plic@c000000"
REQUEST = ImageRequest(
    MemorySelection(
        "/memory@80000000",
        "/reserved-memory/firmware@80000000",
        "/reserved-memory/telemetry@80080000",
        16496,
        16384,
    ),
    PlicSelection(PLIC, 2, 2, "spike"),
    "/witness@40000000",
)


def test_original_multihart_command(compile_tree: CompileTree, tmp_path: Path) -> None:
    """Bind actual declared contexts and CPU identities without replacing target exit with a limit.

    Parameters
    ----------
    compile_tree
        Actual dtc compiler and public DTB decoder.
    tmp_path
        Exclusive output argument root.
    """
    tree = compile_tree(SOURCE)
    platform = bind_platform(tree, REQUEST.memory, REQUEST.device_path, REQUEST.plic)
    executable = os.environ.get("WITNESS_SPIKE") or shutil.which("spike")
    assert executable is not None, "actual Spike simulator is required"
    plugin = os.environ.get("WITNESS_SPIKE_PLUGIN")
    assert plugin is not None, "actual compiled production AXI plugin is required"
    tools = SpikeTools(Path(executable).resolve(), Path(plugin).resolve(), 100, 100000000)
    command = spike_command(
        tools, tree, platform, plic_path=PLIC, paths=SpikePaths(tmp_path / "image", tmp_path)
    )
    assert original_harts(tree, PLIC) == (1, 2)
    assert "-m2147483648:2147483648" in command
    assert "--hartids=1,2" in command
    assert "--pcs=1:2147483648,2:2147483648" in command
    assert not any("instructions" in value for value in command)
    assert command[-1] == str(tmp_path / "image/firmware.elf")


@pytest.mark.parametrize(
    ("old", "new", "finding"),
    [
        ("ucbbar,spike-bare", "unsupported,platform", "model"),
        ("reg = <0x02>;", "reg = <0x01>;", "identity"),
        ("reg = <0x02>;", "reg = <0x05>;", "identity"),
        ('status = "okay";', 'status = "disabled";', "identity"),
        ("rv64imac_zicsr_zifencei", "rv64imac", "ISA"),
        ("#address-cells = <0x01>;", "#address-cells = <0x03>;", "geometry"),
        ("#size-cells = <0x00>;", "#size-cells = <0x01>;", "geometry"),
        ('device_type = "cpu";', 'device_type = "other";', "no original"),
        ("riscv,cpu-intc", "unbound,cpu-intc", "interrupt controller"),
        ("0x02 0x0b 0x02 0x09", "0x02 0x09 0x02 0x0b", "contexts"),
    ],
)
def test_original_topology_refusal(
    compile_tree: CompileTree, old: str, new: str, finding: str
) -> None:
    """Refuse actual compiled topology changes before constructing simulator arguments.

    Parameters
    ----------
    compile_tree
        Actual original source compiler.
    old
        Original declaration to replace.
    new
        Invalid changed declaration.
    finding
        Required refusal category.
    """
    assert old in SOURCE
    with pytest.raises(ValueError, match=finding):
        original_harts(compile_tree(SOURCE.replace(old, new)), PLIC)


@pytest.mark.parametrize(
    "fault",
    [
        "relative-executable",
        "missing-executable",
        "nonexecutable",
        "relative-plugin",
        "missing-plugin",
        "hart",
        "delimiter",
        "missing-plic",
    ],
)
def test_command_admission_refusal(compile_tree: CompileTree, tmp_path: Path, fault: str) -> None:
    """Refuse actual resource/file identities and functional bounds before ISA startup.

    Parameters
    ----------
    compile_tree
        Actual dtc and public decoder.
    tmp_path
        Exact test-owned filesystem.
    fault
        Specific invalid original input.
    """
    executable = os.environ.get("WITNESS_SPIKE") or shutil.which("spike")
    plugin = os.environ.get("WITNESS_SPIKE_PLUGIN")
    assert executable is not None
    assert plugin is not None
    tree = compile_tree(SOURCE)
    platform = bind_platform(tree, REQUEST.memory, REQUEST.device_path, REQUEST.plic)
    tools = SpikeTools(Path(executable).resolve(), Path(plugin).resolve(), 100, 100000000)
    image, output, plic = tmp_path / "image", tmp_path, PLIC
    if fault == "relative-executable":
        tools = replace(tools, executable=Path("spike"))
    elif fault == "missing-executable":
        tools = replace(tools, executable=tmp_path / "missing")
    elif fault == "nonexecutable":
        blocked = tmp_path / "blocked"
        shutil.copyfile(tools.executable, blocked)
        blocked.chmod(0o600)
        tools = replace(tools, executable=blocked)
    elif fault == "relative-plugin":
        tools = replace(tools, plugin=Path("plugin.so"))
    elif fault == "missing-plugin":
        tools = replace(tools, plugin=tmp_path / "missing.so")
    elif fault == "hart":
        platform = replace(platform, hart=4)
    elif fault == "delimiter":
        image = tmp_path / "image,split"
    else:
        plic = "/missing-plic"
    with pytest.raises(ValueError, match=r"absolute|outside|absent|delimiter|contexts"):
        spike_command(tools, tree, platform, plic_path=plic, paths=SpikePaths(image, output))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("rtc", True),
        ("rtc", 0),
        ("rtc", 1000001),
        ("limit", True),
        ("limit", 999999),
        ("limit", 1 << 64),
    ],
)
def test_functional_clock_refusal(
    compile_tree: CompileTree, tmp_path: Path, field: str, value: int
) -> None:
    """Refuse invalid clock maps and native time bounds without running the target.

    Parameters
    ----------
    compile_tree
        Actual compiler and decoder.
    tmp_path
        Test-owned output arguments.
    field
        Functional bound to change.
    value
        Invalid type or out-of-range value.
    """
    executable = os.environ.get("WITNESS_SPIKE") or shutil.which("spike")
    plugin = os.environ.get("WITNESS_SPIKE_PLUGIN")
    assert executable is not None
    assert plugin is not None
    tree = compile_tree(SOURCE)
    platform = bind_platform(tree, REQUEST.memory, REQUEST.device_path, REQUEST.plic)
    tools = SpikeTools(Path(executable).resolve(), Path(plugin).resolve(), 100, 100000000)
    tools = (
        replace(tools, rtc_nanoseconds=value)
        if field == "rtc"
        else replace(tools, time_limit=value)
    )
    with pytest.raises(ValueError, match="outside bounds"):
        spike_command(
            tools, tree, platform, plic_path=PLIC, paths=SpikePaths(tmp_path / "image", tmp_path)
        )


@pytest.mark.parametrize(
    ("old", "new", "finding"),
    [
        ('device_type = "memory";', 'device_type = "other";', "no original RAM"),
        ('device_type = "memory";', 'device_type = "memory"; status = "disabled";', "enabled"),
        (
            "reg = <0x00 0x80000000 0x00 0x80000000>;",
            "reg = <0 0x80000001 0 0x80000000>;",
            "page aligned",
        ),
        (
            "reg = <0x00 0x80000000 0x00 0x80000000>;",
            "reg = <0 0x80000000 0 0x80000001>;",
            "page aligned",
        ),
        (
            "\n\tsoc {",
            (
                '\n memory@90000000 { device_type = "memory"; '
                "reg = <0 0x90000000 0 0x1000>; };\n\tsoc {"
            ),
            "overlap",
        ),
    ],
)
def test_native_ram_layout_refusal(
    compile_tree: CompileTree, tmp_path: Path, old: str, new: str, finding: str
) -> None:
    """Reject an actual compiled RAM layout that Spike would otherwise replace or round.

    Parameters
    ----------
    compile_tree
        Actual dtc compilation and public original-byte decoder.
    tmp_path
        Exclusive prospective image and output argument paths.
    old
        Exact original memory declaration to alter in owned source.
    new
        Concrete invalid RAM declaration compiled by dtc.
    finding
        Required public command admission refusal.
    """
    original = compile_tree(SOURCE)
    platform = bind_platform(original, REQUEST.memory, REQUEST.device_path, REQUEST.plic)
    tree = compile_tree(SOURCE.replace(old, new))
    tools = SpikeTools(
        Path(os.environ["WITNESS_SPIKE"]), Path(os.environ["WITNESS_SPIKE_PLUGIN"]), 100, 10000000
    )
    with pytest.raises(ValueError, match=finding):
        spike_command(
            tools, tree, platform, plic_path=PLIC, paths=SpikePaths(tmp_path / "image", tmp_path)
        )


def test_disjoint_original_ram_banks(compile_tree: CompileTree, tmp_path: Path) -> None:
    """Retain each actual disjoint RAM extent in sorted simulator allocation order.

    Parameters
    ----------
    compile_tree
        Actual dtc compiler and public original-byte decoder.
    tmp_path
        Exclusive prospective image and output argument paths.
    """
    source = SOURCE.replace(
        "\n\tsoc {",
        '\n memory@200000000 { device_type = "memory"; reg = <2 0 0 0x1000>; };\n\tsoc {',
    )
    tree = compile_tree(source)
    platform = bind_platform(tree, REQUEST.memory, REQUEST.device_path, REQUEST.plic)
    tools = SpikeTools(
        Path(os.environ["WITNESS_SPIKE"]), Path(os.environ["WITNESS_SPIKE_PLUGIN"]), 100, 10000000
    )
    command = spike_command(
        tools, tree, platform, plic_path=PLIC, paths=SpikePaths(tmp_path / "image", tmp_path)
    )
    assert "-m2147483648:2147483648,8589934592:4096" in command
