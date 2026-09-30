# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — original runtime library snapshot and actual firmware admission

"""Exercise actual compiler runtime snapshots and refuse original-byte custody violations."""

from __future__ import annotations

import json
import shutil
from typing import TYPE_CHECKING

import pytest
from amp_build_toolchain import compiler_identity
from amp_runtime_snapshot import snapshot_runtime
from test_amp_image_flow import REQUEST, prepared_image
from test_device_tree_resources import compile_tree
from verify_amp_image import verify_image

from manifest_io import sha256_of_file

__all__ = ["compile_tree", "prepared_image"]

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize("fault", ["index", "library", "escape"])
def test_public_image_runtime_refusal(prepared_image: Path, fault: str) -> None:
    """Refuse altered compiler library custody through actual compiled firmware verification.

    Parameters
    ----------
    prepared_image
        Original real public preparation and compiled RV64 firmware.
    fault
        Original runtime index, library bytes or a captured path escaping the image.
    """
    index_path = prepared_image / "runtime_source_index.json"
    index = json.loads(index_path.read_bytes())
    name, item = next(iter(index.items()))
    library = prepared_image / item["path"]
    if fault == "index":
        index.pop(name)
        index_path.write_text(json.dumps(index), encoding="ascii")
        finding = "index disagrees"
    elif fault == "library":
        with library.open("ab") as stream:
            stream.write(b"changed actual compiler library snapshot")
        finding = "library bytes or paths changed"
    else:
        library.unlink()
        library.symlink_to(name)
        finding = "library bytes or paths changed"
    with pytest.raises(ValueError, match=finding):
        verify_image(
            prepared_image,
            prepared_image / "platform.dtb",
            prepared_image / "configuration.txt",
            REQUEST,
        )


@pytest.mark.parametrize("fault", ["identity", "before-copy"])
def test_original_actual_library_copy_refused(tmp_path: Path, fault: str) -> None:
    """Refuse malformed original maps or library byte drift through the actual snapshot API.

    Parameters
    ----------
    tmp_path
        Exclusive owned original library and capture output.
    fault
        Invalid original digest or changed original library after its hash was admitted.
    """
    original = next(iter(compiler_identity("gcc", "cc1")["runtime_libraries"]))
    library = tmp_path / "actual-original-library"
    shutil.copyfile(original, library)
    identities = {str(library): sha256_of_file(library)}
    if fault == "identity":
        identities[str(library)] = "invalid-original-hash"
        finding = "identities are invalid"
    else:
        with library.open("ab") as stream:
            stream.write(b"changed original actual library before copying")
        finding = "changed during snapshot"
    output = tmp_path / "capture"
    output.mkdir()
    with pytest.raises(ValueError, match=finding):
        snapshot_runtime(output, identities)
    assert not (output / "runtime_source_index.json").exists()
