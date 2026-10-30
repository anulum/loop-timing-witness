# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — test operator descriptors for package copies

"""Give a package copy operator descriptors that its own registry has reviewed.

The real descriptors name host files and are never packaged. A test writes
descriptors with the reviewed portable identities and absent host paths, and
pins their digests in an isolated package copy, as an operator review would.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from loop_timing_witness.manifest_io import canonical_json_bytes
from loop_timing_witness.neural_checker_image import IMAGE_EXECUTOR_SCHEMA
from loop_timing_witness.neural_run_selected_profile import (
    IMAGE_BINDING_SHA256,
    IMAGE_BINDING_VARIABLE,
    INSTALLATION_SHA256,
    INSTALLATION_VARIABLE,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def installation_descriptor(package: Path) -> bytes:
    """Return a descriptor with the reviewed runtime identities and absent host paths.

    Parameters
    ----------
    package
        Package directory holding the reviewed runtime contract.

    Returns
    -------
    bytes
        Canonical installation descriptor.
    """
    runtime = json.loads((package / "data/neural-selected-checker-runtime.json").read_bytes())
    bindings = [
        {**item, "name": item["path"], "actual_path": f"/absent/runtime/{index}"}
        for index, item in enumerate(runtime["files"])
    ]
    for item in bindings:
        del item["path"]
    roots = [f"/absent/imports/{index}" for index in range(len(runtime["import_namespaces"]))]
    return canonical_json_bytes({"bindings": bindings, "import_roots": roots})


def image_binding() -> bytes:
    """Return a closed executor binding naming only absent host files.

    Returns
    -------
    bytes
        Canonical executor binding.
    """
    return canonical_json_bytes(
        {
            "schema_id": IMAGE_EXECUTOR_SCHEMA,
            "supplier": {},
            "historical_contracts": {},
            "command": ["/absent/launcher", "{image_root}", "{work_directory}", "{operation}"],
            "bootstrap_environment": {},
            "deadline_seconds": 45,
            "host_boundary": {
                "system": "Linux",
                "machine": "x86_64",
                "kernel_release": "absent",
                "uid": 0,
                "gid": 0,
                "files": [],
                "absent_paths": [],
            },
            "image": {"files": [], "directories": [], "symlinks": []},
            "source_files": ["absent.py"],
            "worker_files": ["absent-worker.py"],
        }
    )


def adopt_operator_descriptors(
    package: Path, directory: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    """Write both descriptors, pin them in the package copy and select them.

    Parameters
    ----------
    package
        Isolated package copy whose registry adopts the descriptors.
    directory
        Owned directory for the descriptor files.
    monkeypatch
        Sets both operator variables for the command.

    Returns
    -------
    tuple[Path, Path]
        Installation descriptor and image binding paths.
    """
    installation = directory / "installation-descriptor.json"
    binding = directory / "image-binding.json"
    installation.write_bytes(installation_descriptor(package))
    binding.write_bytes(image_binding())
    selector = package / "neural_run_selected_profile.py"
    text = selector.read_text(encoding="utf-8")
    for old, raw in ((INSTALLATION_SHA256, installation), (IMAGE_BINDING_SHA256, binding)):
        assert text.count(old) == 1
        text = text.replace(old, hashlib.sha256(raw.read_bytes()).hexdigest())
    selector.write_text(text, encoding="utf-8")
    monkeypatch.setenv(INSTALLATION_VARIABLE, str(installation))
    monkeypatch.setenv(IMAGE_BINDING_VARIABLE, str(binding))
    return installation, binding
