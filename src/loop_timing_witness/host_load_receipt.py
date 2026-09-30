# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — host load receipt validation and report custody

"""Validate bounded host work independently from simulated control-loop timing."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from jsonschema import Draft202012Validator

from .manifest_io import load_json_object, parse_json_object

if TYPE_CHECKING:
    from .run_manifest import RunInputs

ROOT = Path(__file__).resolve().parent / "data"
MAX_DATAGRAM_BYTES = 60000


def validate_host_load(content: bytes) -> dict[str, Any]:
    """Validate a completed worker receipt and its actual native execution bracket.

    Parameters
    ----------
    content
        Original receipt bytes; callers bind them to their capture digest.

    Returns
    -------
    dict of str to Any
        Schema-valid, internally consistent worker and native facts.

    Raises
    ------
    ValueError
        If schema, scheduling, resource scope, counters or time brackets disagree.
    """
    receipt = parse_json_object(content, "host load receipt")
    validator = Draft202012Validator(load_json_object(ROOT / "host-load.schema.json"))
    errors = list(validator.iter_errors(receipt))
    if errors:
        message = f"host load receipt invalid: {errors[0].message}"
        raise ValueError(message)
    profile = receipt["profile"]
    size = receipt["working_set_bytes"]
    if (
        receipt["worker_pid"] == receipt["native_pid"]
        or receipt["policy"]["affinity_cpus"] != [receipt["requested_cpu"]]
        or not receipt["started_ns"]
        <= receipt["native_started_ns"]
        < receipt["native_finished_ns"]
        <= receipt["finished_ns"]
        or receipt["network_scope"] != ("loopback_udp" if profile == "network" else None)
        or receipt["storage_scope"] != ("owned_file_fsync" if profile == "storage" else None)
        or (profile == "network" and size > MAX_DATAGRAM_BYTES)
    ):
        message = "host load policy, scope or native time bracket differs"
        raise ValueError(message)
    counters = receipt["counters"]
    chunks = counters["chunks"]
    expected = dict.fromkeys(counters, 0)
    expected["chunks"] = chunks
    if profile == "cpu":
        expected["arithmetic_operations"] = chunks * 4096
    elif profile == "memory":
        expected["memory_touches"] = chunks * ((size + 63) // 64)
    elif profile == "network":
        expected.update(datagrams=chunks, bytes_sent=chunks * size, bytes_received=chunks * size)
    elif profile == "storage":
        expected.update(fsyncs=chunks, bytes_written=chunks * size, bytes_read=chunks * size)
    else:
        expected["idle_waits"] = chunks
    if counters != expected:
        message = "host load counters differ from complete workload chunks"
        raise ValueError(message)
    return receipt


def attach_host_load(inputs: RunInputs, report: dict[str, Any]) -> None:
    """Attach hash-bound host work without treating wall time as fabric timing.

    Parameters
    ----------
    inputs
        Hash-verified capture inputs and schema-valid declaration.
    report
        Actual run analysis report being assembled.

    Raises
    ------
    ValueError
        If the workload or native exit status contradicts the captured declaration.
    """
    if "host_load" not in inputs.files:
        return
    receipt = validate_host_load(inputs.files["host_load"])
    native = parse_json_object(inputs.files["native_metadata"], "native metadata")
    if inputs.manifest["load_case"] != receipt["profile"] or receipt["native_returncode"] != int(
        bool(native["result"]["overflow"])
    ):
        message = "host load profile or native exit status contradicts the capture"
        raise ValueError(message)
    report["host_load"] = receipt
    report["input_sha256"]["host_load"] = inputs.manifest["host_load"]["sha256"]
    report["limits"].append(
        "Host load counters cover the whole worker span, including work before and after "
        "the enclosed native interval. Host monotonic time is not fabric event time. "
        "Loopback UDP does not measure NIC traffic; file fsync does not establish uncached "
        "block-device load. Host stress does not qualify processor timing or power."
    )
