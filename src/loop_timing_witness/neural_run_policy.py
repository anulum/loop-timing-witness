# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — immutable public neural source admission

"""Select reviewed source and checker installations using consumer-owned identities."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from .manifest_io import JsonInputRefusalError, parse_json_object
from .neural_event_stream import NeuralCaptureRefusalError
from .neural_run_files import read_neural_run_file as read_neural_bound_file
from .neural_run_manifest import NEURAL_SCHEMA_ID, NEURAL_SCHEMA_SHA256
from .neural_run_selected_profile import (
    IMAGE_SOURCE_CONTRACT_SHA256,
    SOURCE_CONTRACT_SHA256,
    image_neural_profile,
    selected_neural_profile,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from .neural_checker_image import ImageCheckerExecutor
    from .neural_checker_installation import NeuralCheckerInstallation

NATIVE_SCHEMA_ID: Final = NEURAL_SCHEMA_ID
ARTIFACT_LIMIT: Final = 8 * 1024 * 1024
PUBLIC_COHORT: Final = "sc-neurocore-neural-step-1n1b16t.v1"
_ARTIFACT_FIELDS: Final = {
    "native_executable",
    "generated_model_archive",
    "generated_model_header",
    "verilated_runtime_object",
    "verilated_threads_object",
}


def _policy_pin(value: object, *, with_path: bool) -> bool:
    """Check the closed native pin or file-reference wire types.

    Parameters
    ----------
    value
        Decoded source-policy reference, before any file is opened.
    with_path
        Require a file path in addition to the digest and unsigned byte count.

    Returns
    -------
    bool
        Whether every field matches the native policy's declared representation.
    """
    fields = {"sha256", "byte_length"}
    if with_path:
        fields.add("path")
    if not isinstance(value, dict) or set(value) != fields:
        return False
    if not isinstance(value["sha256"], str):
        return False
    if with_path and not isinstance(value["path"], str):
        return False
    length = value["byte_length"]
    return type(length) is int and 0 <= length < 2**64


def _compiled_policy(value: object) -> bool:
    """Check the complete native compiled-artifact structure.

    Parameters
    ----------
    value
        One source-policy compiled population.

    Returns
    -------
    bool
        Whether exactly the five required roles contain closed file references.
    """
    return (
        isinstance(value, dict)
        and set(value) == _ARTIFACT_FIELDS
        and all(_policy_pin(reference, with_path=True) for reference in value.values())
    )


def _policy_tables(value: dict[str, Any]) -> bool:
    """Check the source policy's object tables without interpreting their claims.

    Parameters
    ----------
    value
        Root policy with every required field already present.

    Returns
    -------
    bool
        Whether tool strings, nonempty source and artifact maps and the checker
        reference match the native wire structures.
    """
    versions = value["tool_versions"]
    sources = value["sources"]
    compiled = value["compiled_artifacts"]
    if not isinstance(versions, dict) or not all(
        isinstance(version, str) for version in versions.values()
    ):
        return False
    if (
        not isinstance(sources, dict)
        or not sources
        or not all(_policy_pin(reference, with_path=False) for reference in sources.values())
    ):
        return False
    if (
        not isinstance(compiled, dict)
        or not compiled
        or not all(_compiled_policy(population) for population in compiled.values())
    ):
        return False
    return _policy_pin(value["checker_policy_ref"], with_path=True)


@dataclass(frozen=True, slots=True)
class NeuralSourceContract:
    """Reviewed immutable policy bytes and their actual consumer runtime binding.

    Attributes
    ----------
    policy_bytes
        Exact public source policy with the required checker-policy reference.
    checker_policy_bytes
        Exact static checker entry point, source closure and execution contract.
    installation
        Reviewed host installation, or the source owner's qualified immutable
        executor image for a successor registration.
    """

    policy_bytes: bytes
    checker_policy_bytes: bytes
    installation: NeuralCheckerInstallation | ImageCheckerExecutor

    @property
    def key(self) -> tuple[str, str, str, str]:
        """Return the complete consumer admission identity.

        Returns
        -------
        tuple[str, str, str, str]
            Schema ID, schema SHA-256, cohort and exact source-contract digest.
        """
        return (
            NEURAL_SCHEMA_ID,
            NEURAL_SCHEMA_SHA256,
            PUBLIC_COHORT,
            hashlib.sha256(self.policy_bytes).hexdigest(),
        )

    @property
    def policy(self) -> dict[str, Any]:
        """Decode a fresh closed view of the reviewed source policy.

        Returns
        -------
        dict[str, Any]
            Exact policy declarations; caller mutation cannot alter stored bytes.

        Raises
        ------
        NeuralCaptureRefusalError
            If the consumer's policy does not implement the public successor.
        """
        try:
            value = parse_json_object(self.policy_bytes, "consumer source policy")
        except JsonInputRefusalError as exc:
            message = "Consumer public source policy is not a closed JSON object."
            raise NeuralCaptureRefusalError(message) from exc
        fields = {
            "schema_sha256",
            "schema_id",
            "cohort",
            "tool_versions",
            "sources",
            "compiled_artifacts",
            "checker_policy_ref",
        }
        if (
            set(value) != fields
            or value["schema_id"] != NEURAL_SCHEMA_ID
            or value["schema_sha256"] != NEURAL_SCHEMA_SHA256
            or value["cohort"] != PUBLIC_COHORT
            or not _policy_tables(value)
        ):
            message = "Consumer public source policy does not implement its closed contract."
            raise NeuralCaptureRefusalError(message)
        return value


type NeuralEntry = tuple[bytes, bytes, NeuralCheckerInstallation | ImageCheckerExecutor]
"""Reviewed source policy, checker policy and checker executor bytes of one entry."""

type NeuralRegistry = Mapping[tuple[str, str, str, str], Callable[[], NeuralEntry]]
"""Consumer-owned map from admission identity to its reviewed entry factory."""

REVIEWED_REGISTRY: Final[NeuralRegistry] = MappingProxyType(
    {
        (
            NEURAL_SCHEMA_ID,
            NEURAL_SCHEMA_SHA256,
            PUBLIC_COHORT,
            SOURCE_CONTRACT_SHA256,
        ): selected_neural_profile,
        (
            NEURAL_SCHEMA_ID,
            NEURAL_SCHEMA_SHA256,
            PUBLIC_COHORT,
            IMAGE_SOURCE_CONTRACT_SHA256,
        ): image_neural_profile,
    }
)


def admitted_neural_contract(
    directory: Path, manifest: dict[str, Any], registry: NeuralRegistry = REVIEWED_REGISTRY
) -> NeuralSourceContract:
    """Bind a source contract only after exact consumer-owned registry selection.

    Parameters
    ----------
    directory
        Immutable acquisition root containing the declared contract copy.
    manifest
        Closed public carrier declarations from the public manifest reader.
    registry
        The consumer's own reviewed entries; acquisition data never selects it.

    Returns
    -------
    NeuralSourceContract
        The consumer's reviewed source/checker/runtime entry, never run-selected code.

    Raises
    ------
    NeuralCaptureRefusalError
        If no reviewed source entry is installed or the copied contract differs.
    """
    key = (
        manifest["schema_id"],
        NEURAL_SCHEMA_SHA256,
        manifest["native_source_cohort"],
        manifest["source_contract_ref"]["sha256"],
    )
    factory = registry.get(key)
    if factory is None:
        message = "No reviewed source contract is admitted for this neural run."
        raise NeuralCaptureRefusalError(message)
    entry = NeuralSourceContract(*factory())
    if entry.key != key:
        message = "Selected neural source registration differs from its reviewed identity."
        raise NeuralCaptureRefusalError(message)
    read_neural_bound_file(
        directory,
        manifest["source_contract_ref"],
        65536,
        expected_bytes=entry.policy_bytes,
        mismatch_message=(
            "Acquired neural source contract differs from its reviewed consumer policy."
        ),
    )
    _ = entry.policy
    return entry
