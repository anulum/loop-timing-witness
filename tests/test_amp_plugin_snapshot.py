# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original ISA logger completion and corruption regression tests

"""Preserve real native source/header closure and refuse captured original contradictions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from amp_plugin_receipt import admit_plugin
from amp_plugin_snapshot import snapshot_plugin, validate_plugin_snapshot
from test_amp_plugin_receipt import admitted_build, original_plugin, owned_plugin

__all__ = ["admitted_build", "original_plugin", "owned_plugin"]


def test_original_snapshot_roundtrip(admitted_build: Path) -> None:
    """Verify copied source/header bytes using the original receipt and actual library identity.

    Parameters
    ----------
    admitted_build
        Complete real actual private build.
    """
    content, data = admit_plugin(admitted_build)
    output = admitted_build.parent / "capture"
    output.mkdir()
    snapshot_plugin(output, content)
    validate_plugin_snapshot(output, data["plugin_sha256"], thermal=False)
    assert (output / "plugin_build.json").read_bytes() == content
    index = json.loads((output / "plugin_source_index.json").read_bytes())
    assert set(index) == set(data["dependencies"])


@pytest.mark.parametrize("fault", ["copy", "library", "thermal", "index", "source", "escape"])
def test_actual_snapshot_refusal(admitted_build: Path, fault: str) -> None:
    """Refuse original copy drift, false actual model, revised index and captured source escape.

    Parameters
    ----------
    admitted_build
        Complete actual private build.
    fault
        Specific contradiction in original or captured source closure.
    """
    content, data = admit_plugin(admitted_build)
    output = admitted_build.parent / "capture"
    output.mkdir()
    if fault == "copy":
        source = next(
            Path(name)
            for name in data["dependencies"]
            if Path(name).is_relative_to(admitted_build.parent)
        )
        with source.open("ab") as stream:
            stream.write(b"changed before snapshot")
        with pytest.raises(ValueError, match="while snapshotting"):
            snapshot_plugin(output, content)
        return
    snapshot_plugin(output, content)
    digest, thermal = data["plugin_sha256"], False
    index_file = output / "plugin_source_index.json"
    index = json.loads(index_file.read_bytes())
    if fault == "library":
        digest = "0" * 64
        finding = "snapshot library"
    elif fault == "thermal":
        thermal = True
        finding = "snapshot library"
    elif fault == "index":
        index.pop(next(iter(index)))
        index_file.write_text(json.dumps(index), encoding="ascii")
        finding = "source index disagrees"
    else:
        item = next(iter(index.values()))
        source = output / item["path"]
        if fault == "source":
            with source.open("ab") as stream:
                stream.write(b"changed captured original")
        else:
            source.unlink()
            source.symlink_to(admitted_build)
        finding = "bytes or paths changed"
    with pytest.raises(ValueError, match=finding):
        validate_plugin_snapshot(output, digest, thermal=thermal)
