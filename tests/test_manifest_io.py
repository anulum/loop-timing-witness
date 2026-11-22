# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — input reading, file digests and atomic output

"""Contract tests for input reading, JSON loading from files, file digests and atomic writes."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from loop_timing_witness.manifest_io import (
    load_bounded_json_object,
    load_json_object,
    open_input,
    read_input_bytes,
    sha256_of_file,
    write_bytes_atomic,
)
from loop_timing_witness.strict_json import JsonInputRefusalError, canonical_json_bytes


def test_load_returns_the_decoded_object(tmp_path: Path) -> None:
    """A well-formed object round-trips with nested values intact."""
    path = tmp_path / "manifest.json"
    path.write_text('{"alpha": 1, "beta": [true, null], "gamma": {"delta": "ε"}}', encoding="utf-8")
    assert load_json_object(path) == {"alpha": 1, "beta": [True, None], "gamma": {"delta": "ε"}}


def test_load_rejects_a_repeated_nested_key(tmp_path: Path) -> None:
    """Duplicate detection applies inside nested objects too, and names the file."""
    path = tmp_path / "nested.json"
    path.write_text('{"outer": {"inner": 1, "inner": 2}}', encoding="utf-8")
    with pytest.raises(ValueError, match=r"nested\.json: duplicate JSON key: inner"):
        load_json_object(path)


def test_load_rejects_invalid_json(tmp_path: Path) -> None:
    """A syntax error surfaces as ValueError with the file name."""
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(JsonInputRefusalError) as refusal:
        load_json_object(path)
    assert str(refusal.value) == f"{path}: invalid JSON"


def test_load_of_a_missing_file_raises_oserror(tmp_path: Path) -> None:
    """A missing file is an OSError, never an empty object."""
    with pytest.raises(FileNotFoundError):
        load_json_object(tmp_path / "absent.json")


def test_bounded_load_decodes_an_object(tmp_path: Path) -> None:
    """A file within the bounded rules decodes to its object."""
    path = tmp_path / "receipt.json"
    path.write_text('{"alpha": [1, {"beta": "ε"}]}', encoding="utf-8")
    assert load_bounded_json_object(path) == {"alpha": [1, {"beta": "ε"}]}


@pytest.mark.parametrize(
    ("text", "refusal"),
    [
        ('{"a": 18446744073709551616}', "integer outside the 64-bit range: 18446744073709551616"),
        ('{"a": "\\ud800"}', "JSON text holds an unpaired surrogate escape"),
        ('{"a": ' + "[" * 64 + "]" * 64 + "}", "JSON input exceeds decoder limits"),
    ],
    ids=["wide integer", "unpaired surrogate", "nesting 65"],
)
def test_bounded_load_refuses_with_the_path_as_given(
    tmp_path: Path, text: str, refusal: str
) -> None:
    """A file outside the bounded rules is refused with its path as the label.

    Parameters
    ----------
    tmp_path
        Owned directory for the file.
    text
        File content.
    refusal
        Decoder refusal after the path.
    """
    path = tmp_path / "receipt.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(JsonInputRefusalError) as refused:
        load_bounded_json_object(path)
    assert str(refused.value) == f"{path}: {refusal}"


def test_bounded_load_of_a_missing_file_raises_oserror(tmp_path: Path) -> None:
    """A missing file is an OSError, never an empty object."""
    with pytest.raises(FileNotFoundError):
        load_bounded_json_object(tmp_path / "absent.json")


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


def test_run_inputs_are_read_without_blocking_on_a_fifo(tmp_path: Path) -> None:
    """Read a regular file and a device; refuse a FIFO at once and a directory as ``open`` does.

    Parameters
    ----------
    tmp_path
        Owned directory for the regular file, the FIFO and the directory.
    """
    regular = tmp_path / "regular.bin"
    regular.write_bytes(b"bytes")
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    directory = tmp_path / "directory"
    directory.mkdir()
    assert read_input_bytes(regular) == b"bytes"
    assert read_input_bytes(Path("/dev/null")) == b""
    with pytest.raises(OSError, match=r"^\[Errno 22\] Invalid argument: ") as refused:
        read_input_bytes(fifo)
    assert str(refused.value) == f"[Errno 22] Invalid argument: {str(fifo)!r}"
    with pytest.raises(IsADirectoryError) as directory_refused:
        read_input_bytes(directory)
    assert str(directory_refused.value) == f"[Errno 21] Is a directory: {str(directory)!r}"
    with open_input(regular) as stream:
        assert stream.read() == b"bytes"
