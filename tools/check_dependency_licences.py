# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — development dependency licence policy guard

"""Fail closed when the development lock and its reviewed licence record disagree.

``development-dependency-licences.json`` records, for every package pinned in
``requirements-dev.txt``, the exact version and the SPDX licence expression
established by reading the package's licence files and index metadata. The
guard proves that:

- every pinned package has exactly one record and every record has a pin, with
  identical versions, so no dependency enters or changes without a licence
  review;
- every record holds a well-formed SPDX expression (identifiers joined by
  ``AND``, ``OR`` and ``WITH`` with balanced parentheses);
- every identifier in every expression is in the reviewed
  ``allowed_licences`` list.

The development tools are executed, never distributed with or linked into
repository content, so copyleft tool licences place no obligation on this
repository; they are still recorded and must be allowed explicitly.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Final

from manifest_io import load_json_object

POLICY_SCHEMA: Final = "loop-timing-witness.dependency-licences.v1"
POLICY_SCHEMA_VERSION: Final = "1.0.0"
REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
DEFAULT_POLICY: Final = REPOSITORY_ROOT / "development-dependency-licences.json"
PIN: Final = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s\\;]+)", re.MULTILINE)
EXPRESSION_TOKEN: Final = re.compile(r"\(|\)|[A-Za-z0-9.+-]+")
OPERATORS: Final = frozenset({"AND", "OR"})
RESERVED_SYMBOLS: Final = OPERATORS | {")", "WITH"}


def normalise_name(name: str) -> str:
    """Normalise a distribution name as the package index does.

    Parameters
    ----------
    name
        Distribution name as written.

    Returns
    -------
    str
        Lowercase name with runs of ``-``, ``_`` and ``.`` replaced by ``-``.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def locked_pins(lock_text: str) -> dict[str, str]:
    """Read the ``name==version`` pins of a requirements lock.

    Parameters
    ----------
    lock_text
        Lock file content.

    Returns
    -------
    dict[str, str]
        Version by normalised distribution name.

    Raises
    ------
    ValueError
        If a distribution is pinned more than once.
    """
    pins: dict[str, str] = {}
    for name, version in PIN.findall(lock_text):
        key = normalise_name(name)
        if key in pins:
            message = f"lock pins {key} more than once"
            raise ValueError(message)
        pins[key] = version
    return pins


def expression_identifiers(expression: str) -> list[str]:
    """Parse one SPDX licence expression and return its licence identifiers.

    Grammar: ``expression := term (("AND" | "OR") term)*`` and
    ``term := "(" expression ")" | identifier ["WITH" identifier]``. The
    exception identifier after ``WITH`` is not returned.

    Parameters
    ----------
    expression
        Expression text.

    Returns
    -------
    list[str]
        Licence identifiers in order of appearance.

    Raises
    ------
    ValueError
        If the text contains characters outside the grammar or the token
        sequence does not match it.
    """
    stripped = re.sub(r"\s+", "", EXPRESSION_TOKEN.sub("", expression))
    if stripped:
        message = f"unexpected characters {stripped!r} in {expression!r}"
        raise ValueError(message)
    symbols = EXPRESSION_TOKEN.findall(expression)
    malformed = f"malformed licence expression {expression!r}"
    identifiers: list[str] = []
    depth = 0
    expecting_operand = True
    index = 0
    while index < len(symbols):
        symbol = symbols[index]
        if expecting_operand and symbol == "(":
            depth += 1
        elif expecting_operand and symbol not in RESERVED_SYMBOLS:
            identifiers.append(symbol)
            expecting_operand = False
            index += _exception_length(symbols, index + 1, malformed)
        elif not expecting_operand and symbol == ")" and depth > 0:
            depth -= 1
        elif not expecting_operand and symbol in OPERATORS:
            expecting_operand = True
        else:
            raise ValueError(malformed)
        index += 1
    if expecting_operand or depth:
        raise ValueError(malformed)
    return identifiers


