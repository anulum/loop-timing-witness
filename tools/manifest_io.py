# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — strict JSON input and atomic output primitives

"""Preserve the repository manifest_io entry point using the installed package."""

from loop_timing_witness.manifest_io import (
    canonical_json_bytes,
    load_json_object,
    parse_json_object,
    sha256_of_file,
    write_bytes_atomic,
)

__all__ = [
    "canonical_json_bytes",
    "load_json_object",
    "parse_json_object",
    "sha256_of_file",
    "write_bytes_atomic",
]
