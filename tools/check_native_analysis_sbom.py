# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete native analysis dependency SBOM verification

"""Verify a generated CycloneDX inventory against the actual locked Cargo package."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

from cyclonedx.schema import SchemaVersion
from cyclonedx.validation.json import JsonStrictValidator

from check_analysis_package import audit as package_audit
from check_analysis_package import read_package_file
from manifest_io import parse_json_object

_TOOL = [{"vendor": "CycloneDX", "name": "cargo-cyclonedx", "version": "0.5.9"}]


def _metadata(crate: Path) -> dict[str, Any]:
    """Read fresh metadata through the actual locked offline Cargo command.

    Parameters
    ----------
    crate
        Complete maintained analysis package.

    Returns
    -------
    dict[str, Any]
        Original successfully decoded Cargo metadata.

    Raises
    ------
    ValueError
        If Cargo is unavailable or its output is not a JSON object.
    subprocess.CalledProcessError
        If the real metadata command refuses its source inputs.
    subprocess.TimeoutExpired
        If metadata exceeds its finite execution allocation.
    """
    cargo = shutil.which("cargo")
    if cargo is None:
        message = "Cargo is unavailable"
        raise ValueError(message)
    result = subprocess.run(
        [
            cargo,
            "metadata",
            "--offline",
            "--locked",
            "--format-version",
            "1",
            "--manifest-path",
            str(crate / "Cargo.toml"),
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )
    return parse_json_object(result.stdout, "Cargo metadata")


def _correspondence(
    bom: dict[str, Any], lock: dict[str, Any], metadata: dict[str, Any]
) -> list[str]:
    """Compare the complete generated inventory with actual source metadata.

    Parameters
    ----------
    bom
        Schema-validated generated document.
    lock
        Complete maintained Cargo lock.
    metadata
        Fresh original Cargo package, target and dependency graph data.

    Returns
    -------
    list[str]
        First authored identity, population or graph contradiction, or no findings.
    """
    packages = {item["id"]: item for item in metadata["packages"]}
    owner = packages[metadata["resolve"]["root"]]
    component = bom["metadata"]["component"]
    if (
        (component["name"], component["version"]) != (owner["name"], owner["version"])
        or component["licenses"] != [{"expression": owner["license"]}]
        or bom["metadata"]["tools"] != _TOOL
    ):
        return ["root package, licence or generator identity differs"]
    targets = {
        ("application" if target["kind"] == ["bin"] else "library", target["name"])
        for target in owner["targets"]
        if target["kind"] in (["lib"], ["bin"])
    }
    observed_targets = {(item["type"], item["name"]) for item in component["components"]}
    if (
        observed_targets != targets
        or len(observed_targets) != len(component["components"])
        or any(item["version"] != owner["version"] for item in component["components"])
    ):
        return ["native library and executable target inventory differs"]
    expected = {
        (item["name"], item["version"]): item for item in lock["package"] if "source" in item
    }
    observed = {(item["name"], item["version"]): item for item in bom["components"]}
    if len(observed) != len(bom["components"]) or observed.keys() != expected.keys():
        return ["complete unique registry package population differs"]
    ids = {metadata["resolve"]["root"]: component["bom-ref"]}
    for package_id, package in packages.items():
        if package_id == metadata["resolve"]["root"]:
            continue
        key = (package["name"], package["version"])
        item = observed[key]
        if (
            item["bom-ref"] != package_id
            or item["purl"] != f"pkg:cargo/{package['name']}@{package['version']}"
            or item["hashes"] != [{"alg": "SHA-256", "content": expected[key]["checksum"]}]
            or item["licenses"] != [{"expression": package["license"].replace("/", " OR ")}]
        ):
            return ["registry archive, package URL or declared licence differs"]
        ids[package_id] = package_id
    graph = {
        ids[node["id"]]: {ids[dependency] for dependency in node["dependencies"]}
        for node in metadata["resolve"]["nodes"]
    }
    actual = {node["ref"]: set(node.get("dependsOn", [])) for node in bom["dependencies"]}
    if len(actual) != len(bom["dependencies"]) or actual != graph:
        return ["complete locked dependency graph differs"]
    return []


def audit(root: Path, sbom: Path) -> list[str]:
    """Verify the complete native SBOM through schema and fresh Cargo metadata.

    Parameters
    ----------
    root
        Actual repository containing the analysis crate and its canonical source owners.
    sbom
        Complete generated CycloneDX 1.5 JSON file; regular, unlinked and at most 256 KiB.

    Returns
    -------
    list[str]
        Authored findings for invalid inputs, metadata, inventory or graph; empty on success.
        The inventory identifies source packages and target names, not built-binary digests.
    """
    try:
        if package_audit(root):
            return ["analysis package source or reviewed licence bindings differ"]
        raw = read_package_file(sbom)
        bom = parse_json_object(raw, "native analysis SBOM")
        if (
            bom.get("specVersion") != "1.5"
            or JsonStrictValidator(SchemaVersion.V1_5).validate_str(raw.decode("utf-8")) is not None
        ):
            return ["document does not match CycloneDX 1.5"]
        crate = root / "analysis/rust"
        lock = tomllib.loads(read_package_file(crate / "Cargo.lock").decode("utf-8"))
        return _correspondence(bom, lock, _metadata(crate))
    except (
        OSError,
        UnicodeError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ):
        return ["SBOM inputs or Cargo metadata are unavailable or invalid"]


def main(argv: list[str] | None = None) -> int:
    """Check a native analysis dependency inventory using the public command.

    Parameters
    ----------
    argv
        Command arguments; None reads the process arguments.

    Returns
    -------
    int
        Zero for a complete matching inventory, one for any authored finding.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sbom", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    findings = audit(args.root, args.sbom)
    for finding in findings:
        print(f"native-analysis-sbom: FAIL {finding}")
    if findings:
        return 1
    print("native-analysis-sbom: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
