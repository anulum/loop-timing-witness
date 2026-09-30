# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — admitted real firmware input custody and mutation refusal

"""Exercise source snapshot custody after admission of an actual compiled RV64 image."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from amp_capture_snapshot import snapshot_image, verify_snapshot
from test_amp_spike_command import REQUEST
from test_capture_amp_simulation import capture_arguments
from verify_amp_image import verify_image

from manifest_io import sha256_of_file

__all__ = ["capture_arguments"]


@pytest.mark.parametrize("fault", ["none", "before-copy", "after-copy", "absolute", "escape"])
def test_admitted_image_custody(capture_arguments: list[str], fault: str) -> None:
    """Refuse real original source drift and changed snapshot bytes across the admission boundary.

    Parameters
    ----------
    capture_arguments
        Real prepared source-bound RV64 firmware copy.
    fault
        Exact original mutation or invalid snapshot path.
    """
    image = Path(capture_arguments[capture_arguments.index("--image") + 1])
    manifest = verify_image(image, image / "platform.dtb", image / "configuration.txt", REQUEST)
    admitted = json.loads(manifest.read_bytes())
    hashes = {name: digest for name, digest in admitted["inputs"].items() if name != "compiler"}
    hashes["firmware.elf"] = admitted["firmware_sha256"]
    output = image.parent / "snapshot"
    if fault in {"absolute", "escape"}:
        hashes[str(image / "firmware.elf") if fault == "absolute" else "../firmware.elf"] = hashes[
            "firmware.elf"
        ]
        with pytest.raises(ValueError, match="relative input paths"):
            snapshot_image(image, output, hashes)
        assert not output.exists()
        return
    if fault == "before-copy":
        with (image / "source/runtime/bare_metal/amp_controller.c").open("ab") as stream:
            stream.write(b"\nchanged after admission\n")
        with pytest.raises(ValueError, match="changed during capture snapshot"):
            snapshot_image(image, output, hashes)
        return
    snapshot_image(image, output, hashes)
    if fault == "after-copy":
        with (output / "firmware.elf").open("ab") as stream:
            stream.write(b"changed after startup")
        with pytest.raises(ValueError, match="changed during execution"):
            verify_snapshot(output, hashes)
    else:
        verify_snapshot(output, hashes)
        assert sha256_of_file(output / "firmware.elf") == admitted["firmware_sha256"]
