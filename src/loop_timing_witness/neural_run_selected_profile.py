# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — exact selected simulation source and runtime profile

"""Construct the reviewed simulation registrations from pinned consumer assets."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Final

from .manifest_io import parse_json_object
from .neural_checker_image import ImageCheckerExecutor
from .neural_checker_installation import CheckerInstalledFile, NeuralCheckerInstallation
from .neural_event_stream import NeuralCaptureRefusalError

SOURCE_CONTRACT_SHA256: Final = "ec1236a69fc9e16a4eff1dfa7bdad8aa8b6088fc4ebceb8d8c43d33517199304"
IMAGE_SOURCE_CONTRACT_SHA256: Final = (
    "5ff959e55f59ca3b1d1993bbc2ed9028c49e08feb6ff15a0fd5af156959d5488"
)
IMAGE_ROOT_VARIABLE: Final = "LOOP_TIMING_WITNESS_CHECKER_IMAGE"
INSTALLATION_VARIABLE: Final = "LOOP_TIMING_WITNESS_CHECKER_INSTALLATION"
IMAGE_BINDING_VARIABLE: Final = "LOOP_TIMING_WITNESS_CHECKER_IMAGE_BINDING"
_ASSET_LIMIT: Final = 262144
# Host-specific descriptors are supplied by the operator, never packaged;
# only their reviewed digests are part of the consumer registry.
INSTALLATION_SHA256: Final = "7e0e98ba8c02f8a5cf6d9ae58d9146d2106b1211ae0739f0945f2eeb093a611d"
IMAGE_BINDING_SHA256: Final = "92727d94d239cab44f1ff966a890a438f5864086e8129b594ad75828c420ae2a"
_ASSETS: Final = {
    "neural-selected-source-contract.json": SOURCE_CONTRACT_SHA256,
    "neural-selected-checker-policy.json": (
        "443d6a1bfaa20f317e0e730d5659be13a4f07b6dd98469a333b2c0baa9feb390"
    ),
    "neural-selected-checker-runtime.json": (
        "7f37448dcd18d9c2b41b2f1966154a5cff9f96081195a79b6dd5a5c8596b4890"
    ),
    "neural-image-source-contract.json": IMAGE_SOURCE_CONTRACT_SHA256,
    "neural-image-checker-policy.json": (
        "be96f75a8f2f43ceeaae212bc481348e5d05b3ca795f7f97ee75c6cf11d691ce"
    ),
    "neural-image-checker-runtime.json": (
        "5e3f47b55576fc977f339d994e746ee23166d93e03ad4e6f33b90ca15b04dd9a"
    ),
}


def _asset(name: str) -> bytes:
    """Read one exact consumer asset through a finite regular no-follow descriptor.

    Parameters
    ----------
    name
        Fixed asset role selected by this module, never an acquisition path.

    Returns
    -------
    bytes
        Complete reviewed bytes with the exact selected identity.

    Raises
    ------
    NeuralCaptureRefusalError
        If package data is unavailable, nonregular, oversized or changed.
    """
    return _pinned(Path(__file__).with_name("data") / name, _ASSETS[name])


def _pinned(path: Path, expected: str) -> bytes:
    """Read one finite regular no-follow file with an exact reviewed digest.

    Parameters
    ----------
    path
        Package asset or operator-selected descriptor.
    expected
        Reviewed SHA-256 of the complete bytes.

    Returns
    -------
    bytes
        Complete reviewed bytes.

    Raises
    ------
    NeuralCaptureRefusalError
        If the file is unavailable, nonregular, oversized or changed.
    """
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                message = "Selected neural profile asset must be a regular file."
                raise NeuralCaptureRefusalError(message)
            raw = stream.read(_ASSET_LIMIT + 1)
    except OSError as exc:
        message = "Selected neural profile installation asset is unavailable."
        raise NeuralCaptureRefusalError(message) from exc
    if len(raw) > _ASSET_LIMIT or hashlib.sha256(raw).hexdigest() != expected:
        message = "Selected neural profile asset differs from its reviewed binding."
        raise NeuralCaptureRefusalError(message)
    return raw


def _operator_file(variable: str, expected: str, missing: str) -> bytes:
    """Read the reviewed host-specific descriptor that the operator selects.

    Parameters
    ----------
    variable
        Environment variable naming an absolute descriptor path.
    expected
        Reviewed SHA-256 of the descriptor.
    missing
        Refusal when no absolute path is selected.

    Returns
    -------
    bytes
        Complete reviewed descriptor bytes.

    Raises
    ------
    NeuralCaptureRefusalError
        If no absolute path is selected or the descriptor differs.
    """
    selected = os.environ.get(variable, "")
    if not selected or not Path(selected).is_absolute():
        raise NeuralCaptureRefusalError(missing)
    return _pinned(Path(selected), expected)


def selected_neural_profile() -> tuple[bytes, bytes, NeuralCheckerInstallation]:
    """Construct the exact source-owner-selected bounded simulation registration.

    Returns
    -------
    tuple[bytes, bytes, NeuralCheckerInstallation]
        Frozen source and checker policies with the selected consumer installation.
        Host paths come from the operator's reviewed installation descriptor,
        selected by ``LOOP_TIMING_WITNESS_CHECKER_INSTALLATION``; acquisition data cannot
        select an executable, environment, import root or policy replacement.

    Raises
    ------
    NeuralCaptureRefusalError
        If package assets, the operator descriptor or the installed worker bodies differ.
    """
    policy = _asset("neural-selected-source-contract.json")
    checker = _asset("neural-selected-checker-policy.json")
    runtime_bytes = _asset("neural-selected-checker-runtime.json")
    runtime = parse_json_object(runtime_bytes, "selected checker runtime")
    descriptor = _operator_file(
        INSTALLATION_VARIABLE,
        INSTALLATION_SHA256,
        "No reviewed checker installation descriptor is selected for this neural registration.",
    )
    settings = parse_json_object(descriptor, "selected consumer installation")
    files = tuple(
        CheckerInstalledFile(
            item["name"], Path(item["actual_path"]), item["sha256"], item["byte_length"]
        )
        for item in settings["bindings"]
    )
    installation = NeuralCheckerInstallation(
        next(item for item in files if item.name == runtime["interpreter"]["path"]),
        next(item for item in files if item.name == runtime["tracer"]["path"]),
        files,
        tuple(Path(name) for name in settings["import_roots"]),
        runtime["platform_baseline"]["id"],
        runtime["platform_baseline"]["kernel_release"],
    )
    if installation.contract_bytes() != runtime_bytes:
        message = "Selected checker worker or installation differs from its reviewed runtime."
        raise NeuralCaptureRefusalError(message)
    return policy, checker, installation


def image_neural_profile() -> tuple[bytes, bytes, ImageCheckerExecutor]:
    """Construct the source owner's qualified immutable executor registration.

    Returns
    -------
    tuple[bytes, bytes, ImageCheckerExecutor]
        Frozen successor source and checker policies with the image executor.
        The operator selects the extracted image directory through
        ``LOOP_TIMING_WITNESS_CHECKER_IMAGE``; the image is verified against the
        pinned inventory before every use, so the path cannot select other code.
        The reviewed executor binding, which names host files, is selected
        through ``LOOP_TIMING_WITNESS_CHECKER_IMAGE_BINDING``.

    Raises
    ------
    NeuralCaptureRefusalError
        If package assets or the binding differ, or no absolute binding or image
        directory is selected.
    """
    policy = _asset("neural-image-source-contract.json")
    checker = _asset("neural-image-checker-policy.json")
    runtime = _asset("neural-image-checker-runtime.json")
    binding = _operator_file(
        IMAGE_BINDING_VARIABLE,
        IMAGE_BINDING_SHA256,
        "No immutable checker image binding is selected for this neural registration.",
    )
    selected = os.environ.get(IMAGE_ROOT_VARIABLE, "")
    if not selected or not Path(selected).is_absolute():
        message = "No immutable checker image is selected for this neural registration."
        raise NeuralCaptureRefusalError(message)
    return policy, checker, ImageCheckerExecutor(Path(selected), binding, runtime)
