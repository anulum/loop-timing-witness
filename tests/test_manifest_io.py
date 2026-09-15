# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — tests of the JSON input and atomic output primitives

"""Contract tests for strict JSON reading, canonical serialisation and atomic writes."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

import pytest

from manifest_io import canonical_json_bytes, load_json_object, sha256_of_file, write_bytes_atomic

if TYPE_CHECKING:
    from pathlib import Path


def test_load_returns_the_decoded_object(tmp_path: Path) -> None:
    """A well-formed object round-trips with nested values intact."""
    path = tmp_path / "manifest.json"
    path.write_text('{"alpha": 1, "beta": [true, null], "gamma": {"delta": "ε"}}', encoding="utf-8")
    assert load_json_object(path) == {"alpha": 1, "beta": [True, None], "gamma": {"delta": "ε"}}


def test_load_rejects_a_repeated_top_level_key(tmp_path: Path) -> None:
    """A repeated member name fails instead of silently keeping the last value."""
    path = tmp_path / "manifest.json"
    path.write_text('{"alpha": 1, "alpha": 2}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key: alpha"):
        load_json_object(path)


def test_load_rejects_a_repeated_nested_key(tmp_path: Path) -> None:
    """Duplicate detection applies inside nested objects too, and names the file."""
    path = tmp_path / "nested.json"
    path.write_text('{"outer": {"inner": 1, "inner": 2}}', encoding="utf-8")
    with pytest.raises(ValueError, match=r"nested\.json: duplicate JSON key: inner"):
        load_json_object(path)


def test_load_rejects_a_non_object_top_level(tmp_path: Path) -> None:
    """A valid JSON array is still refused as a manifest."""
    path = tmp_path / "manifest.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ValueError, match="top-level JSON value must be an object"):
        load_json_object(path)


def test_load_rejects_invalid_json(tmp_path: Path) -> None:
    """A syntax error surfaces as ValueError with the file name."""
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match=r"broken\.json: invalid JSON"):
        load_json_object(path)


def test_load_rejects_bytes_that_are_not_utf8(tmp_path: Path) -> None:
    """A Windows-1250 encoded file is refused rather than decoded wrongly."""
    path = tmp_path / "latin1.json"
    path.write_bytes('{"name": "Šotek"}'.encode("cp1250"))
    with pytest.raises(ValueError, match="not UTF-8"):
        load_json_object(path)


def test_load_of_a_missing_file_raises_oserror(tmp_path: Path) -> None:
    """A missing file is an OSError, never an empty object."""
    with pytest.raises(FileNotFoundError):
        load_json_object(tmp_path / "absent.json")


def test_canonical_bytes_are_independent_of_key_order() -> None:
    """Insertion order does not change the serialised bytes; keys are sorted."""
    first = canonical_json_bytes({"beta": 2, "alpha": {"z": 1, "a": 2}})
    second = canonical_json_bytes({"alpha": {"a": 2, "z": 1}, "beta": 2})
    assert first == second
    assert first == b'{\n  "alpha": {\n    "a": 2,\n    "z": 1\n  },\n  "beta": 2\n}\n'


def test_canonical_bytes_keep_non_ascii_text() -> None:
    """Non-ASCII text is written as UTF-8, not as escape sequences."""
    assert "Šotek".encode() in canonical_json_bytes({"name": "Šotek"})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_canonical_bytes_refuse_non_finite_numbers(value: float) -> None:
    """Non-finite numbers cannot enter a drift-checked artefact."""
    with pytest.raises(ValueError, match="Out of range float values"):
        canonical_json_bytes({"value": value})


def test_sha256_matches_a_direct_digest(tmp_path: Path) -> None:
    """The file digest equals hashlib over the same bytes."""
    path = tmp_path / "payload.bin"
    path.write_bytes(b"\x00timebase\xff")
    assert sha256_of_file(path) == hashlib.sha256(b"\x00timebase\xff").hexdigest()


def test_atomic_write_creates_and_replaces_a_file(tmp_path: Path) -> None:
    """A write creates the file, a second write replaces it, and no temporary file remains."""
    path = tmp_path / "inventory.json"
    write_bytes_atomic(path, canonical_json_bytes({"first": 1}))
    assert json.loads(path.read_text(encoding="utf-8")) == {"first": 1}
    write_bytes_atomic(path, canonical_json_bytes({"second": 2}))
    assert json.loads(path.read_text(encoding="utf-8")) == {"second": 2}
    assert sorted(item.name for item in tmp_path.iterdir()) == ["inventory.json"]


def test_atomic_write_failure_keeps_the_directory_clean(tmp_path: Path) -> None:
    """When the final rename fails the temporary file is removed and the error propagates."""
    destination = tmp_path / "occupied"
    destination.mkdir()
    (destination / "keep.txt").write_text("existing", encoding="utf-8")
    with pytest.raises(OSError, match="occupied"):
        write_bytes_atomic(destination, b"new content")
    assert sorted(item.name for item in tmp_path.iterdir()) == ["occupied"]
    assert (destination / "keep.txt").read_text(encoding="utf-8") == "existing"


def test_atomic_write_into_a_missing_directory_raises(tmp_path: Path) -> None:
    """The parent directory must exist; nothing is created on failure."""
    with pytest.raises(FileNotFoundError):
        write_bytes_atomic(tmp_path / "absent" / "file.json", b"{}")
    assert list(tmp_path.iterdir()) == []
