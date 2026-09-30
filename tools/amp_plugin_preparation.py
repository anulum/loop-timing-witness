# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original plugin generation and compilation custody

"""Freeze actual generation inputs and compiler-derived dependencies before compilation."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

from amp_build_dependencies import dependency_hashes
from amp_plugin_inputs import NATIVE_OBJECTS, ROOT, PluginBuild, original_identity
from jsonschema import Draft202012Validator

from manifest_io import canonical_json_bytes, load_json_object, sha256_of_file


def freeze_plugin(build: PluginBuild, stage: str) -> Path:
    """Create an exclusive original generation or pre-compilation receipt.

    Parameters
    ----------
    build
        Original actual selections used by public Make.
    stage
        Generation before Verilator, or compilation after real dependency preprocessing.

    Returns
    -------
    Path
        New exclusive stage receipt retained in the actual build directory.

    Raises
    ------
    ValueError
        If the original generation inputs changed or the requested stage is unknown.
    """
    if stage not in ("generation", "compilation"):
        message = "AMP plugin preparation stage must be generation or compilation"
        raise ValueError(message)
    if any(path.suffix in (".o", ".a", ".so") for path in build.directory.rglob("*")):
        message = "AMP plugin preparation must precede compilation"
        raise ValueError(message)
    if build.directory.is_symlink():
        message = "AMP plugin output directory cannot be a symbolic link"
        raise ValueError(message)
    if stage == "generation":
        if (build.directory / "generation.json").exists():
            message = "AMP plugin original generation receipt already exists"
            raise FileExistsError(message)
        if any(build.directory.iterdir()):
            message = "AMP plugin generation requires an empty output directory"
            raise ValueError(message)
    identity = original_identity(build)
    data: dict[str, Any] = {
        "schema": "loop-timing-witness.amp-plugin-preparation.v1",
        "stage": stage,
        "identity": identity,
    }
    directory = build.directory.resolve()
    if stage == "compilation":
        generation = directory / "generation.json"
        original = load_json_object(generation)
        if original != {**data, "stage": "generation"}:
            message = "AMP plugin original generation inputs changed"
            raise ValueError(message)
        records = tuple(
            directory / "precompile" / (name + ".d") for name in (*NATIVE_OBJECTS, "model")
        )
        data.update(
            {
                "generation_sha256": sha256_of_file(generation),
                "dependencies": dependency_hashes(records, ROOT),
                "dependency_records": {str(path): sha256_of_file(path) for path in records},
                "build_files": {
                    str(path): sha256_of_file(path)
                    for path in sorted((directory / "rtl").iterdir())
                    if path.suffix in (".cpp", ".h", ".mk", ".dat")
                },
            }
        )
    path = directory / (stage + ".json")
    with path.open("xb") as stream:
        stream.write(canonical_json_bytes(data))
    return path


def verified_preparation(build: PluginBuild, dependencies: dict[str, str]) -> dict[str, Any]:
    """Require unchanged original generation inputs and every pre-compilation dependency.

    Parameters
    ----------
    build
        Actual completed build selection.
    dependencies
        Actual post-compilation source/header dependency map.

    Returns
    -------
    dict of str to Any
        Original pre-compilation receipt after actual build reconciliation.

    Raises
    ------
    ValueError
        If original source/tool identities or dependency closure changed during the build.
    """
    directory = build.directory.resolve()
    data = load_json_object(directory / "compilation.json")
    schema = load_json_object(ROOT / "amp-plugin-build.schema.json")
    errors = list(
        Draft202012Validator({"$defs": schema["$defs"], "$ref": "#/$defs/preparation"}).iter_errors(
            data
        )
    )
    if errors:
        message = "AMP plugin preparation invalid: " + errors[0].message
        raise ValueError(message)
    generation = load_json_object(directory / "generation.json")
    if (
        data.get("schema") != "loop-timing-witness.amp-plugin-preparation.v1"
        or data.get("stage") != "compilation"
        or data.get("identity") != original_identity(build)
        or generation
        != {"schema": data["schema"], "stage": "generation", "identity": data["identity"]}
        or data.get("generation_sha256") != sha256_of_file(directory / "generation.json")
    ):
        message = "AMP plugin preparation or original build inputs changed"
        raise ValueError(message)
    for name, digest in data["dependency_records"].items():
        if sha256_of_file(Path(name)) != digest:
            message = "AMP plugin pre-compilation dependency record changed"
            raise ValueError(message)
    for name, digest in data["build_files"].items():
        if sha256_of_file(Path(name)) != digest:
            message = "AMP plugin generated build input changed during compilation"
            raise ValueError(message)
    original = dependency_hashes(tuple(Path(name) for name in data["dependency_records"]), ROOT)
    if original != data["dependencies"] or dependencies != original:
        message = "AMP plugin source/header dependency changed during compilation"
        raise ValueError(message)
    return data


def main(argv: list[str] | None = None) -> int:
    """Freeze one actual original plugin build stage through the public command line.

    Parameters
    ----------
    argv
        Explicit arguments or process arguments.

    Returns
    -------
    int
        Zero after exclusive complete freeze, one after retained refusal.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=("generation", "compilation"))
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--sdk", required=True, type=Path)
    parser.add_argument("--cc", required=True)
    parser.add_argument("--cxx", required=True)
    parser.add_argument("--thermal", required=True, type=int)
    parser.add_argument("--fifo-address-bits", required=True, type=int)
    parser.add_argument("--runtime-root", type=Path)
    args = parser.parse_args(argv)
    try:
        path = freeze_plugin(
            PluginBuild(
                args.directory,
                args.source,
                args.sdk,
                args.cc,
                args.cxx,
                args.thermal,
                args.fifo_address_bits,
                args.runtime_root,
            ),
            args.stage,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"AMP plugin preparation: FAIL: {error}", file=sys.stderr)
        return 1
    print(f"AMP plugin preparation: PASS: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
