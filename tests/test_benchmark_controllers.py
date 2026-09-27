# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual native comparison and protocol tests

"""Verify source-bound native benchmark artifacts through actual C/Rust programs."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from benchmark_batches import decode_batch
from benchmark_controllers import BINARIES, SOURCES

from conftest import REPOSITORY_ROOT

if TYPE_CHECKING:
    from conftest import RunTool


@pytest.fixture(scope="module")
def native_batches() -> list[str]:
    """Build and execute both actual native benchmark programs.

    Returns
    -------
    list of str
        Actual C and Rust standard output.
    """
    subprocess.run(
        ["make", "controller-build"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        timeout=90,
    )
    return [
        subprocess.run(
            [str(REPOSITORY_ROOT / binary)], check=True, capture_output=True, text=True, timeout=30
        ).stdout
        for binary in (
            "build/controller_benchmark",
            "controllers/rust/target/release/controller_benchmark",
        )
    ]


def test_actual_comparison(native_batches: list[str], tmp_path: Path, run_tool: RunTool) -> None:
    """Check all measured backends, raw parity, warmup exclusion and artifact identity.

    Parameters
    ----------
    native_batches
        Actual native output and completed build.
    tmp_path
        Exclusive output allocation.
    run_tool
        Public comparison CLI.
    """
    assert decode_batch(native_batches[0])[0][3] == decode_batch(native_batches[1])[0][3]
    output = tmp_path / "comparison.json"
    original_affinity = os.sched_getaffinity(0)
    args = [
        "--output",
        str(output),
        "--cpu",
        str(min(original_affinity)),
        "--warmup",
        "1",
        "--repeats",
        "5",
    ]
    result = run_tool("benchmark_controllers", *args)
    assert result.returncode == 0, result.stderr
    artifact = json.loads(output.read_text())
    assert artifact["parameters"] == {"warmup": 1, "repeats": 5, "iterations": 1000000}
    assert artifact["production_performance_claim"] is False
    assert artifact["host"]["child_affinity"] == [min(original_affinity)]
    assert os.sched_getaffinity(0) == original_affinity
    assert artifact["ci_evidence"]["status"] == "not_attested"
    assert len(artifact["raw_batches"]) == 24
    for name, digest in artifact["source_and_binary_sha256"].items():
        assert hashlib.sha256((REPOSITORY_ROOT / name).read_bytes()).hexdigest() == digest
    assert {(row["backend"], row["controller"]) for row in artifact["results"]} == {
        (backend, controller) for backend in ("c", "rust") for controller in ("pid", "lqr")
    }
    for row in artifact["results"]:
        batches = [
            batch
            for batch in artifact["raw_batches"]
            if batch["phase"] == "measured"
            and batch["backend"] == row["backend"]
            and batch["controller"] == row["controller"]
        ]
        samples = sorted(batch["total_ns"] / 1000000 for batch in batches)
        stats = row["stats"]
        assert len(samples) == 5
        assert stats["p50_ns"] == samples[2]
        assert stats["p95_ns"] == pytest.approx(samples[3] + 0.8 * (samples[4] - samples[3]))
        assert stats["p99_ns"] == pytest.approx(samples[3] + 0.96 * (samples[4] - samples[3]))
        assert stats["mean_ns"] == pytest.approx(sum(samples) / 5)
        assert stats["throughput_steps_per_second"] == pytest.approx(1e9 / (sum(samples) / 5))
        assert len({batch["command_checksum"] for batch in batches}) == 1
    original = output.read_bytes()
    repeated = run_tool("benchmark_controllers", *args)
    assert repeated.returncode == 1
    assert output.read_bytes() == original


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--warmup", "0"),
        ("--warmup", "1001"),
        ("--repeats", "4"),
        ("--repeats", "1001"),
        ("--cpu", "-1"),
    ],
)
def test_invalid_parameters(tmp_path: Path, run_tool: RunTool, option: str, value: str) -> None:
    """Refuse invalid measurement bounds or affinity before creating an artifact.

    Parameters
    ----------
    tmp_path
        Exclusive output allocation.
    run_tool
        Actual comparison command.
    option
        Public parameter to invalidate.
    value
        Out-of-range value.
    """
    output = tmp_path / "refused.json"
    result = run_tool(
        "benchmark_controllers",
        "--output",
        str(output),
        "--cpu",
        str(min(os.sched_getaffinity(0))),
        option,
        value,
    )
    assert result.returncode == 1
    assert not output.exists()


@pytest.fixture
def frozen_checkout(native_batches: list[str], tmp_path: Path) -> Path:
    """Copy actual built sources into an owned local checkout for integrity faults.

    Parameters
    ----------
    native_batches
        Actual native build output.
    tmp_path
        Exclusive snapshot allocation.

    Returns
    -------
    Path
        Actual local clone with current source and binary copies.
    """
    assert native_batches
    root = tmp_path / "snapshot"
    subprocess.run(
        ["git", "clone", "--shared", "--no-checkout", str(REPOSITORY_ROOT), str(root)],
        check=True,
        capture_output=True,
        timeout=30,
    )
    for relative in (*SOURCES, *BINARIES.values()):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPOSITORY_ROOT / relative, destination)
    return root


def test_actual_checksum_mismatch(frozen_checkout: Path, tmp_path: Path, run_tool: RunTool) -> None:
    """Refuse a real C workload whose random seed differs from the Rust workload.

    Parameters
    ----------
    frozen_checkout
        Exclusive copied actual sources and built binaries.
    tmp_path
        Exclusive result allocation.
    run_tool
        Actual comparison CLI.
    """
    source = frozen_checkout / "benchmarks/controller_benchmark.c"
    source.write_text(source.read_text().replace("random_state = 1729", "random_state = 1730"))
    subprocess.run(
        [
            "gcc",
            "-std=gnu11",
            "-O3",
            "-flto",
            "-Icontrollers/c",
            "controllers/c/witness_controller.c",
            "benchmarks/controller_benchmark.c",
            "-o",
            "build/controller_benchmark",
        ],
        cwd=frozen_checkout,
        check=True,
        capture_output=True,
        timeout=30,
    )
    output = tmp_path / "mismatch.json"
    result = run_tool(
        "benchmark_controllers",
        "--source-root",
        str(frozen_checkout),
        "--cpu",
        str(min(os.sched_getaffinity(0))),
        "--output",
        str(output),
        "--warmup",
        "1",
        "--repeats",
        "5",
    )
    assert result.returncode == 1
    assert "checksum parity failed" in result.stderr
    assert not output.exists()


def test_actual_source_change(frozen_checkout: Path, tmp_path: Path) -> None:
    """Refuse a real source edit after the benchmark's initial digest snapshot.

    Parameters
    ----------
    frozen_checkout
        Copied actual source and binary allocation owned by this test.
    tmp_path
        Exclusive result allocation.
    """
    output = tmp_path / "changed.json"
    command = [
        str(REPOSITORY_ROOT / ".venv/bin/python"),
        str(REPOSITORY_ROOT / "tools/benchmark_controllers.py"),
        "--source-root",
        str(frozen_checkout),
        "--cpu",
        str(min(os.sched_getaffinity(0))),
        "--output",
        str(output),
        "--warmup",
        "1",
        "--repeats",
        "100",
    ]
    with subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    ) as run:
        limit = time.monotonic() + 10
        children = Path(f"/proc/{run.pid}/task/{run.pid}/children")
        while not children.read_text().strip():
            assert run.poll() is None
            assert time.monotonic() < limit
            time.sleep(0.001)
        source = frozen_checkout / "controllers/c/witness_controller.h"
        source.write_bytes(source.read_bytes() + b"\n")
        _, stderr = run.communicate(timeout=30)
    assert run.returncode == 1
    assert "changed during measurement" in stderr
    assert not output.exists()


@pytest.mark.parametrize("producer", ["benchmark_controllers.py", "benchmark_batches.py"])
def test_snapshot_producer_refusal(
    frozen_checkout: Path, tmp_path: Path, run_tool: RunTool, producer: str
) -> None:
    """Refuse a snapshot that cannot identify the actual executing measurement code.

    Parameters
    ----------
    frozen_checkout
        Actual copied source and binary allocation.
    tmp_path
        Exclusive output allocation.
    run_tool
        Actual comparison CLI.
    producer
        Measurement module deliberately changed in the owned snapshot.
    """
    source = frozen_checkout / "tools" / producer
    source.write_bytes(source.read_bytes() + b"\n")
    output = tmp_path / "producer_mismatch.json"
    result = run_tool(
        "benchmark_controllers",
        "--source-root",
        str(frozen_checkout),
        "--cpu",
        str(min(os.sched_getaffinity(0))),
        "--output",
        str(output),
    )
    assert result.returncode == 1
    assert "differs from executing producer" in result.stderr
    assert not output.exists()
