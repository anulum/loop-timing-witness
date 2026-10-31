# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete no-follow neural file acquisition

"""Exercise complete original artifact binding through the real public file API."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError
from loop_timing_witness.neural_run_files import (
    read_neural_manifest_root,
    read_neural_run_file,
    read_run_dispatch_bytes,
)

_ROOT = Path(__file__).resolve().parents[1]
_ORIGINAL_SHA = "c5397e9146741b23a9e85f686d0e47b5bbc1dafb8e0f1c70df92c999e6c13315"


def _original(path: Path) -> tuple[bytes, dict[str, object]]:
    """Copy one complete actual original acquisition artifact without interpreting it.

    Parameters
    ----------
    path
        Owned normal file under the actual filesystem test root.

    Returns
    -------
    tuple[bytes, dict[str, object]]
        Complete original bytes and their exact within-root file reference.
    """
    raw = (_ROOT / "tests/data/neural-native-original.run.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == _ORIGINAL_SHA
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw, {"path": "data/run.json", "sha256": _ORIGINAL_SHA, "byte_length": len(raw)}


def test_complete_original_bytes_and_real_empty_file_bind(tmp_path: Path) -> None:
    """Read the complete retained acquisition bytes and distinguish a real empty file.

    Parameters
    ----------
    tmp_path
        Actual artifact-copy and zero-byte regular-file allocation.
    """
    raw, reference = _original(tmp_path / "data/run.json")
    assert read_neural_run_file(tmp_path, reference, len(raw)) == raw
    (tmp_path / "empty.txt").write_bytes(b"")
    empty = {"path": "empty.txt", "sha256": hashlib.sha256(b"").hexdigest(), "byte_length": 0}
    assert read_neural_run_file(tmp_path, empty, 0) == b""
    assert read_neural_run_file(tmp_path, empty, 0, expected_bytes=b"") == b""
    (tmp_path / "empty.txt").unlink()
    with pytest.raises(NeuralCaptureRefusalError):
        read_neural_run_file(tmp_path, empty, 0)


def test_consumer_expected_bytes_are_checked_before_the_digest(tmp_path: Path) -> None:
    """Bind the original body and diagnose a same-length replacement independently.

    Parameters
    ----------
    tmp_path
        Owned complete original acquisition file.
    """
    raw, reference = _original(tmp_path / "data/run.json")
    assert read_neural_run_file(tmp_path, reference, len(raw), expected_bytes=raw) == raw
    changed = bytearray(raw)
    changed[0] ^= 1
    (tmp_path / "data/run.json").write_bytes(changed)
    with pytest.raises(NeuralCaptureRefusalError, match="Selected original body changed"):
        read_neural_run_file(
            tmp_path,
            reference,
            len(raw),
            expected_bytes=raw,
            mismatch_message="Selected original body changed.",
        )


@pytest.mark.parametrize("field", ["sha256", "byte_length"])
def test_expected_body_does_not_waive_the_declared_reference(tmp_path: Path, field: str) -> None:
    """Retain exact digest and length checks after matching consumer-owned bytes.

    Parameters
    ----------
    tmp_path
        Owned original artifact.
    field
        Declared digest or byte count contradicted by the intact actual body.
    """
    raw, reference = _original(tmp_path / "data/run.json")
    reference[field] = "0" * 64 if field == "sha256" else len(raw) + 1
    with pytest.raises(NeuralCaptureRefusalError, match="Original whole length/SHA-256 differs"):
        read_neural_run_file(tmp_path, reference, len(raw) + 1, expected_bytes=raw)


@pytest.mark.parametrize("parent", [False, True])
def test_internal_symlink_is_refused_at_each_component(tmp_path: Path, *, parent: bool) -> None:
    """Refuse an actual within-root symlink even when the target has the expected bytes.

    Parameters
    ----------
    tmp_path
        Original regular data and a real symlink within the same acquisition root.
    parent
        Link the parent directory or the final original artifact itself.
    """
    raw, reference = _original(tmp_path / "data/run.json")
    if parent:
        (tmp_path / "alias").symlink_to("data", target_is_directory=True)
        reference["path"] = "alias/run.json"
    else:
        (tmp_path / "alias.json").symlink_to("data/run.json")
        reference["path"] = "alias.json"
    step = "parent" if parent else "file"
    with pytest.raises(NeuralCaptureRefusalError) as refused:
        read_neural_run_file(tmp_path, reference, len(raw))
    assert str(refused.value) == (
        f"Cannot open original {step} without symlinks: {reference['path']}."
    )
    assert (tmp_path / "data/run.json").read_bytes() == raw


@pytest.mark.parametrize("kind", ["fifo", "directory", "absent"])
def test_nonregular_originals_are_refused_without_a_writer(tmp_path: Path, kind: str) -> None:
    """Refuse actual unsupported file kinds before an empty digest could replace data.

    Parameters
    ----------
    tmp_path
        Real filesystem object allocation.
    kind
        Actual FIFO, directory or absent input.
    """
    path = tmp_path / "original"
    if kind == "fifo":
        os.mkfifo(path)
    elif kind == "directory":
        path.mkdir()
    reference = {"path": "original", "sha256": hashlib.sha256(b"").hexdigest(), "byte_length": 0}
    with pytest.raises(NeuralCaptureRefusalError):
        read_neural_run_file(tmp_path, reference, 0)


@pytest.mark.parametrize("kind", ["digest", "short", "long", "allocation"])
def test_complete_original_identity_and_allocation_are_required(tmp_path: Path, kind: str) -> None:
    """Refuse actual complete byte or role-allocation contradictions.

    Parameters
    ----------
    tmp_path
        Whole unchanged original artifact bytes.
    kind
        Deliberately contradictory digest, length or caller allocation.
    """
    raw, reference = _original(tmp_path / "data/run.json")
    limit = len(raw) + 1
    if kind == "digest":
        reference["sha256"] = "0" * 64
    elif kind == "short":
        reference["byte_length"] = len(raw) - 1
    elif kind == "long":
        reference["byte_length"] = len(raw) + 1
    else:
        limit = len(raw) - 1
    with pytest.raises(NeuralCaptureRefusalError):
        read_neural_run_file(tmp_path, reference, limit)
    assert (tmp_path / "data/run.json").read_bytes() == raw


@pytest.mark.parametrize("path", ["data//run.json", "data/./run.json", "../run.json", "", "dátá"])
def test_reference_names_require_complete_portable_components(tmp_path: Path, path: str) -> None:
    """Refuse noncanonical references even when normalisation could select original bytes.

    Parameters
    ----------
    tmp_path
        Actual original artifact root.
    path
        Noncanonical or nonportable reference name.
    """
    raw, reference = _original(tmp_path / "data/run.json")
    reference["path"] = path
    with pytest.raises(NeuralCaptureRefusalError, match="Invalid within-run original path"):
        read_neural_run_file(tmp_path, reference, len(raw))


@pytest.mark.parametrize("kind", ["bool", "float", "upper", "newline", "extra", "path"])
def test_reference_fields_remain_exact_and_closed(tmp_path: Path, kind: str) -> None:
    """Refuse coerced scalar fields or unknown members through the actual reader.

    Parameters
    ----------
    tmp_path
        Actual complete original file.
    kind
        Invalid exact scalar or additional member.
    """
    raw, reference = _original(tmp_path / "data/run.json")
    if kind == "bool":
        reference["byte_length"] = True
    elif kind == "float":
        reference["byte_length"] = float(len(raw))
    elif kind == "upper":
        reference["sha256"] = _ORIGINAL_SHA.upper()
    elif kind == "newline":
        reference["sha256"] = _ORIGINAL_SHA + "\n"
    elif kind == "path":
        reference["path"] = 1
    else:
        reference["extra"] = 0
    # A reference without a text path cannot be named in the refusal.
    named = "" if kind == "path" else ": data/run.json"
    with pytest.raises(NeuralCaptureRefusalError) as refused:
        read_neural_run_file(tmp_path, reference, len(raw))
    assert str(refused.value) == f"Invalid original file reference{named}."


def test_root_readers_preserve_original_bytes_with_host_filename(tmp_path: Path) -> None:
    """Acquire the unchanged original under a caller-selected nonportable root basename.

    Parameters
    ----------
    tmp_path
        Owned root manifest containing spaces and Unicode in its host filename.
    """
    raw, _ = _original(tmp_path / "data/run.json")
    root = tmp_path / "original capture Šotek.json"
    root.write_bytes(raw)
    assert read_neural_manifest_root(root) == raw
    assert read_run_dispatch_bytes(root) == raw


@pytest.mark.parametrize("dispatch", [False, True])
def test_root_allocations_refuse_complete_excess_bytes(tmp_path: Path, *, dispatch: bool) -> None:
    """Reject actual oversized root files instead of accepting a truncated JSON prefix.

    Parameters
    ----------
    tmp_path
        Original private manifest with excessive trailing JSON whitespace.
    dispatch
        Exercise the finite global dispatch or narrower neural root allocation.
    """
    raw, _ = _original(tmp_path / "data/run.json")
    limit = 16 * 1048576 if dispatch else 65536
    root = tmp_path / "oversized.json"
    root.write_bytes(raw + b" " * (limit + 1 - len(raw)))
    reader = read_run_dispatch_bytes if dispatch else read_neural_manifest_root
    with pytest.raises(NeuralCaptureRefusalError):
        reader(root)
    assert root.stat().st_size == limit + 1


@pytest.mark.parametrize("dispatch", [False, True])
def test_root_path_failures_use_authored_refusals(tmp_path: Path, *, dispatch: bool) -> None:
    """Refuse actual NUL and absent parent paths without leaking filesystem diagnostics.

    Parameters
    ----------
    tmp_path
        Existing parent for caller-selected invalid or missing root paths.
    dispatch
        Real dispatch or neural root acquisition entry point.
    """
    reader = read_run_dispatch_bytes if dispatch else read_neural_manifest_root
    refusal = r"^Cannot acquire" if dispatch else r"^Cannot read neural manifest as a regular"
    for root in (tmp_path / "invalid\x00.json", tmp_path / "absent/run.json"):
        with pytest.raises(NeuralCaptureRefusalError, match=refusal):
            reader(root)
