# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original native plugin receipt and live build closure admission

"""Preserve the repository amp_plugin_receipt entry point using the installed package."""

from loop_timing_witness.amp_plugin_receipt import (
    ROOT,
    admit_plugin,
    build_identities,
    decode_plugin_receipt,
)

__all__ = [
    "ROOT",
    "admit_plugin",
    "build_identities",
    "decode_plugin_receipt",
]
