# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — firmware reader outcomes on stacked random edits

"""Hold the firmware ELF and device-tree readers' outcomes on stacked random edits in a corpus.

The ELF and device-tree corpora change one field or one byte at a time. This corpus stacks
random overwrites on the same real inputs, as a careless or hostile producer could: each case
overwrites one to eight runs of one to eight bytes at random offsets of a base, and one case in
eight then cuts the result at a random length. The bases are the two real images of
``amp-elf-cases.json`` and the three compiled trees of ``device-tree-cases.json``; each base has
its own SplitMix64 sequence (Steele, Lea and Flood, 2014), seeded with ``SEED`` plus its position,
so the native analysis rebuilds every input in its unit tests and requires the same outcomes.

For an image the corpus records what ``admit_elf`` returns for the firmware reservation and what
``read_symbols`` returns (as a digest), or the text each refuses with. For a tree it records the
decoded tree's digest and how its readers' outcomes differ from the unchanged tree's, or the text
``decode_device_tree`` refuses with. A reader that raises anything but its refusal fails the test.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from test_amp_elf_corpus import RAM, _admission, _symbols
from test_device_tree_corpus import _changes, _indexed, _outcome, _readers, _refusals

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
DATA: Final = REPOSITORY_ROOT / "analysis/rust/tests/data"
CORPUS: Final = DATA / "firmware-reader-mutations.json"
SEED: Final = 20261121
CASES: Final = 200
MASK: Final = (1 << 64) - 1
BASES: Final = (
    ("elf", "linked"),
    ("elf", "firmware"),
    ("device tree", "spike platform"),
    ("device tree", "reservations"),
    ("device tree", "translation"),
)
DESCRIPTION: Final = (
    "Firmware ELF and device-tree reader outcomes on stacked random edits of real inputs. Each "
    "base (an image of amp-elf-cases.json or a tree chunk of device-tree-cases.json) has its own "
    "SplitMix64 sequence seeded with seed + its position in bases. A case draws n = 1 + r % 8; "
    "n times it draws an offset o = r % length and a width w = 1 + r % 8, then overwrites each "
    "byte from o to min(length, o + w) - 1 with r % 256, in order; it then draws r and, when "
    "r % 8 == 0, cuts the input to r' % length bytes. Each r is the next draw. An ELF outcome is "
    "[admit_elf for the reservation, read_symbols as a digest]; a tree outcome is the decode "
    "refusal, or the tree digest with the readers' changes from the unchanged tree. Refusals are "
    "indices into texts."
)


class SplitMix64:
    """The SplitMix64 generator of Steele, Lea and Flood (2014)."""

    def __init__(self, seed: int) -> None:
        """Start the sequence at a seed.

        Parameters
        ----------
        seed
            Initial 64-bit state.
        """
        self.state = seed & MASK

    def draw(self) -> int:
        """Return the next 64-bit output.

        Returns
        -------
        int
            Next output of the sequence.
        """
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK
        mixed = self.state
        mixed = ((mixed ^ (mixed >> 30)) * 0xBF58476D1CE4E5B9) & MASK
        mixed = ((mixed ^ (mixed >> 27)) * 0x94D049BB133111EB) & MASK
        return mixed ^ (mixed >> 31)


def stacked_edits(base: bytes, random: SplitMix64) -> bytes:
    """Return one stacked random edit of a base, as the corpus description defines it.

    Parameters
    ----------
    base
        Nonempty input to change.
    random
        The base's sequence, advanced by every draw.

    Returns
    -------
    bytes
        Changed, possibly cut, input.
    """
    data = bytearray(base)
    for _ in range(1 + random.draw() % 8):
        offset = random.draw() % len(data)
        end = min(len(data), offset + 1 + random.draw() % 8)
        for position in range(offset, end):
            data[position] = random.draw() % 256
    if random.draw() % 8 == 0:
        del data[random.draw() % len(data) :]
    return bytes(data)


def _bases() -> list[bytes]:
    """Return the real images and compiled trees of the committed corpora in ``BASES`` order.

    Returns
    -------
    list[bytes]
        Base inputs.
    """
    images = json.loads((DATA / "amp-elf-cases.json").read_text(encoding="utf-8"))["images"]
    chunks = json.loads((DATA / "device-tree-cases.json").read_text(encoding="utf-8"))["chunks"]
    return [
        bytes.fromhex(images[name]["hex"] if reader == "elf" else chunks[name])
        for reader, name in BASES
    ]


def _tree_outcome(blob: bytes, reference: dict[str, Any]) -> dict[str, Any]:
    """Return a changed tree's decode refusal, or its digest and reader changes.

    Parameters
    ----------
    blob
        Changed tree.
    reference
        Reader outcomes of the unchanged tree.

    Returns
    -------
    dict[str, Any]
        ``{"refusal": text}`` or ``{"tree_sha256": hex, "readers": changes}``.
    """
    outcome, tree = _outcome(blob, full_tree=False)
    if tree is None:
        return outcome
    return {**outcome, "readers": _changes(reference, _readers(tree))}


def corpus() -> dict[str, Any]:
    """Build the complete corpus from the committed bases and Python's readers.

    Returns
    -------
    dict[str, Any]
        Text table and the outcomes of every base's cases.
    """
    bases = []
    for position, ((reader, name), base) in enumerate(zip(BASES, _bases(), strict=True)):
        random = SplitMix64(SEED + position)
        reference: dict[str, Any] = {}
        if reader == "device tree":
            tree = _outcome(base, full_tree=False)[1]
            assert tree is not None, name
            reference = _readers(tree)
        outcomes: list[Any] = []
        for _ in range(CASES):
            changed = stacked_edits(base, random)
            if reader == "elf":
                outcomes.append([_admission(changed, RAM), _symbols(changed, whole=False)])
            else:
                outcomes.append(_tree_outcome(changed, reference))
        bases.append({"reader": reader, "name": name, "outcomes": outcomes})
    texts = sorted(_refusals(bases))
    index = {text: number for number, text in enumerate(texts)}
    return {
        "schema": "loop-timing-witness.firmware-reader-mutations.v1",
        "description": DESCRIPTION,
        "seed": SEED,
        "cases": CASES,
        "reservation": [RAM.address, RAM.size],
        "texts": texts,
        "bases": _indexed(bases, index),
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


def test_committed_corpus_equals_python_outcomes() -> None:
    """Rebuild the corpus from the committed bases and the Python readers; require the file."""
    assert CORPUS.read_text(encoding="utf-8") == _text(corpus())
    assert CORPUS.with_name(CORPUS.name + ".license").is_file()


def test_the_edits_reach_admitted_and_decoded_inputs_and_refusals() -> None:
    """The cases are not all refused at the first check: each reader also admits or decodes some.

    A corpus whose every case failed the first header check would compare little beyond it.
    """
    document = corpus()
    for base in document["bases"]:
        outcomes = base["outcomes"]
        if base["reader"] == "elf":
            admitted = [item for item in outcomes if "segments" in item[0]]
            refused = [item for item in outcomes if "refusal" in item[0]]
        else:
            admitted = [item for item in outcomes if "tree_sha256" in item]
            refused = [item for item in outcomes if "refusal" in item]
        assert admitted, base["name"]
        assert refused, base["name"]
        assert len({json.dumps(item, sort_keys=True) for item in refused}) > 1, base["name"]
