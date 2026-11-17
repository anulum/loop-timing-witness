# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original native plugin receipt and live build closure admission

"""Admit actual native plugin receipts and refuse changed live build inputs or tools."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .amp_build_dependencies import dependency_hashes
from .manifest_io import (
    canonical_json_bytes,
    load_json_object,
    parse_bounded_json_object,
    sha256_of_file,
)
from .validate_measurement_domain import schema_locations

ROOT = Path(__file__).resolve().parent / "data"
# Every GCC-instrumented object registers its counters through this libgcov entry point.
_COUNTER_SYMBOL = b"__gcov_init"


def instrumentation_record(kind: str, compile_flags: str, link_flags: str) -> dict[str, Any] | None:
    """Return the receipt record of a measurement-only plugin variant, or None for production.

    Parameters
    ----------
    kind
        ``none`` for the production plugin, ``coverage`` for the counted variant.
    compile_flags
        Flags added to the device object, whitespace-separated; empty for production.
    link_flags
        Flags added to the shared-object link, whitespace-separated; empty for production.

    Returns
    -------
    dict of str to Any or None
        The ``instrumentation`` record, absent from a production receipt.

    Raises
    ------
    ValueError
        If the kind is unknown, or its flags are given for production or missing for coverage.
    """
    if kind not in ("none", "coverage"):
        message = "AMP plugin instrumentation must be none or coverage"
        raise ValueError(message)
    compile_list, link_list = compile_flags.split(), link_flags.split()
    counted = kind == "coverage"
    given = (bool(compile_list), bool(link_list))
    if given != (counted, counted):
        message = "AMP plugin instrumentation flags disagree with its kind"
        raise ValueError(message)
    if not counted:
        return None
    return {
        "kind": "gcov",
        "objects": ["plugin"],
        "compile_flags": compile_list,
        "link_flags": link_list,
    }


def library_instrumented(plugin: Path) -> bool:
    """Tell whether a plugin library carries GCC coverage counters.

    Parameters
    ----------
    plugin
        Linked plugin library.

    Returns
    -------
    bool
        Whether the library names the libgcov registration entry point.
    """
    return _COUNTER_SYMBOL in plugin.read_bytes()


def _identities_agree(data: dict[str, Any]) -> bool:
    """Tell whether the receipt repeats every preparation identity it depends on.

    Parameters
    ----------
    data
        Schema-valid plugin build receipt.

    Returns
    -------
    bool
        Whether the build identity fields equal the preparation's, every source,
        library, dependency, record and build file digest is a recorded dependency,
        and the preparation and its generation record are recorded beside each other.
    """
    preparation = data["preparation"]
    identity = preparation["identity"]
    preparation_path = data["preparation_path"]
    groups = [
        identity["sources"],
        identity["runtime_libraries"],
        *(compiler["runtime_libraries"] for compiler in identity["compilers"].values()),
        *(preparation[name] for name in ("dependencies", "dependency_records", "build_files")),
    ]
    return not (
        any(identity[name] != data[name] for name in identity if name != "sources")
        or any(
            data["dependencies"].get(name) != digest
            for group in groups
            for name, digest in group.items()
        )
        or data["dependencies"].get(preparation_path)
        != hashlib.sha256(canonical_json_bytes(preparation)).hexdigest()
        or not Path(preparation_path).name
        or data["dependencies"].get(str(Path(preparation_path).with_name("generation.json")))
        != preparation["generation_sha256"]
    )


def decode_plugin_receipt(content: bytes, *, instrumented: bool = False) -> dict[str, Any]:
    """Require the complete versioned original native compiler and SDK receipt shape.

    Parameters
    ----------
    content
        Original receipt bytes, not a reconstructed selection of metadata.
    instrumented
        True only for a coverage run, which admits the counted variant and nothing else;
        every other caller admits production receipts only.

    Returns
    -------
    dict of str to Any
        Complete original schema-valid receipt.

    Raises
    ------
    ValueError
        If JSON, schema identifier, types, bounds or required build identity fields are invalid,
        the preparation path names no file beside which its generation record would lie, or the
        receipt's instrumentation record disagrees with the selection.
    """
    data = parse_bounded_json_object(content, "AMP plugin build")
    locations = schema_locations(data, load_json_object(ROOT / "amp-plugin-build.schema.json"))
    if locations:
        message = (
            f"AMP plugin build receipt {locations[0]}: does not satisfy the AMP plugin build schema"
        )
        raise ValueError(message)
    if not _identities_agree(data):
        message = "AMP plugin receipt omits or contradicts original preparation identities"
        raise ValueError(message)
    if "instrumentation" in data and not instrumented:
        message = "AMP plugin build is a coverage measurement variant, never admitted evidence"
        raise ValueError(message)
    if instrumented and "instrumentation" not in data:
        message = "AMP coverage run requires an instrumented plugin build"
        raise ValueError(message)
    return data


def build_identities(data: dict[str, Any]) -> dict[str, str]:
    """Enumerate original compiler-recorded dependencies, link objects and selected tool identities.

    Parameters
    ----------
    data
        Original receipt admitted by decode_plugin_receipt.

    Returns
    -------
    dict of str to str
        Exact original absolute paths and expected hashes; conflicting duplicate identities refused.
    """
    identities: dict[str, str] = {}
    tools = [data["verilator"], data["verilator"]["backend"], *data["build_tools"].values()]
    for compiler in data["compilers"].values():
        tools.extend([compiler["driver"], *compiler["programs"].values()])
    groups = [
        data[field]
        for field in ("dependencies", "dependency_records", "link_inputs", "runtime_libraries")
    ]
    groups.extend({item["path"]: item["sha256"]} for item in tools)
    for group in groups:
        for name, digest in group.items():
            if name in identities and identities[name] != digest:
                message = "AMP plugin build has conflicting original identities"
                raise ValueError(message)
            identities[name] = digest
    return identities


def admit_plugin(plugin: Path, *, instrumented: bool = False) -> tuple[bytes, dict[str, Any]]:
    """Verify the selected actual library and its complete original live build closure.

    Parameters
    ----------
    plugin
        Explicit actual library, with original plugin.json beside it.
    instrumented
        True only for a coverage run; see :func:`decode_plugin_receipt`.

    Returns
    -------
    tuple of bytes and dict of str to Any
        Unchanged original receipt bytes and schema-valid admitted identities.

    Raises
    ------
    OSError
        If the receipt, library, actual dependencies or selected tool files are unavailable.
    ValueError
        If the library or original compiler/source/header/link/tool bytes changed, the
        receipt's instrumentation record disagrees with the selection, or the library's own
        counters disagree with the record.
    """
    content = plugin.with_name("plugin.json").read_bytes()
    data = decode_plugin_receipt(content, instrumented=instrumented)
    if sha256_of_file(plugin) != data["plugin_sha256"]:
        message = "AMP plugin library differs from the original build receipt"
        raise ValueError(message)
    if library_instrumented(plugin) != instrumented:
        message = "AMP plugin library counters disagree with its build receipt"
        raise ValueError(message)
    for name, digest in build_identities(data).items():
        if sha256_of_file(Path(name)) != digest:
            message = "AMP plugin build input or tool changed: " + name
            raise ValueError(message)
    native = {"controller.d", "configuration.d", "plugin.d", "verilated.d", "verilated_threads.d"}
    names = {Path(name).name for name in data["dependency_records"]}
    links = {Path(name).name for name in data["link_inputs"]}
    expected_links = {name.removesuffix(".d") + ".o" for name in native}
    expected_links.add("Vaxi_control_witness__ALL.a")
    if (
        not native.issubset(names)
        or "Vaxi_control_witness__ALL.d" not in names
        or links != expected_links
    ):
        message = "AMP plugin build lacks complete native or model build roles"
        raise ValueError(message)
    for name in data["dependency_records"]:
        record = Path(name)
        directory = Path(data["working_directory"]) if record.name in native else record.parent
        recorded = dependency_hashes((record,), directory)
        if any(data["dependencies"].get(source) != digest for source, digest in recorded.items()):
            message = "AMP plugin receipt omits or contradicts compiler-recorded dependencies"
            raise ValueError(message)
    return content, data
