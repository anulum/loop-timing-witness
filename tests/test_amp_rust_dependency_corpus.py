# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — Rust dependency record corpus shared with the native analysis

"""Hold Python's shell lexing and Rust dependency record reader's outcomes in a shared corpus.

An AMP image built with the Rust kernel binds the sources that rustc's
dependency records name (``rust_dependency_hashes``), whose rules are split
with CPython's POSIX ``shlex.split``. The corpus holds:

- ``shlex.split`` on every text up to three characters over an alphabet of
  word, whitespace, quote, escape and non-ASCII characters, and on every text
  of four and five characters over the quote and escape core; the native
  tests rebuild the texts in the same order;
- the reader on named cases, every one a small file tree with its records:
  continuations, line ends, Unicode line breaks and whitespace, comments,
  targets, quoting, ``$$``, phony rules, escaping, empty and absolute names,
  symbolic links, missing files, the order of failing sources and records
  that are not UTF-8.

An outcome is the digests by name, Python's refusal text, or the text of the
``OSError`` the reader raises; the case directory is written ``<root>``.
"""

from __future__ import annotations

import itertools
import json
import shlex
from pathlib import Path
from typing import Any, Final

from amp_rust_dependencies import rust_dependency_hashes

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
CORPUS: Final = REPOSITORY_ROOT / "analysis/rust/tests/data/amp-rust-dependency-cases.json"
ALPHABET: Final = ("a", " ", "\t", "\n", "\r", "'", '"', "\\", "$", "#", "é", "\x0b", "\u2028")
CORE: Final = ("a", " ", "'", '"', "\\")
SHLEX_ERRORS: Final = ("No closing quotation", "No escaped character")
RUST_TREE: Final = {"source/a.rs": "fn a() {}\n", "source/b c.rs": "fn b() {}\n"}
RUST_RECORD: Final = "out.rmeta: source/a.rs\n\nsource/a.rs:\n"


def _texts() -> list[str]:
    """Return every shell lexing text in the order the native tests rebuild it.

    Returns
    -------
    list[str]
        Texts of lengths 0 to 3 over ``ALPHABET``, then 4 and 5 over ``CORE``.
    """
    texts: list[str] = []
    for alphabet, lengths in ((ALPHABET, range(4)), (CORE, range(4, 6))):
        for length in lengths:
            texts.extend("".join(word) for word in itertools.product(alphabet, repeat=length))
    return texts


def _split(text: str) -> list[str] | int:
    """Return ``shlex.split``'s words, or the index of its error text.

    Parameters
    ----------
    text
        Text to split.

    Returns
    -------
    list[str] | int
        Words in order, or an index into ``SHLEX_ERRORS``.
    """
    try:
        return shlex.split(text)
    except ValueError as error:
        return SHLEX_ERRORS.index(str(error))


def _rust_cases() -> dict[str, dict[str, Any]]:
    """Return named Rust record cases: records and the tree beside them.

    Returns
    -------
    dict[str, dict[str, Any]]
        Records (text or hexadecimal bytes) and tree by case name.
    """

    def case(*records: str | bytes, tree: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"records": list(records), "tree": RUST_TREE if tree is None else tree}

    quoted = "out.rmeta: 'source/b c.rs'\n'source/b c.rs':\n"
    linked = {**RUST_TREE, "source/l.rs": {"symlink": "a.rs"}, "outside.rs": "x\n"}
    escaping = {**RUST_TREE, "source/out.rs": {"symlink": "../outside.rs"}, "outside.rs": "x\n"}
    return {
        "one source": case(RUST_RECORD),
        "two records": case(RUST_RECORD, "lib.rlib: source/a.rs source/b\\ c.rs\n"),
        "no records": case(),
        "continuation": case("out.rmeta: source/a.rs \\\nsource/b\\ c.rs\nsource/a.rs:\n"),
        "carriage returns": case("out.rmeta: source/a.rs\r\n\r\nsource/a.rs:\r\n"),
        "lone carriage returns": case("out.rmeta: source/a.rs\r\rsource/a.rs:\r"),
        "unicode line break": case("out.rmeta: source/a.rs\u2028source/a.rs:\n"),
        "next line": case("out.rmeta: source/a.rs\x85source/a.rs:\n"),
        "vertical tab": case("out.rmeta: source/a.rs\x0bsource/a.rs:\n"),
        "form feed": case("out.rmeta: source/a.rs\x0csource/a.rs:\n"),
        "file separator": case("out.rmeta: source/a.rs\x1csource/a.rs:\n"),
        "group separator": case("out.rmeta: source/a.rs\x1dsource/a.rs:\n"),
        "record separator": case("out.rmeta: source/a.rs\x1esource/a.rs:\n"),
        "paragraph separator": case("out.rmeta: source/a.rs\u2029source/a.rs:\n"),
        "unicode blank line": case("out.rmeta: source/a.rs\n\u3000\nsource/a.rs:\n"),
        "comment": case(RUST_RECORD + "# env-dep:HOME=/root\n"),
        "indented comment": case(RUST_RECORD + "\u3000# x: y\n"),
        "missing colon": case("malformed record\n"),
        "empty target": case(": source/a.rs\n"),
        "blank target": case("\u3000: source/a.rs\n"),
        "two targets": case("first second: source/a.rs\n"),
        "quoted names": case(quoted),
        "doubled separators": case("out.rmeta: source//a.rs\n"),
        "empty quoted source": case("out.rmeta: ''\n"),
        "dollar names": case("out.rmeta: source/$$a.rs\n", tree={"source/$$a.rs": "x\n"}),
        "unclosed quote in target": case("'out.rmeta: source/a.rs\n"),
        "unclosed quote in sources": case("out.rmeta: 'source/a.rs\n"),
        "final escape": case("out.rmeta: source/a.rs \\"),
        "phony only": case("source/a.rs:\n"),
        "phony disagrees": case(RUST_RECORD + "source/other.rs:\n"),
        "absolute source": case("out.rmeta: /source/a.rs\n"),
        "escaping source": case(
            "out.rmeta: source/../outside.rs\n", tree={**RUST_TREE, "outside.rs": "x\n"}
        ),
        "linked source inside": case("out.rmeta: source/l.rs\n", tree=linked),
        "linked source outside": case("out.rmeta: source/out.rs\n", tree=escaping),
        "missing source": case("out.rmeta: source/missing.rs\n"),
        "dotted missing source": case("out.rmeta: source/./sub/../missing.rs\n"),
        "first failing source in sorted order": case(
            "out.rmeta: source/missing.rs source/../outside.rs\n",
            tree={**RUST_TREE, "outside.rs": "x\n"},
        ),
        "directory source": case(
            "out.rmeta: source/d\n", tree={**RUST_TREE, "source/d/x.rs": "x\n"}
        ),
        "missing record": {"records": [{"missing": True}], "tree": RUST_TREE},
        "record not utf-8": case(b"out.rmeta: source/a.rs\xff\n"),
        "byte order mark": case("\ufeffout.rmeta: source/a.rs\n"),
    }


