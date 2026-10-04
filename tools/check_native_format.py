# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — maintained C and C++ formatting

"""Check every enrolled C/C++ source and header with the pinned formatter."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from check_source_gates import LANGUAGES, audit

from repository_files import candidate_files

FORMATTER_VERSION = "18.1.3"
NATIVE_LANGUAGES = frozenset({"c", "cxx", "headers"})


def main(argv: list[str] | None = None) -> int:
    """Check the complete Git source candidate without changing its bytes.

    Parameters
    ----------
    argv
        Arguments without the executable; None reads sys.argv.

    Returns
    -------
    int
        Zero for enrolled, formatted native source; one for a missing tool,
        invalid enrolment, unsupported formatter or formatting discrepancy.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--formatter", default=os.environ.get("WITNESS_CLANG_FORMAT", "clang-format-18")
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    findings = audit(root)
    if findings:
        for finding in findings:
            print(f"native-format: FAIL {finding}")
        return 1
    try:
        style = root / ".clang-format"
        if not style.is_file():
            print("native-format: FAIL repository .clang-format is missing")
            return 1
        paths = [
            str(root / name)
            for name in candidate_files(root)
            if LANGUAGES.get(Path(name).suffix) in NATIVE_LANGUAGES
        ]
        if not paths:
            print("native-format: FAIL no maintained C/C++ sources or headers")
            return 1
        version = subprocess.run(  # noqa: S603 - Caller selects the formatter; no shell is used.
            [args.formatter, "--version"], capture_output=True, text=True, check=True
        )
        if re.search(r"\bclang-format version 18\.1\.3(?:\s|$)", version.stdout) is None:
            print(
                f"native-format: FAIL expected clang-format {FORMATTER_VERSION}; "
                f"received {version.stdout.strip()}"
            )
            return 1
        result = subprocess.run(  # noqa: S603 - Caller selects the formatter; no shell is used.
            [
                args.formatter,
                f"--style=file:{style}",
                "--dry-run",
                "--Werror",
                "--ferror-limit=0",
                *paths,
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"native-format: FAIL {exc}")
        return 1
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        print(f"native-format: FAIL files={len(paths)}")
    else:
        print(f"native-format: PASS files={len(paths)}")
    return int(result.returncode != 0)


if __name__ == "__main__":
    sys.exit(main())
