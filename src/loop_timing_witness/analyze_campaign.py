# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — repeat campaign command

"""Analyse every repeat of one run configuration and write the campaign report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .campaign_analysis import build_campaign_report
from .campaign_manifest import load_campaign
from .campaign_outputs import write_campaign_report


def main(argv: list[str] | None = None) -> int:
    """Run the repeat campaign command-line entry point.

    Parameters
    ----------
    argv
        Arguments without executable name, or ``None`` for ``sys.argv``.

    Returns
    -------
    int
        Zero for a published report whose campaign is complete, two for a
        published report of an incomplete campaign, one when the campaign is
        refused or the report cannot be written.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path, help="versioned repeat campaign manifest JSON")
    parser.add_argument("--output-dir", required=True, type=Path, help="new report directory")
    args = parser.parse_args(argv)
    try:
        report = build_campaign_report(load_campaign(args.campaign))
        write_campaign_report(args.output_dir, report)
    except (OSError, ValueError) as error:
        print(f"repeat campaign: FAIL: {error}", file=sys.stderr)
        return 1
    if report["status"] != "complete":
        print(f"repeat campaign: INCOMPLETE: {args.output_dir}")
        for item in report["plan"]["nonconformities"]:
            print(f"  {item}")
        return 2
    print(f"repeat campaign: COMPLETE: {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