def _materialise(directory: Path, case: dict[str, Any]) -> tuple[Path, ...]:
    """Write one case's tree and records and return the record paths.

    Parameters
    ----------
    directory
        Owned empty case directory.
    case
        Records and tree.

    Returns
    -------
    tuple[Path, ...]
        Record paths in order.
    """
    for name, content in case["tree"].items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, dict):
            path.symlink_to(content["symlink"])
        else:
            path.write_text(content, encoding="utf-8")
    (directory / "records").mkdir()
    paths = []
    for index, record in enumerate(case["records"]):
        path = directory / "records" / f"{index}.d"
        if isinstance(record, bytes):
            path.write_bytes(record)
        elif isinstance(record, str):
            path.write_bytes(record.encode("utf-8"))
        paths.append(path)
    return tuple(paths)


def _outcome(directory: Path, records: tuple[Path, ...]) -> dict[str, Any]:
    """Return the reader's digests, refusal or ``OSError`` text, with the root written ``<root>``.

    Parameters
    ----------
    directory
        Case directory.
    records
        Record paths.

    Returns
    -------
    dict[str, Any]
        ``{"hashes": ...}``, ``{"refusal": text}`` or ``{"os_error": text}``.
    """
    root = str(directory)
    try:
        hashes = rust_dependency_hashes(records, directory)
    except ValueError as error:
        return {"refusal": str(error).replace(root, "<root>")}
    except OSError as error:
        return {"os_error": str(error).replace(root, "<root>")}
    return {"hashes": dict(sorted(hashes.items()))}


def _written(case: dict[str, Any]) -> dict[str, Any]:
    """Return a case in its committed form, with byte records as hexadecimal text.

    Parameters
    ----------
    case
        Records and tree.

    Returns
    -------
    dict[str, Any]
        Records as ``{"text": ...}``, ``{"hex": ...}`` or ``{"missing": true}``, and the tree.
    """
    records = [
        {"hex": record.hex()}
        if isinstance(record, bytes)
        else record
        if isinstance(record, dict)
        else {"text": record}
        for record in case["records"]
    ]
    return {"records": records, "tree": case["tree"]}


def corpus(directory: Path) -> dict[str, Any]:
    """Build the complete corpus from Python's lexer and reader.

    Parameters
    ----------
    directory
        Owned empty directory for the case trees.

    Returns
    -------
    dict[str, Any]
        Lexing outcomes and reader cases.
    """
    directory = directory.resolve()
    cases: list[dict[str, Any]] = []
    for name, case in _rust_cases().items():
        path = directory / f"case-{len(cases)}"
        path.mkdir()
        records = _materialise(path, case)
        cases.append({"name": name, **_written(case), **_outcome(path, records)})
    return {
        "schema": "loop-timing-witness.amp-rust-dependency-cases.v1",
        "description": (
            "Python's posix shlex.split and Rust dependency record reader's outcomes. shlex holds "
            "the outcome of every text of lengths 0-3 over alphabet and 4-5 over core, in "
            "itertools.product order: the words, or an index into errors. Each case writes its "
            "tree (text files, or symlinks) and its records (text, hexadecimal bytes, or missing) "
            "under a new directory, runs rust_dependency_hashes, and gives hashes by name, a "
            "refusal, or an os_error text; the case directory is written <root>."
        ),
        "shlex": {
            "alphabet": list(ALPHABET),
            "core": list(CORE),
            "errors": list(SHLEX_ERRORS),
            "outcomes": [_split(text) for text in _texts()],
        },
        "cases": cases,
    }


def _text(document: dict[str, Any]) -> str:
    """Return the committed text form of the corpus.

    Parameters
    ----------
    document
        Corpus.

    Returns
    -------
    str
        Compact sorted JSON and a final newline.
    """
    return json.dumps(document, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"


def test_committed_corpus_equals_python_outcomes(tmp_path: Path) -> None:
    """Rebuild the corpus from Python's lexer and reader and require the committed file.

    Parameters
    ----------
    tmp_path
        Owned directory for the case trees.
    """
    assert CORPUS.read_text(encoding="utf-8") == _text(corpus(tmp_path))
    assert CORPUS.with_name(CORPUS.name + ".license").is_file()
