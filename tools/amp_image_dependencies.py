# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original firmware compiler dependency closure

"""Preserve the repository amp_image_dependencies entry point using the installed package."""

from loop_timing_witness.amp_image_dependencies import (
    HASH_SCHEMA,
    RECORD_COUNT,
    dependency_index,
    image_dependency_hashes,
    image_dependency_record_count,
    snapshot_image_dependencies,
    validate_image_dependency_snapshot,
    verify_precompile_dependencies,
)

__all__ = [
    "HASH_SCHEMA",
    "RECORD_COUNT",
    "dependency_index",
    "image_dependency_hashes",
    "image_dependency_record_count",
    "snapshot_image_dependencies",
    "validate_image_dependency_snapshot",
    "verify_precompile_dependencies",
]
