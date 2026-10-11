# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual producer context and source drift controls

"""Exercise actual loaded source selection and immutable producer context through public APIs."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from native_source_snapshot import snapshot_native_sources
from producer_source_context import ProducerSourceContext, snapshot_producer_context
from test_native_run import configuration

from conftest import REPOSITORY_ROOT
from loop_timing_witness import manifest_io as actual_json


@pytest.fixture
def actual_context(tmp_path: Path) -> ProducerSourceContext:
    """Freeze the real project producer and its original native inputs.

    Parameters
    ----------
    tmp_path
        Exclusive source and context output.

    Returns
    -------
    ProducerSourceContext
        Actual loaded project identities and preserved repository sources.
    """
    native = snapshot_native_sources(REPOSITORY_ROOT, tmp_path, host_load=True)
    return snapshot_producer_context(REPOSITORY_ROOT, tmp_path, native)


def test_actual_package_implementation_and_environment_are_bound(
    actual_context: ProducerSourceContext,
) -> None:
    """Resolve real package code rather than treating its repository shim as implementation.

    Parameters
    ----------
    actual_context
        Context built from real loaded modules and native sources.
    """
    actual_context.verify()
    document = json.loads(actual_context.document.read_bytes())
    name = "source/parent_package/loop_timing_witness/manifest_io.py"
    reference = document["sources"][name]
    implementation = Path(actual_json.__file__)
    assert Path(reference["origin"]).resolve() == implementation.resolve()
    assert reference["sha256"] == hashlib.sha256(implementation.read_bytes()).hexdigest()
    assert (actual_context.document.parent / name).read_bytes() == implementation.read_bytes()
    assert "source/tools/manifest_io.py" in document["sources"]
    assert "source/parent_tools/producer_source_context.py" in document["sources"]
    assert document["python"]["implementation"] == "cpython"
    assert Path(document["python"]["executable"]).is_file()
    assert set(document["dependencies"]) == {
        "jsonschema",
        "attrs",
        "referencing",
        "jsonschema-specifications",
        "rpds-py",
    }
    assert actual_context.document in actual_context.artifacts()


@pytest.mark.parametrize("member", ["context", "source"])
def test_modified_retained_context_or_source_is_refused(
    actual_context: ProducerSourceContext, member: str
) -> None:
    """Refuse actual retained source bytes or metadata that no longer match the snapshot.

    Parameters
    ----------
    actual_context
        Original actual context that passes before corruption.
    member
        Whether the metadata or one actual frozen Python implementation changes.
    """
    actual_context.verify()
    target = actual_context.document
    if member == "source":
        target = (
            actual_context.document.parent
            / "source/parent_package/loop_timing_witness/manifest_io.py"
        )
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="capture producer"):
        actual_context.verify()


def test_native_input_drift_is_refused_without_changing_the_repository(tmp_path: Path) -> None:
    """Detect changed build inputs in a real source copy while retaining canonical bytes.

    Parameters
    ----------
    tmp_path
        Exclusive copied build input and snapshot destination.
    """
    copied = tmp_path / "copy"
    copied.mkdir()
    snapshot_native_sources(REPOSITORY_ROOT, copied)
    root = copied / "source"
    original = REPOSITORY_ROOT / "Makefile"
    saved = original.read_bytes()
    output = tmp_path / "run"
    output.mkdir()
    native = snapshot_native_sources(root, output)
    context = snapshot_producer_context(root, output, native)
    context.verify()
    (root / "Makefile").write_bytes(saved + b"\n")
    with pytest.raises(ValueError, match="capture producer source changed"):
        context.verify()
    assert original.read_bytes() == saved


def test_existing_native_snapshot_drift_is_refused(tmp_path: Path) -> None:
    """Reject a prior actual source copy that changed before the context was constructed.

    Parameters
    ----------
    tmp_path
        Exclusive real repository source snapshot.
    """
    native = snapshot_native_sources(REPOSITORY_ROOT, tmp_path)
    member = tmp_path / "source/Makefile"
    member.write_bytes(member.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="capture producer source changed"):
        snapshot_producer_context(REPOSITORY_ROOT, tmp_path, native)


def test_changed_native_origin_is_refused_even_with_identical_bytes(tmp_path: Path) -> None:
    """Detect an origin replacement while keeping all original repository bytes intact.

    Parameters
    ----------
    tmp_path
        Exclusive actual native copy and context output.
    """
    copied = tmp_path / "copy"
    copied.mkdir()
    snapshot_native_sources(REPOSITORY_ROOT, copied)
    root = copied / "source"
    output = tmp_path / "run"
    output.mkdir()
    context = snapshot_producer_context(root, output, snapshot_native_sources(root, output))
    context.verify()
    origin = root / "Makefile"
    retained = root / "retained-Makefile"
    origin.rename(retained)
    origin.symlink_to(retained.name)
    with pytest.raises(ValueError, match="capture producer source changed"):
        context.verify()


def test_loaded_package_origin_wins_over_a_same_named_checkout_file(tmp_path: Path) -> None:
    """Bind actual loaded JSON code rather than a different file supplied by a native root.

    Parameters
    ----------
    tmp_path
        Actual copied native inputs with an independently modified package source.
    """
    copied = tmp_path / "copy"
    copied.mkdir()
    snapshot_native_sources(REPOSITORY_ROOT, copied)
    root = copied / "source"
    shadow = root / "src/loop_timing_witness/manifest_io.py"
    shadow.parent.mkdir(parents=True)
    original = Path(actual_json.__file__)
    shadow.write_bytes(original.read_bytes() + b"\n")
    output = tmp_path / "run"
    output.mkdir()
    context = snapshot_producer_context(root, output, snapshot_native_sources(root, output))
    context.verify()
    document = json.loads(context.document.read_bytes())
    name = "source/parent_package/loop_timing_witness/manifest_io.py"
    assert Path(document["sources"][name]["origin"]).resolve() == original.resolve()
    assert (output / name).read_bytes() == original.read_bytes()
    assert (output / name).read_bytes() != shadow.read_bytes()


@pytest.mark.parametrize("member", ["origin", "frozen", "context"])
def test_actual_capture_refuses_source_drift_before_acceptance(tmp_path: Path, member: str) -> None:
    """Retain real completed native output but refuse a changed producer context.

    Parameters
    ----------
    tmp_path
        Exclusive source copy, actual native build, and retained failure logs.
    member
        Whether original code, frozen code, or context metadata changes during capture.
    """
    copied = tmp_path / "copy"
    copied.mkdir()
    snapshot_native_sources(REPOSITORY_ROOT, copied, host_load=True)
    root = copied / "source"
    for source in (REPOSITORY_ROOT / "tools").glob("*.py"):
        shutil.copyfile(source, root / "tools" / source.name)
    shutil.copytree(
        Path(actual_json.__file__).parent,
        root / "src/loop_timing_witness",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copyfile(REPOSITORY_ROOT / "measurement-domain.json", root / "measurement-domain.json")
    config = tmp_path / "configuration.txt"
    config.write_text(configuration("pid", "none"), encoding="utf-8")
    output = tmp_path / "capture"
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(str(root / name) for name in ("src", "tools"))
    with (
        (tmp_path / "capture.log").open("w") as log,
        subprocess.Popen(
            [
                sys.executable,
                str(root / "tools/capture_native_simulation.py"),
                str(config),
                "--output-dir",
                str(output),
            ],
            cwd=root,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        ) as process,
    ):
        limit = time.monotonic() + 30
        while (
            not (output / "build.log").exists()
            and process.poll() is None
            and time.monotonic() < limit
        ):
            time.sleep(0.01)
        assert (output / "build.log").exists()
        targets = {
            "origin": root / "src/loop_timing_witness/manifest_io.py",
            "frozen": output / "source/parent_package/loop_timing_witness/manifest_io.py",
            "context": output / "producer_context.json",
        }
        target = targets[member]
        target.write_bytes(target.read_bytes() + b"\n")
        assert process.wait(timeout=120) == 1
    diagnostic = (tmp_path / "capture.log").read_text()
    assert "capture producer" in diagnostic
    assert "changed" in diagnostic
    metadata = json.loads((output / "native_metadata.json").read_bytes())
    assert metadata["result"]["samples"] == 32
    assert metadata["result"]["overflow"] == 0
    assert (output / "events.bin").stat().st_size > 0
    assert not (output / "manifest.json").exists()
    assert not (output / "reports").exists()
