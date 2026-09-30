# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — captured original compiler and simulator runtime libraries

"""Preserve the repository amp_runtime_snapshot entry point using the installed package."""

from loop_timing_witness.amp_runtime_snapshot import (
    HASH_SCHEMA,
    runtime_index,
    snapshot_runtime,
    validate_runtime_snapshot,
)

__all__ = [
    "HASH_SCHEMA",
    "runtime_index",
    "snapshot_runtime",
    "validate_runtime_snapshot",
]
