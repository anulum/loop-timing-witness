# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — measurement-domain manifest validator

"""Preserve the repository validate_measurement_domain entry point using the installed package."""

import sys
from pathlib import Path

from loop_timing_witness.validate_measurement_domain import (
    GROUP,
    MAX_GRAY_FIFO_DEPTH,
    MIN_GRAY_FIFO_DEPTH,
    NANOSECONDS_PER_SECOND,
    PERIODIC_PROFILE,
    PROJECT,
    REQUIRED_RECORD_FIELDS,
    TYPE_WIDTH_BYTES,
    RegistryResult,
    registry_cross_check,
    schema_findings,
    semantic_findings,
    validate,
)
from loop_timing_witness.validate_measurement_domain import (
    main as package_main,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPOSITORY_ROOT / "measurement-domain.json"
DEFAULT_SCHEMA = REPOSITORY_ROOT / "measurement-domain.schema.json"

__all__ = [
    "DEFAULT_MANIFEST",
    "DEFAULT_SCHEMA",
    "GROUP",
    "MAX_GRAY_FIFO_DEPTH",
    "MIN_GRAY_FIFO_DEPTH",
    "NANOSECONDS_PER_SECOND",
    "PERIODIC_PROFILE",
    "PROJECT",
    "REPOSITORY_ROOT",
    "REQUIRED_RECORD_FIELDS",
    "TYPE_WIDTH_BYTES",
    "RegistryResult",
    "main",
    "registry_cross_check",
    "schema_findings",
    "semantic_findings",
    "validate",
]


def main(argv: list[str] | None = None) -> int:
    """Validate repository inputs through the package CLI with repository defaults.

    Parameters
    ----------
    argv
        Explicit arguments, or ``None`` for process arguments.

    Returns
    -------
    int
        Original validator status for the selected manifest and schema.
    """
    return package_main(argv, default_manifest=DEFAULT_MANIFEST, default_schema=DEFAULT_SCHEMA)


if __name__ == "__main__":
    sys.exit(main())
