# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — explicit original RV64 Rust compiler argument vectors

"""Preserve fixed original Rust vectors using the installed analysis package."""

from loop_timing_witness.amp_rust_vectors import (
    ADAPTER,
    CORE,
    LIBRARY,
    TARGET,
    rust_vectors,
)

__all__ = ["ADAPTER", "CORE", "LIBRARY", "TARGET", "rust_vectors"]
