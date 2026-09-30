# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — public original firmware admission before object compilation

"""Refuse changed original firmware inputs before any actual compiler object recipe runs."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from amp_prepared_inputs import admit_preparation


def main(argv: list[str] | None = None) -> int:
    """Verify original source, tool and preprocessing custody through the public CLI.

    Parameters
    ----------
    argv
        Explicit arguments or process command arguments.

    Returns
    -------
    int
        Zero for unchanged original preparation, one for retained input admission failure.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        admit_preparation(args.directory)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"AMP original preparation: FAIL: {error}", file=sys.stderr)
        return 1
    print("AMP original preparation: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
