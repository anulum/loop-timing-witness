# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — public interface of the unchanged Spike device

"""Call the unchanged Spike device through its public interface and Spike's device registry.

The probe plugin includes ``runtime/isa/spike_axi_device.cpp`` verbatim and adds one
device factory. That factory builds the production device and calls the public
``load`` and ``store`` interface with requests Spike's own bus never forms. It also asks
Spike's registry for the production factory's device-tree text, which Spike requests
only for built-in devices. It then hands the device to Spike, so the actual firmware runs
to completion on it.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from amp_diagnostic_build import build_diagnostic_plugin, verified_receipt
from amp_platform import bind_platform
from amp_spike_command import SpikePaths, SpikeTools, spike_command
from device_tree_blob import decode_device_tree
from test_amp_spike_command import REQUEST

from loop_timing_witness.host_profile import scaled

ROOT = Path(__file__).resolve().parents[1]
PROBE = """// The device source is this unit's only copy, so its anonymous-namespace member types
// cannot meet another definition, which GCC's subobject-linkage warning guards against.
#pragma GCC diagnostic ignored "-Wsubobject-linkage"
#include "@DEVICE@"

using witness_axi_probe_t = witness_axi_t;

namespace {
/** Build the production device, call its public interface, then hand it to Spike. */
witness_axi_t *probe_parse(const void *fdt, const sim_t *sim, reg_t *base,
                           const std::vector<std::string> &args) {
    auto *device = witness_axi_parse(fdt, sim, base, args);
    abstract_device_t &bus = *device;
    std::array<std::uint8_t, 8> word{};
    const bool refused =
        !bus.load(0, 1, word.data()) && !bus.load(0, 8, word.data()) &&
        !bus.load(1, 4, word.data()) && !bus.load(256, 4, word.data()) &&
        !bus.load(252, 4, word.data()) && !bus.store(0, 1, word.data()) &&
        !bus.store(0, 8, word.data()) && !bus.store(1, 4, word.data()) &&
        !bus.store(256, 4, word.data());
    std::cout << "WITNESS_DEVICE_PROBE " << (refused ? "refused" : "admitted") << "\\n"
              << mmio_device_map().at("witness_axi")->generate_dts(sim, args);
    std::cout.flush();
    return device;
}

/** Describe the probe's aperture with the production text. */
std::string probe_dts(const sim_t *sim, const std::vector<std::string> &args) {
    return witness_axi_dts(sim, args);
}
} // namespace

REGISTER_DEVICE(witness_axi_probe, probe_parse, probe_dts)
"""


@pytest.fixture(scope="module", params=["WITNESS_SPIKE_PLUGIN", "WITNESS_SPIKE_THERMAL_PLUGIN"])
def probe_plugin(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Link the probe against the selected plugin's verified objects.

    Parameters
    ----------
    request
        Mechanical or thermal plugin selection.
    tmp_path_factory
        Exclusive probe source, dependency records and build logs.

    Returns
    -------
    Path
        Probe plugin; a counted selected plugin passes its counters on.
    """
    production = Path(os.environ[request.param])
    receipt = verified_receipt(production)
    directory = tmp_path_factory.mktemp("amp-device-probe")
    source = directory / "device_probe.cpp"
    device = (ROOT / "runtime/isa/spike_axi_device.cpp").resolve()
    source.write_text(PROBE.replace("@DEVICE@", str(device)), encoding="utf-8")
    return build_diagnostic_plugin(production, receipt, directory, source)


def test_public_device_interface(probe_plugin: Path, tmp_path: Path) -> None:
    """Refuse every malformed public request, describe the aperture and complete the run.

    Parameters
    ----------
    probe_plugin
        Probe of the unchanged production device.
    tmp_path
        Exclusive execution outputs and diagnostics.
    """
    image = Path(os.environ["WITNESS_AMP_IMAGE"])
    tree = decode_device_tree((image / "platform.dtb").read_bytes())
    platform = bind_platform(tree, REQUEST.memory, REQUEST.device_path, REQUEST.plic)
    output = tmp_path / "execution"
    output.mkdir()
    argv = spike_command(
        SpikeTools(Path(os.environ["WITNESS_SPIKE"]), probe_plugin, 100, 10000000),
        tree,
        platform,
        plic_path=REQUEST.plic.path,
        paths=SpikePaths(image, output),
    )
    index = next(i for i, text in enumerate(argv) if text.startswith("--device=witness_axi,"))
    argv[index] = argv[index].replace("--device=witness_axi,", "--device=witness_axi_probe,", 1)
    result = subprocess.run(
        argv, cwd=ROOT, capture_output=True, text=True, timeout=scaled(30), check=False
    )
    (output / "spike.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "WITNESS_DEVICE_PROBE refused\n" in result.stdout
    assert (
        '    witness@40000000 { compatible = "anulum,loop-timing-witness-axi-v1", '
        '"anulum,witness-isa-simulation"; reg = <0x0 0x40000000 0 0x100>; '
        "interrupt-parent = <&PLIC>; interrupts = <0x2>; };\n"
    ) in result.stdout
    assert '"samples":10,"events":40,"misses":0,"overflow":0,"safe":false' in result.stdout
    assert (output / "events.bin").stat().st_size == 640
