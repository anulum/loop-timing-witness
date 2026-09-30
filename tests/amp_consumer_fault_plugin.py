# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — real Spike consumer startup fault build

"""Build an explicit consumer publication fault from original production inputs."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest

from manifest_io import sha256_of_file

ROOT = Path(__file__).resolve().parents[1]
ConsumerFault = Literal["invalid-ready", "corrupt-ready-mailbox", "invalid-complete"]


@dataclass(frozen=True)
class ConsumerFaultPlugin:
    """One diagnostic plugin and the exact consumer protocol fault it injects."""

    path: Path
    fault: ConsumerFault


def consumer_fault_sources(directory: Path, fault: ConsumerFault) -> tuple[Path, Path, Path]:
    """Generate a diagnostic plugin whose real logger violates one owned transition.

    Parameters
    ----------
    directory
        Exclusive build directory for the generated diagnostic sources.
    fault
        Consumer-owned startup release, ready-mailbox or completion fault.

    Returns
    -------
    tuple of Path, Path and Path
        Generated plugin translation unit, logger header and memory transport header.
        Exact production anchors make source drift fail before compilation.
    """
    logger = (ROOT / "runtime/amp_logger.h").read_text()
    logger = logger.replace(
        '#include "run_control.h"',
        '#include "' + str((ROOT / "runtime/run_control.h").resolve()) + '"',
    ).replace(
        '#include "bare_metal/amp_contract.h"',
        '#include "' + str((ROOT / "runtime/bare_metal/amp_contract.h").resolve()) + '"',
    )
    ready_write = (
        "            device.write_memory32(shared + "
        "offsetof(witness_amp_mailbox, logger_status),\n"
        "                                  WITNESS_AMP_LOGGER_READY);"
    )
    complete_write = (
        "        device.write_memory32(shared + "
        "offsetof(witness_amp_mailbox, logger_status),\n"
        "                              WITNESS_AMP_LOGGER_COMPLETE);"
    )
    assert logger.count(ready_write) == 1
    assert logger.count(complete_write) == 1
    if fault == "invalid-ready":
        logger = logger.replace(ready_write, ready_write.replace("WITNESS_AMP_LOGGER_READY", "99"))
    elif fault == "corrupt-ready-mailbox":
        logger = logger.replace(
            ready_write,
            ready_write + "\n            device.write_memory32(shared + "
            "offsetof(witness_amp_mailbox, reserved), 1);",
        )
    else:
        logger = logger.replace(
            complete_write,
            complete_write.replace("WITNESS_AMP_LOGGER_COMPLETE", "99"),
        )
    logger_path = directory / "consumer_fault_logger.h"
    logger_path.write_text(logger)

    transport = (ROOT / "runtime/isa/spike_amp_transport.h").read_text()
    transport = transport.replace(
        '#include "../rtl/simulation.h"',
        '#include "' + str((ROOT / "runtime/rtl/simulation.h").resolve()) + '"',
    ).replace(
        '#include "../bare_metal/amp_contract.h"',
        '#include "' + str((ROOT / "runtime/bare_metal/amp_contract.h").resolve()) + '"',
    )
    transport_guard = (
        "        if (displacement != offsetof(witness_amp_mailbox, consumer) &&\n"
        "            displacement != offsetof(witness_amp_mailbox, logger_status))"
    )
    assert transport.count(transport_guard) == 1
    if fault == "corrupt-ready-mailbox":
        transport = transport.replace(
            transport_guard,
            "        if (displacement != offsetof(witness_amp_mailbox, consumer) &&\n"
            "            displacement != offsetof(witness_amp_mailbox, logger_status) &&\n"
            "            displacement != offsetof(witness_amp_mailbox, reserved))",
        )
    transport_path = directory / "consumer_fault_transport.h"
    transport_path.write_text(transport)

    source = (ROOT / "runtime/isa/spike_axi_device.cpp").read_text()
    replacements = {
        "../rtl/simulation.h": str((ROOT / "runtime/rtl/simulation.h").resolve()),
        "spike_amp_transport.h": str(transport_path.resolve()),
        "../amp_logger.h": str(logger_path.resolve()),
    }
    for original_include, replacement in replacements.items():
        anchor = '"' + original_include + '"'
        assert source.count(anchor) == 1
        source = source.replace(anchor, '"' + replacement + '"')
    if fault == "invalid-complete":
        final_synchronise = """        }
        synchronize();
    }
};"""
        assert source.count(final_synchronise) == 1
        source = source.replace(
            final_synchronise,
            """        } else if (transport.read_memory32(configuration.shared +
                       offsetof(witness_amp_mailbox, status)) == WITNESS_AMP_REFUSED) {
            throw std::runtime_error("ACTUAL_INVALID_COMPLETE cause=" +
                std::to_string(transport.read_memory32(configuration.shared +
                    offsetof(witness_amp_mailbox, trap_cause))) + " value=" +
                std::to_string(transport.read_memory32(configuration.shared +
                    offsetof(witness_amp_mailbox, trap_value))));
        }
        synchronize();
    }
};""",
        )
    source_path = directory / "consumer_fault_plugin.cpp"
    source_path.write_text(source)
    return source_path, logger_path, transport_path


@pytest.fixture(
    scope="module",
    params=[
        pytest.param(
            (environment, fault),
            id=environment.removeprefix("WITNESS_SPIKE_").lower() + "-" + fault,
        )
        for environment in ("WITNESS_SPIKE_PLUGIN", "WITNESS_SPIKE_THERMAL_PLUGIN")
        for fault in ("invalid-ready", "corrupt-ready-mailbox", "invalid-complete")
    ],
)
def consumer_fault_plugin(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> ConsumerFaultPlugin:
    """Link the diagnostic logger against hash-verified production RTL and SDK objects."""
    environment, fault = request.param
    production = Path(os.environ[environment])
    receipt = json.loads((production.parent / "plugin.json").read_text())
    assert sha256_of_file(production) == receipt["plugin_sha256"]
    compiler = receipt["compilers"]["cxx"]["driver"]
    assert sha256_of_file(Path(compiler["path"])) == compiler["sha256"]
    for name, digest in receipt["link_inputs"].items():
        assert sha256_of_file(Path(name)) == digest

    directory = tmp_path_factory.mktemp("amp-consumer-fault-plugin")
    source, logger, transport = consumer_fault_sources(directory, fault)
    sdk_source = Path(receipt["spike_sdk"]["source"])
    sdk_build = Path(receipt["spike_sdk"]["build"])
    verilator = Path(receipt["verilator"]["root"]) / "include"
    includes = [
        verilator,
        verilator / "vltstd",
        sdk_source,
        sdk_source / "riscv",
        sdk_source / "fdt",
        sdk_build,
    ]
    target = directory / "witness_spike_axi.so"
    commands = [
        [
            compiler["path"],
            "-std=c++20",
            "-O2",
            "-fPIC",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wconversion",
            "-Wshadow",
            "-I" + str(production.parent / "rtl"),
            *[argument for path in includes for argument in ["-isystem", str(path)]],
            "-MD",
            "-MF",
            str(directory / "plugin.d"),
            "-c",
            str(source),
            "-o",
            str(directory / "plugin.o"),
        ],
        [
            compiler["path"],
            "-shared",
            "-Wl,--fatal-warnings",
            str(directory / "plugin.o"),
            *[name for name in receipt["link_inputs"] if Path(name).name != "plugin.o"],
            "-pthread",
            "-o",
            str(target),
        ],
    ]
    (directory / "build.argv.json").write_text(json.dumps(commands, indent=2))
    for index, argv in enumerate(commands):
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, check=False)
        (directory / f"build_{index}.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
    (directory / "source_sha256.json").write_text(
        json.dumps(
            {
                "production_plugin": receipt["plugin_sha256"],
                "production_logger": sha256_of_file(ROOT / "runtime/amp_logger.h"),
                "production_transport": sha256_of_file(ROOT / "runtime/isa/spike_amp_transport.h"),
                "fault": fault,
                "diagnostic_logger": sha256_of_file(logger),
                "diagnostic_transport": sha256_of_file(transport),
                "diagnostic_source": sha256_of_file(source),
                "diagnostic_plugin": sha256_of_file(target),
            },
            indent=2,
        )
    )
    return ConsumerFaultPlugin(target, fault)