def _exception_length(symbols: list[str], index: int, malformed: str) -> int:
    """Measure an optional ``WITH <exception>`` clause after an identifier.

    Parameters
    ----------
    symbols
        Tokenised expression.
    index
        Position just after the licence identifier.
    malformed
        Error message for a clause without a valid exception identifier.

    Returns
    -------
    int
        ``2`` when a complete clause follows, ``0`` when none does.

    Raises
    ------
    ValueError
        If ``WITH`` is not followed by an exception identifier.
    """
    if index >= len(symbols) or symbols[index] != "WITH":
        return 0
    if index + 1 >= len(symbols) or symbols[index + 1] in RESERVED_SYMBOLS | {"("}:
        raise ValueError(malformed)
    return 2


def _policy_shape(policy: dict[str, Any]) -> list[str]:
    """Check the licence record's top-level shape.

    Parameters
    ----------
    policy
        Decoded licence record.

    Returns
    -------
    list[str]
        Shape violations; the record is evaluated only when this is empty.
    """
    findings = []
    if policy.get("schema") != POLICY_SCHEMA:
        findings.append(f"policy: schema must be {POLICY_SCHEMA!r}")
    if policy.get("schema_version") != POLICY_SCHEMA_VERSION:
        findings.append(f"policy: schema_version must be {POLICY_SCHEMA_VERSION!r}")
    if not isinstance(policy.get("lock_file"), str):
        findings.append("policy: lock_file must be a relative path")
    allowed = policy.get("allowed_licences")
    if not (
        isinstance(allowed, list) and allowed and all(isinstance(item, str) for item in allowed)
    ):
        findings.append("policy: allowed_licences must be a non-empty list of identifiers")
    packages = policy.get("packages")
    if not isinstance(packages, dict) or not all(
        isinstance(record, dict)
        and set(record) == {"licence", "version"}
        and all(isinstance(value, str) for value in record.values())
        for record in packages.values()
    ):
        findings.append("policy: packages must map names to {licence, version} strings")
    return findings


def audit(policy_path: Path) -> list[str]:
    """Compare the licence record with its lock and licence allow-list.

    Parameters
    ----------
    policy_path
        Licence record file; ``lock_file`` inside it is resolved relative to
        this file's directory.

    Returns
    -------
    list[str]
        Findings; empty when the lock and record agree and every licence is
        allowed.
    """
    try:
        policy = load_json_object(policy_path)
    except (OSError, ValueError) as exc:
        return [f"policy unreadable: {exc}"]
    findings = _policy_shape(policy)
    if findings:
        return findings
    lock_path = policy_path.parent / policy["lock_file"]
    try:
        pins = locked_pins(lock_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return [f"lock unreadable: {exc}"]
    packages: dict[str, dict[str, str]] = policy["packages"]
    findings.extend(
        f"{name}: record name must be written in normalised form {normalise_name(name)!r}"
        for name in sorted(packages)
        if name != normalise_name(name)
    )
    recorded = {name: record for name, record in packages.items() if name == normalise_name(name)}
    allowed = set(policy["allowed_licences"])
    findings.extend(
        f"{name}: pinned but has no licence record" for name in sorted(set(pins) - set(recorded))
    )
    findings.extend(
        f"{name}: licence record without a pin" for name in sorted(set(recorded) - set(pins))
    )
    for name in sorted(set(pins) & set(recorded)):
        record = recorded[name]
        if record["version"] != pins[name]:
            findings.append(
                f"{name}: record version {record['version']} differs from pin {pins[name]}"
            )
        try:
            identifiers = expression_identifiers(record["licence"])
        except ValueError as exc:
            findings.append(f"{name}: {exc}")
            continue
        findings.extend(
            f"{name}: licence {identifier!r} is not in allowed_licences"
            for identifier in identifiers
            if identifier not in allowed
        )
    return findings


def main(argv: list[str] | None = None) -> int:
    """Run the dependency licence guard.

    Parameters
    ----------
    argv
        Argument vector without the program name; ``None`` reads
        ``sys.argv``.

    Returns
    -------
    int
        ``0`` when the lock and licence record agree, ``1`` otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy", type=Path, nargs="?", default=DEFAULT_POLICY)
    args = parser.parse_args(argv)
    findings = audit(args.policy)
    for finding in findings:
        print(f"dependency-licences: FAIL {finding}")
    if findings:
        return 1
    print("dependency-licences: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
