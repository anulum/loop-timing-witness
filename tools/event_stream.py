# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — binary event stream decoder

"""Preserve the repository event_stream entry point using the installed package."""

from loop_timing_witness.event_stream import (
    EVENT_RECORD,
    Event,
    decode_events,
)

__all__ = [
    "EVENT_RECORD",
    "Event",
    "decode_events",
]
