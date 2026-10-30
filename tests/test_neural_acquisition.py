# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — complete hermetic neural acquisition verification

"""Verify a complete acquisition through the consumer registry, image and report."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from neural_acquisition_support import (
    NeuralAcquisition,
    build_neural_acquisition,
    calibrated_host_installation,
    edit_json,
    make_writable,
)
from neural_rust_support import assert_report_in_both

from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError
from loop_timing_witness.neural_run_api import (
    NeuralRunError,
    build_neural_run_report,
    load_neural_run,
)
from loop_timing_witness.neural_run_dispatch import dispatch_analysis

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from loop_timing_witness.neural_checker_installation import NeuralCheckerInstallation
    from loop_timing_witness.neural_run_policy import NeuralEntry

_DIMENSIONS = ("source_binding", "capture", "numerical", "completion", "clock")


@pytest.fixture(params=[0, 1], ids=["original", "reset"])
def acquisition(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[NeuralAcquisition]:
    """Write one complete acquisition and restore permissions afterwards.

    Parameters
    ----------
    request
        Selected epoch.
    tmp_path
        Owned test directory.

    Yields
    ------
    NeuralAcquisition
        Written acquisition, image and registry entry.
    """
    yield build_neural_acquisition(tmp_path / "run", epoch=request.param)
    make_writable(tmp_path)


def test_complete_acquisition_passes_every_dimension(
    acquisition: NeuralAcquisition, tmp_path: Path
) -> None:
    """Pass all five dimensions in both languages after really running both checker operations.

    Parameters
    ----------
    acquisition
        Complete acquisition admitted by its own registry entry.
    tmp_path
        Owned directory for the Rust run.
    """
    report = build_neural_run_report(
        load_neural_run(acquisition.manifest, registry=acquisition.registry)
    )
    assert_report_in_both(report, acquisition, tmp_path / "rust")
    assert report["verification"]["whole"] is True
    for name in _DIMENSIONS:
        assert report[name]["pass"] is True, report[name]["findings"]
    assert report["numerical"]["source_checker_executed"] is True
    invocations = report["source_binding"]["checker_invocations"]
    assert [invocations[name]["native_returncode"] for name in ("generate", "check")] == [0, 0]
    epoch = report["completion"]["epoch"]
    assert (report["completion"]["reset_receipt"] is None) is (epoch == 0)


def test_dispatch_publishes_the_passing_report(
    acquisition: NeuralAcquisition, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Publish one report and print the passing verdict.

    Parameters
    ----------
    acquisition
        Complete acquisition admitted by its own registry entry.
    tmp_path
        Owned report parent.
    capsys
        Captured command output.
    """
    output = tmp_path / "report"
    status, raw = dispatch_analysis(acquisition.manifest, output, registry=acquisition.registry)
    assert status == 0
    assert raw == acquisition.manifest.read_bytes()
    assert json.loads((output / "report.json").read_bytes())["verification"]["whole"] is True
    assert capsys.readouterr().out == f"run analysis: PASS: {output}\n"


