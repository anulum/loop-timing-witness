# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — receipt schema locations shared with the native analysis

"""Build the receipt schema-location corpus from Python and hold it committed.

Each group changes one node of a valid native-run metadata document or host
load receipt and records the failing locations Python's ``schema_locations``
reports for the committed schema. The native crate's unit tests read the same
file and require the same locations.
"""

from __future__ import annotations

import json
from typing import Any, Final

from test_control_schema_corpus import cases_of

from conftest import REPOSITORY_ROOT
from loop_timing_witness.manifest_io import load_json_object
from loop_timing_witness.validate_measurement_domain import schema_locations

CORPUS: Final = REPOSITORY_ROOT / "analysis/rust/tests/data/control-receipt-schema-locations.json"
NATIVE: Final[dict[str, Any]] = json.loads(
    '{"artifacts":{"configuration":{"bytes":0,"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},"events":{"bytes":0,"sha256":"aaaaaaaaaaaaaaaaaaaa'
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},"tracking_raw":{"bytes":0,"sha256":"a'
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}},"coefficients":{"'
    'derivative_decay":-2147483648,"derivative_gain":-2147483648,"integral_max":-21474836'
    '48,"integral_min":-2147483648,"ki_period":-2147483648,"kp":-2147483648,"output_max":'
    '-2147483648,"output_min":-2147483648,"position_gain":-2147483648,"reference_gain":-2'
    '147483648,"velocity_gain":-2147483648},"controller":"pid","crypto_library":{"algorit'
    'hm":"sha256","header_version_number":805306368,"runtime_version_number":805306368},"'
    'cycles":1,"fault":{"cycle":0,"duration_periods":0,"kind":"none"},"host_policy":{"aff'
    'inity_cpus":[0],"nice":-20,"observed_cpu":0,"priority":0,"requested_cpu":-1,"request'
    'ed_priority":-1,"requested_scheduler":-1,"scheduler":0},"overload":{"iterations":0,"'
    'modeled_nanoseconds":0},"period_ticks":1,"reference":{"amplitude":-2147483648,"mode"'
    ':0,"offset":-2147483648,"phase":0,"ramp":-2147483648},"result":{"misses":0,"overflow'
    '":0,"records":0,"safe":false,"samples":0},"schema":"loop-timing-witness.native-run.v'
    '1","source_kind":"rtl_simulation","thermal":false}'
)
HOST_LOAD: Final[dict[str, Any]] = json.loads(
    '{"checksum":0,"counters":{"arithmetic_operations":0,"bytes_read":0,"bytes_received":'
    '0,"bytes_sent":0,"bytes_written":0,"chunks":1,"datagrams":0,"fsyncs":0,"idle_waits":'
    '0,"memory_touches":0},"finished_ns":1,"native_finished_ns":1,"native_pid":1,"native_'
    'returncode":-255,"native_started_ns":1,"network_scope":null,"policy":{"affinity_cpus'
    '":[0],"nice":-20,"priority":0,"scheduler":0},"profile":"idle","python_version":"1.2.'
    '3","requested_cpu":0,"schema":"loop-timing-witness.host-load.v1","started_ns":1,"sto'
    'rage_scope":null,"worker_pid":1,"working_set_bytes":4096}'
)


def corpus() -> dict[str, Any]:
    """Build the receipt corpus from the committed schemas and valid documents.

    Returns
    -------
    dict[str, Any]
        Valid base documents and one group of changes per node.
    """
    native = load_json_object(REPOSITORY_ROOT / "native-run.schema.json")
    host_load = load_json_object(REPOSITORY_ROOT / "host-load.schema.json")
    return {
        "schema": "loop-timing-witness.control-receipt-schema-locations.v1",
        "bases": {"native": NATIVE, "host_load": HOST_LOAD},
        "native": cases_of("native", NATIVE, native, 99),
        "host_load": cases_of("host_load", HOST_LOAD, host_load, 99),
    }


def test_bases_are_valid() -> None:
    """Both base documents satisfy their schemas."""
    assert (
        schema_locations(NATIVE, load_json_object(REPOSITORY_ROOT / "native-run.schema.json")) == []
    )
    assert (
        schema_locations(HOST_LOAD, load_json_object(REPOSITORY_ROOT / "host-load.schema.json"))
        == []
    )


def test_committed_corpus_equals_python_locations() -> None:
    """The committed corpus is exactly what Python's schema locations give."""
    text = json.dumps(corpus(), ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    assert CORPUS.read_text(encoding="utf-8") == text + "\n"
    assert CORPUS.with_name(CORPUS.name + ".license").is_file()
