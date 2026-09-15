# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — capability inventory generation and drift check

"""Generate the public capability inventory from the measurement-domain manifest.

The inventory is the repository's public statement of implemented measurement
capability. It is derived, never hand-edited: project identity, evidence
maturity, capabilities and claims are copied from ``measurement-domain.json``
and the manifest's SHA-256 is embedded, so any edit to either file is
detectable. Generation refuses a manifest that fails
``validate_measurement_domain.py``, so the inventory can never publish an
inconsistent state. ``--check`` fails when the committed inventory differs
byte for byte from a fresh generation; ``--write`` regenerates it atomically.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Final

from manifest_io import (
    canonical_json_bytes,
    load_json_object,
    sha256_of_file,
    write_bytes_atomic,
)
from validate_measurement_domain import DEFAULT_MANIFEST, DEFAULT_SCHEMA, validate

INVENTORY_SCHEMA: Final = "loop-timing-witness.capability-inventory.v1"
INVENTORY_SCHEMA_VERSION: Final = "1.0.0"
DEFAULT_INVENTORY: Final = DEFAULT_MANIFEST.parent / "capability-inventory.json"


def generate_inventory(manifest_path: Path, schema_path: Path) -> dict[str, Any]:
    """Build the inventory object from one validated manifest.

    Parameters
    ----------
    manifest_path
        Manifest file to project.
    schema_path
        JSON Schema the manifest must satisfy.

    Returns
    -------
    dict[str, Any]
        The inventory object, ready for canonical serialisation.

    Raises
    ------
    ValueError
        If the manifest fails validation; the message lists every finding.
    """
    findings, _ = validate(manifest_path, schema_path, None)
    if findings:
        message = "manifest is invalid: " + "; ".join(findings)
        raise ValueError(message)
    manifest = load_json_object(manifest_path)
    return {
        "schema": INVENTORY_SCHEMA,
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "project": manifest["project"],
        "evidence_maturity": manifest["evidence_maturity"],
        "implemented_capability_count": len(manifest["capabilities"]),
        "capabilities": manifest["capabilities"],
        "claims": manifest["claims"],
        "source": {
            "manifest_path": manifest_path.name,
            "manifest_sha256": sha256_of_file(manifest_path),
        },
    }


def main(argv: list[str] | None = None) -> int:
    """Run the capability inventory command-line interface.

    Parameters
    ----------
    argv
        Argument vector without the program name; ``None`` reads
        ``sys.argv``.

    Returns
    -------
    int
        ``0`` for an in-sync check or a completed write, ``1`` for drift, an
        unreadable inventory or an invalid manifest.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        generated = canonical_json_bytes(generate_inventory(args.manifest, args.schema))
    except (OSError, ValueError) as exc:
        print(f"capability-inventory: FAIL {exc}")
        return 1
    if args.write:
        try:
            write_bytes_atomic(args.inventory, generated)
        except OSError as exc:
            print(f"capability-inventory: FAIL cannot write inventory: {exc}")
            return 1
        print(f"capability-inventory: wrote {args.inventory}")
        return 0
    try:
        committed = args.inventory.read_bytes()
    except OSError as exc:
        print(f"capability-inventory: FAIL cannot read committed inventory: {exc}")
        return 1
    if committed != generated:
        print("capability-inventory: FAIL drift between manifest and inventory")
        return 1
    print("capability-inventory: PASS in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