def test_reviewed_registry_does_not_admit_a_test_acquisition(
    acquisition: NeuralAcquisition, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Refuse the same acquisition when only the shipped reviewed entries apply.

    Parameters
    ----------
    acquisition
        Complete acquisition that the shipped registry does not know.
    tmp_path
        Owned report parent.
    capsys
        Captured command output.
    """
    output = tmp_path / "report"
    status, _ = dispatch_analysis(acquisition.manifest, output)
    assert status == 1
    assert "No reviewed source contract is admitted" in capsys.readouterr().err
    assert not output.exists()


@pytest.fixture(scope="module")
def host_installation(tmp_path_factory: pytest.TempPathFactory) -> NeuralCheckerInstallation:
    """Calibrate one host installation from the real traced checker runs.

    Parameters
    ----------
    tmp_path_factory
        Owned calibration directory.

    Returns
    -------
    NeuralCheckerInstallation
        Running interpreter, actual tracer and every observed runtime file.
    """
    return calibrated_host_installation(tmp_path_factory.mktemp("calibration"))


def test_host_installation_passes_under_the_traced_isolated_worker(
    host_installation: NeuralCheckerInstallation, tmp_path: Path
) -> None:
    """Pass every dimension in both languages through the traced, isolated host worker.

    Parameters
    ----------
    host_installation
        Calibrated reviewed host installation.
    tmp_path
        Owned acquisition directory.
    """
    acquisition = build_neural_acquisition(tmp_path / "run", installation=host_installation)
    try:
        report = build_neural_run_report(
            load_neural_run(acquisition.manifest, registry=acquisition.registry)
        )
        assert_report_in_both(report, acquisition, tmp_path / "rust")
    finally:
        make_writable(tmp_path)
    assert report["verification"]["whole"] is True, report["verification"]
    receipt = report["source_binding"]["checker_invocations"]["check"]
    assert receipt["worker_observation"]["phase"] == "source"
    assert str(host_installation.tracer.path) in receipt["command"]


def _raising(error: BaseException) -> Callable[[], NeuralEntry]:
    """Return a consumer registry factory that fails with one error.

    Parameters
    ----------
    error
        Error raised by the factory.

    Returns
    -------
    Callable[[], NeuralEntry]
        Failing factory.
    """

    def factory() -> NeuralEntry:
        """Fail while selecting the reviewed entry.

        Raises
        ------
        BaseException
            The selected error.
        """
        raise error

    return factory


def test_registry_entry_must_keep_its_reviewed_identity(tmp_path: Path) -> None:
    """Refuse a registry entry whose policy no longer matches its own key.

    Parameters
    ----------
    tmp_path
        Owned acquisition directory.
    """
    acquisition = build_neural_acquisition(tmp_path / "run")
    make_writable(tmp_path)
    (key,) = acquisition.registry
    policy, checker, executor = acquisition.entry
    registry = {key: lambda: (policy + b" ", checker, executor)}
    with pytest.raises(NeuralCaptureRefusalError, match="differs from its reviewed identity"):
        load_neural_run(acquisition.manifest, registry=registry)


def test_registry_failures_are_bounded_and_dispatched_without_details(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Map an unreadable entry to a refusal and an unexpected failure to a fixed error.

    Parameters
    ----------
    tmp_path
        Owned acquisition and report parent.
    capsys
        Captured command output.
    """
    acquisition = build_neural_acquisition(tmp_path / "run")
    make_writable(tmp_path)
    (key,) = acquisition.registry
    unreadable = {key: _raising(OSError("hidden detail"))}
    with pytest.raises(NeuralCaptureRefusalError, match="Cannot bind the complete public neural"):
        load_neural_run(acquisition.manifest, registry=unreadable)
    broken = {key: _raising(RuntimeError("hidden detail"))}
    with pytest.raises(NeuralRunError, match="Neural run analysis failed"):
        load_neural_run(acquisition.manifest, registry=broken)
    status, _ = dispatch_analysis(acquisition.manifest, tmp_path / "report", registry=broken)
    assert status == 1
    error = capsys.readouterr().err
    assert error == "run analysis: FAIL: Neural analysis or report publication failed.\n"
    assert not (tmp_path / "report").exists()


def test_dispatch_returns_legacy_roots_and_invalid_neural_verdicts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Return a legacy root unchanged and status two for an interpretable failure.

    Parameters
    ----------
    tmp_path
        Owned acquisition, legacy root and report parent.
    capsys
        Captured command output.
    """
    legacy = tmp_path / "legacy.json"
    legacy.write_bytes(b'{"profile": "control"}')
    assert dispatch_analysis(legacy, tmp_path / "unused") == (None, legacy.read_bytes())
    change = edit_json("clock-schedule.json", lambda value: value.update(first_input_tick=21))
    acquisition = build_neural_acquisition(tmp_path / "run", change=change)
    output = tmp_path / "report"
    status, _ = dispatch_analysis(acquisition.manifest, output, registry=acquisition.registry)
    make_writable(tmp_path)
    assert status == 2
    assert capsys.readouterr().out == f"run analysis: INVALID: {output}\n"
    assert json.loads((output / "report.json").read_bytes())["clock"]["pass"] is False
