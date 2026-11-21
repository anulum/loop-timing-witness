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
- names, outside the seat trailer, an agent seat identifier, a coordination
  record name, the internal reviewer or a hub event citation;
- uses self-applied superlatives or internal quality labels.

A coordination record name is matched by its shape: a capitalised prefix of
one or more segments, then ``_`` and a dashed date or a compact UTC stamp, so
a new record prefix needs no list update. Seat prefixes and the reviewer's
name are compared by the SHA-256 digest of the word, so this public file
names neither. The rule is the commit body policy, version 2, of the
coordination tools; it judges each new message, not earlier history.

Lines starting with ``#`` are removed first, as Git does for an edited
message.
"""

from __future__ import annotations

import argparse
import hashlib
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
SEAT_NAME: Final = re.compile(r"\b([A-Za-z]+)-[0-9A-Fa-f]{4,}\b")
SEAT_PREFIX_DIGESTS: Final = frozenset(
    {
        "c857d09db23e6822e3600bc06ad8d58f92ed62bc8efd81c753f77048662cb97d",
        "57de4cf40144bdf7d00010f2f5557a7d642c2b9705309bfade167dd313e2ca93",
        "add92b9cde2bdbf3daaf65a0db79e9b1a7fa428b71b4d6ce38c742eb6dca0c1c",
        "5d72436256ada53828b51895a94bb8489e9f1ac4fe937a8024ef1594e7045ff6",
        "e4f9c522e1c89280e9561b825f4f24fe32b51ff82d61e5c2b1dfd0321c35a90b",
        "67f2d22514622d1be30c14ee9f3cb104503a159a33a656ca91a1953aa9616429",
        "fc5a1047f5919892fcdf8aa79ea5d6bb6531b5c176939ef0110906cb225941c1",
    }
)
RECORD_NAME: Final = re.compile(
    r"(?<![A-Za-z0-9])[A-Z][A-Z0-9]*(?:_[A-Z][A-Z0-9]*)*"
    r"_(?:\d{4}-\d{2}-\d{2}(?:T\d{4,6}Z?)?|\d{8}T\d{4,6}Z?)"
)
CAPITAL_WORD: Final = re.compile(r"\b[A-Z]+\b")
REVIEWER_DIGESTS: Final = frozenset(
    {"b336d7bb3299feff86048893005c2a64066d3fcf32b1618bd95e770ddb21a3fd"}
)
HUB_EVENT: Final = re.compile(r"\b(?:hub|event|seq)\s+#?\d{5,}\b", re.IGNORECASE)
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


def _digest(word: str) -> str:
    """Return the SHA-256 digest of one word as lowercase hexadecimal.

    Parameters
    ----------
    word
        Word compared against a digest set.

    Returns
    -------
    str
        The 64-character digest.
    """
    return hashlib.sha256(word.encode("utf-8")).hexdigest()


def _identifier_findings(lines: list[str]) -> list[str]:
    """Report each kind of internal identifier the message names, once per name.

    Parameters
    ----------
    lines
        Message lines without comment lines. The seat trailer is left out
        here; its own rule judges it.

    Returns
    -------
    list[str]
        ``"<kind> in the message: <names>"`` for each kind found, every name
        listed once in the order it first appears.
    """
    text = "\n".join(line for line in lines if not SEAT_PREFIX.match(line))
    kinds = (
        (
            "agent seat identifier",
            [
                match.group(0)
                for match in SEAT_NAME.finditer(text)
                if _digest(match.group(1).lower()) in SEAT_PREFIX_DIGESTS
            ],
        ),
        ("coordination record name", [match.group(0) for match in RECORD_NAME.finditer(text)]),
        (
            "internal reviewer name",
            [
                match.group(0)
                for match in CAPITAL_WORD.finditer(text)
                if _digest(match.group(0)) in REVIEWER_DIGESTS
            ],
        ),
        ("hub event citation", [match.group(0) for match in HUB_EVENT.finditer(text)]),
    )
    return [
        f"{kind} in the message: {', '.join(dict.fromkeys(names))}"
        for kind, names in kinds
        if names
    ]


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
    findings.extend(_identifier_findings(lines))
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
    except OSError, UnicodeDecodeError:
        print("commit-message: cannot read message file", file=sys.stderr)
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
