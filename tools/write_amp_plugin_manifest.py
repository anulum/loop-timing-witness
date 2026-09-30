# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual AMP logger completion and captured stream agreement

"""Retain actual compiler, SDK, RTL, dependency and link identities for a native Spike plugin."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

from amp_build_dependencies import dependency_hashes
from amp_plugin_inputs import NATIVE_OBJECTS, ROOT, PluginBuild
from amp_plugin_preparation import verified_preparation

from manifest_io import canonical_json_bytes, sha256_of_file


def write_plugin_manifest(build: PluginBuild) -> Path:
    """Bind the actual post-build source/header/tool/link closure to the resulting library.

    Parameters
    ----------
    build
        Actual Make build selections with complete native compiler dependency records.

    Returns
    -------
    Path
        New exclusive plugin.json receipt; original receipts are never overwritten.

    Raises
    ------
    OSError
        If actual original inputs, link artifacts or exclusive receipt are unavailable.
    ValueError
        If the plant parameter or compiler dependency closure is invalid.
    subprocess.SubprocessError
        If actual Git/compiler/version introspection fails.
    """
    directory = build.directory.resolve()
    records = tuple(directory / (name + ".d") for name in NATIVE_OBJECTS)
    dependencies = dependency_hashes(records, ROOT)
    model = directory / "rtl"
    model_records = tuple(
        path for path in sorted(model.glob("*.d")) if not path.name.endswith("__ver.d")
    )
    dependencies.update(dependency_hashes(model_records, model))
    preparation = verified_preparation(build, dependencies)
    identity = preparation["identity"]
    dependencies.update(identity["sources"])
    dependencies.update(preparation["build_files"])
    dependencies.update(preparation["dependency_records"])
    dependencies.update(
        {
            str(directory / name): sha256_of_file(directory / name)
            for name in ("generation.json", "compilation.json")
        }
    )
    link_inputs = [directory / (name + ".o") for name in NATIVE_OBJECTS]
    link_inputs.append(model / "Vaxi_control_witness__ALL.a")
    data: dict[str, Any] = {
        "schema": "loop-timing-witness.amp-plugin-build.v1",
        "simulation_only": True,
        **{
            name: identity[name]
            for name in (
                "working_directory",
                "thermal",
                "fifo_address_bits",
                "compilers",
                "verilator",
                "spike_sdk",
                "build_tools",
                "runtime_libraries",
            )
        },
        "plugin_sha256": sha256_of_file(directory / "witness_spike_axi.so"),
        "preparation": preparation,
        "preparation_path": str(directory / "compilation.json"),
        "dependencies": dependencies,
        "dependency_records": {
            str(path): sha256_of_file(path) for path in (*records, *model_records)
        },
        "link_inputs": {str(path): sha256_of_file(path) for path in link_inputs},
    }
    path = directory / "plugin.json"
    with path.open("xb") as stream:
        stream.write(canonical_json_bytes(data))
    return path


def main(argv: list[str] | None = None) -> int:
    """Write one original native plugin build receipt after the actual Make compile/link.

    Parameters
    ----------
    argv
        Explicit arguments or process arguments.

    Returns
    -------
    int
        Zero after exclusive complete provenance output, one after retained refusal.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--cc", required=True)
    parser.add_argument("--cxx", required=True)
    parser.add_argument("--thermal", type=int, required=True)
    parser.add_argument("--fifo-address-bits", type=int, default=8)
    parser.add_argument("--runtime-root", type=Path)
    args = parser.parse_args(argv)
    try:
        path = write_plugin_manifest(
            PluginBuild(
                args.directory,
                args.source,
                args.sdk,
                args.cc,
                args.cxx,
                args.thermal,
                args.fifo_address_bits,
                args.runtime_root,
            )
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"AMP plugin build receipt: FAIL: {error}", file=sys.stderr)
        return 1
    print(f"AMP plugin build receipt: PASS: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
