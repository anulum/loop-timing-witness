# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — strict JSON input and atomic output primitives

"""Preserve the repository manifest_io entry point using the installed package.

The strict JSON primitives come from ``loop_timing_witness.strict_json`` and the file
primitives from ``loop_timing_witness.manifest_io``; the tools import both here by one name.
"""

from loop_timing_witness.manifest_io import load_json_object, sha256_of_file, write_bytes_atomic
from loop_timing_witness.strict_json import (
    JsonInputRefusalError,
    canonical_json_bytes,
    parse_json_object,
)

__all__ = [
    "JsonInputRefusalError",
    "canonical_json_bytes",
    "load_json_object",
    "parse_json_object",
    "sha256_of_file",
    "write_bytes_atomic",
]
