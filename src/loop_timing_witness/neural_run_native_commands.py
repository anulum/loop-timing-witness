# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — recorded native command predicates

"""Reconcile original recorded commands without invoking run-supplied code."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .neural_run_binding import BoundNeuralRun

DEFAULTS = {
    "EXTRA_STATE_REGISTER": 0,
    "TIMESTAMP_OFFSET": 0,
    "DROP_ENCODER_FEED": 0,
    "ADDRESS_BITS": 10,
}
SELECTED_STEPS = 1000
COMPILED_RTL = {
    "native_neural_dut.sv",
    "source/proposed_neural_wrapper.sv",
    "source/SC-NEUROCORE/hdl/sc_lif_neuron.v",
    "source/SC-NEUROCORE/hdl/sc_aer_encoder.v",
    "source/LOOP-TIMING-WITNESS/rtl/clock_reset_release.sv",
    "source/LOOP-TIMING-WITNESS/rtl/shared_event_witness.sv",
    "source/LOOP-TIMING-WITNESS/rtl/event_record_fifo.sv",
}


_VERILATOR_OPTIONS = frozenset(
    {"--cc", "--Wall", "--assert", "+1800-2012ext+v", "+1800-2012ext+sv"}
)
_CPP_OPTIONS = frozenset({"-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-Wshadow"})


def _arguments_match(run: BoundNeuralRun, runtime: dict[str, Any]) -> bool:
    """Tell whether the recorded compiler and run arguments are the selected ones.

    Parameters
    ----------
    run
        Full source-bound native run.
    runtime
        Complete closed decoded runtime receipt.

    Returns
    -------
    bool
        Whether Verilator received exactly the non-default parameter flags, the
        SystemVerilog dialect and the required options, the C++ compile received
        the native trial source and the required warnings, and the run mode is
        the run's epoch mode.
    """
    params = runtime["parameters"]
    paths = runtime["actual_source_paths"]
    jobs = runtime["jobs"]
    flags = {f"-G{name}={value}" for name, value in params.items() if value != DEFAULTS[name]}
    verilator = jobs[0]["command"]
    cpp = jobs[2]["command"]
    mode = "reset" if run.manifest["epoch"] else "original"
    actual_native = next(path for path, name in paths.items() if name == "native/native_trial.cpp")
    return (
        {arg for arg in verilator if arg.startswith("-G")} == flags
        and ["--language", "1800-2012"] in [verilator[i : i + 2] for i in range(len(verilator) - 1)]
        and _VERILATOR_OPTIONS.issubset(verilator)
        and actual_native in cpp
        and _CPP_OPTIONS.issubset(cpp)
        and jobs[4]["command"][-1] == mode
    )


def native_command_findings(run: BoundNeuralRun, runtime: dict[str, Any]) -> tuple[str, ...]:
    """Compare actual compiler, source, parameter, mode and execution declarations.

    Parameters
    ----------
    run
        Full source-bound native run with already bound original object/log bytes.
    runtime
        Complete closed decoded runtime receipt.

    Returns
    -------
    tuple[str, ...]
        Reliable contradictions or known deliberate source fault configurations.
    """
    params = runtime["parameters"]
    paths = runtime["actual_source_paths"]
    jobs = runtime["jobs"]
    failures = []
    if {paths[arg] for arg in jobs[0]["command"] if arg in paths} != COMPILED_RTL:
        failures.append("Actual native compiled RTL source inventory differs.")
    if runtime["tool_versions"] != run.contract.policy["tool_versions"]:
        failures.append("Actual native compiler versions differ.")
    if (
        runtime["backend"] != "verilator-native-cpp"
        or runtime["dialect"] != "1800-2012"
        or runtime["epoch"] != run.manifest["epoch"]
        or runtime["steps"] != SELECTED_STEPS
        or run.manifest["fifo_capacity_records"] != 1 << params["ADDRESS_BITS"]
    ):
        failures.append("Actual native runtime identity/configuration differs.")
    if not _arguments_match(run, runtime):
        failures.append("Actual native compiler/dialect/run arguments differ.")
    if (
        any(job["returncode"] != 0 for job in jobs)
        or run.files["native_job_4_stdout"] != b"NATIVE_JOINT_EXPORT_COMPLETE\n"
        or run.files["native_job_4_stderr"]
    ):
        failures.append("Actual native build/execution did not complete cleanly.")
    if params != DEFAULTS:
        failures.append("Actual compile parameters differ from selected source configuration.")
    return tuple(failures)
