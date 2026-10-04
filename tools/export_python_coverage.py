# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — Python coverage XML with unambiguous repository paths

"""Export collected Python coverage without collapsing equal basenames."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final

from coverage import Coverage

COMPLETE_COVERAGE: Final = 100.0


def main(argv: list[str] | None = None) -> int:
    """Render the existing coverage data with paths relative to the repository.

    Parameters
    ----------
    argv
        Command-line arguments; ``None`` reads the process arguments.

    Returns
    -------
    int
        Zero after the configured coverage threshold passes.

    Notes
    -----
    Data collection retains the production source set in ``pyproject.toml``.
    Only the XML reporter's source root changes after loading that data; measured
    files, excluded lines, executable statements and branch counts are preserved.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Destination Cobertura XML report")
    args = parser.parse_args(argv)
    measured = Coverage(config_file="pyproject.toml")
    measured.load()
    loaded = measured.get_data()
    try:
        measured.set_option("run:source", ["."])
        percent = measured.xml_report(outfile=str(args.output))
    finally:
        # With path aliases configured, reporting replaces the loaded SQLite
        # data by a remapped in-memory copy. Release both connections instead
        # of leaving them to the garbage collector of the calling process.
        loaded.close()
        measured.get_data().close(force=True)
    return 0 if percent == COMPLETE_COVERAGE else 1


if __name__ == "__main__":
    sys.exit(main())
