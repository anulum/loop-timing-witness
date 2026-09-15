# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — commit-message policy guard

"""Validate a commit message as the ``commit-msg`` hook.

Commit messages are public. The hook receives the pending message file and
rejects a message that:

- has a subject that is not a conventional ``type(scope): summary`` line of
  at most 72 characters;
- lacks exactly one required authorship line;
- lacks exactly one ``Seat:`` trailer whose identifier is a short lowercase
  alphanumeric seat identifier;
- has anything other than blank lines, the seat trailer and the authorship
  line from the seat trailer to the end of the message, which keeps every
  other trailer (co-author, session or tool attribution) out;
- carries a ``Co-Authored-By:`` line anywhere or a generated-by attribution;
- uses self-applied superlatives or internal quality labels.

Lines starting with ``#`` are removed first, as Git does for an edited
message.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Final

REQUIRED_AUTHORSHIP_LINE: Final = (
    "Authored by Anulum Fortis & Arcane Sapience (protoscience@anulum.li)"
)
SUBJECT: Final = re.compile(
    r"^(build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test)"
    r"(\([a-z0-9][a-z0-9-]*\))?: \S"
)
MAXIMUM_SUBJECT_LENGTH: Final = 72
SEAT_PREFIX: Final = re.compile(r"^\s*Seat:", re.IGNORECASE)
SEAT_TRAILER: Final = re.compile(r"^Seat: [a-z0-9]{2,16}$")
CO_AUTHOR: Final = re.compile(r"^\s*Co-Authored-By:", re.IGNORECASE)
GENERATED_ATTRIBUTION: Final = re.compile(r"\bgenerated (with|by)\b", re.IGNORECASE)
SUPERLATIVE: Final = re.compile(
    r"\b(best-in-class|comprehensive|cutting-edge|elite|groundbreaking|leveraging"
    r"|revolutionary|robust|sota|state-of-the-art|unrivalled|world-class)\b",
    re.IGNORECASE,
)


def _trailer_findings(lines: list[str], authorship: list[int]) -> list[str]:
    """Check the seat trailer, its identifier and the closing trailer block.

    Parameters
    ----------
    lines
        Message lines without comment lines.
    authorship
        Indices of lines equal to the required authorship line.

    Returns
    -------
    list[str]
        Trailer violations.
    """
    seats = [index for index, line in enumerate(lines) if SEAT_PREFIX.match(line)]
    if not seats:
        return ["missing `Seat: <seat-id>` trailer"]
    if len(seats) != 1:
        return ["expected exactly one `Seat: <seat-id>` trailer"]
    seat = seats[0]
    findings = []
    if SEAT_TRAILER.match(lines[seat].rstrip()) is None:
        findings.append("`Seat:` needs one lowercase alphanumeric identifier of 2-16 characters")
    if len(authorship) == 1 and seat > authorship[0]:
        findings.append("`Seat:` trailer must come before the authorship line")
    closing = [line for line in lines[seat + 1 :] if line.strip()]
    if any(line.strip() != REQUIRED_AUTHORSHIP_LINE for line in closing):
        findings.append("only the authorship line may follow the `Seat:` trailer")
    return findings


def message_findings(message: str) -> list[str]:
    """Return every policy violation of one commit message.

    Parameters
    ----------
    message
        Full commit-message text.

    Returns
    -------
    list[str]
        Violations; empty when the message is acceptable.
    """
    lines = [line for line in message.splitlines() if not line.startswith("#")]
    findings = []
    subject = next((line for line in lines if line.strip()), "")
    if SUBJECT.match(subject) is None:
        findings.append("subject must read `type(scope): summary` with a conventional type")
    if len(subject) > MAXIMUM_SUBJECT_LENGTH:
        findings.append(f"subject exceeds {MAXIMUM_SUBJECT_LENGTH} characters")
    authorship = [
        index for index, line in enumerate(lines) if line.strip() == REQUIRED_AUTHORSHIP_LINE
    ]
    if not authorship:
        findings.append("missing required authorship line")
    elif len(authorship) != 1:
        findings.append("expected exactly one authorship line")
    findings.extend(_trailer_findings(lines, authorship))
    if any(CO_AUTHOR.match(line) for line in lines):
        findings.append("`Co-Authored-By:` is forbidden")
    body = "\n".join(lines)
    if GENERATED_ATTRIBUTION.search(body):
        findings.append("generated-by attribution is forbidden")
    superlatives = sorted({match.group(0).lower() for match in SUPERLATIVE.finditer(body)})
    if superlatives:
        findings.append(f"self-applied quality terms are forbidden: {', '.join(superlatives)}")
    return findings


def main(argv: list[str] | None = None) -> int:
    """Run the commit-message hook.

    Parameters
    ----------
    argv
        Argument vector without the program name; ``None`` reads
        ``sys.argv``.

    Returns
    -------
    int
        ``0`` when the message is acceptable, ``1`` when it violates the
        policy or cannot be read.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("message_file", type=Path)
    args = parser.parse_args(argv)
    try:
        message = args.message_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"commit-message: cannot read {args.message_file}: {exc}", file=sys.stderr)
        return 1
    findings = message_findings(message)
    if not findings:
        return 0
    print("commit-message: rejected", file=sys.stderr)
    for finding in findings:
        print(f"  - {finding}", file=sys.stderr)
    print(
        f"required closing block:\n  Seat: <seat-id>\n  {REQUIRED_AUTHORSHIP_LINE}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
