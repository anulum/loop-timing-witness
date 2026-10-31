# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — public source-policy shape and immutable admission controls

"""Decode the authentic policy and refuse altered metadata without registering it."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from neural_operator_support import adopt_operator_descriptors, image_binding

from loop_timing_witness.neural_checker_image import ImageCheckerExecutor
from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError
from loop_timing_witness.neural_run_manifest import load_neural_manifest
from loop_timing_witness.neural_run_policy import NeuralSourceContract, admitted_neural_contract
from loop_timing_witness.neural_run_selected_profile import (
    IMAGE_ROOT_VARIABLE,
    IMAGE_SOURCE_CONTRACT_SHA256,
)

_ROOT = Path(__file__).resolve().parents[1]
_POLICY_SHA = IMAGE_SOURCE_CONTRACT_SHA256
_IMAGE = "/absent-operator-image"


def _image_entry() -> tuple[bytes, bytes, ImageCheckerExecutor]:
    """Return the packaged image policies with a test executor binding.

    Returns
    -------
    tuple[bytes, bytes, ImageCheckerExecutor]
        Reviewed source and checker policies; the image is never opened here.
    """
    data = _ROOT / "src/loop_timing_witness/data"
    runtime = (data / "neural-image-checker-runtime.json").read_bytes()
    return (
        (data / "neural-image-source-contract.json").read_bytes(),
        (data / "neural-image-checker-policy.json").read_bytes(),
        ImageCheckerExecutor(Path(_IMAGE), image_binding(), runtime),
    )


@pytest.fixture
def source_contract() -> NeuralSourceContract:
    """Construct the exact reviewed image policy without claiming runtime execution.

    Returns
    -------
    NeuralSourceContract
        Authentic immutable policy, checker and executor metadata.
    """
    contract = NeuralSourceContract(*_image_entry())
    assert hashlib.sha256(contract.policy_bytes).hexdigest() == _POLICY_SHA
    return contract


def _view(contract: NeuralSourceContract, value: dict[str, Any]) -> dict[str, Any]:
    """Decode an altered policy through its public view, without admitting a new key.

    Parameters
    ----------
    contract
        Selected original checker and installation metadata.
    value
        A complete original policy with deliberate caller-side damage.

    Returns
    -------
    dict[str, Any]
        Public policy view, if the entire declaration is structurally valid.
    """
    return NeuralSourceContract(
        json.dumps(value).encode(), contract.checker_policy_bytes, contract.installation
    ).policy


def test_original_policy_identity_and_fresh_view_preserve_all_source_bindings(
    source_contract: NeuralSourceContract,
) -> None:
    """Keep the authentic source identity immutable when a returned view is edited.

    Parameters
    ----------
    source_contract
        Exact selected source policy and unchanged worker metadata.
    """
    expected = json.loads(source_contract.policy_bytes)
    assert source_contract.key == (
        "loop-timing-witness.neural-step-run.v1",
        "846d131e51cff0dee88d8c9484e435eb02444e0f0a18b58e9d5f053633164f8f",
        "sc-neurocore-neural-step-1n1b16t.v1",
        _POLICY_SHA,
    )
    actual = source_contract.policy
    assert actual == expected
    assert len(actual["sources"]) == 57
    assert len(actual["compiled_artifacts"]) == 6
    actual["sources"].clear()
    assert source_contract.policy == expected
    assert hashlib.sha256(source_contract.policy_bytes).hexdigest() == _POLICY_SHA


@pytest.mark.parametrize(
    "field", ["tool_versions", "sources", "compiled_artifacts", "checker_policy_ref"]
)
@pytest.mark.parametrize("bad_value", [True, 1, "not a mapping", ["not a mapping"], None])
def test_non_mapping_policy_tables_refuse(
    source_contract: NeuralSourceContract, field: str, bad_value: object
) -> None:
    """Reject non-object policy fields derived from the exact original declaration.

    Parameters
    ----------
    source_contract
        Selected original policy used for the single damaged field.
    field
        Required source, tool, artifact or checker-reference object.
    bad_value
        JSON value that has no object structure.
    """
    value = source_contract.policy
    value[field] = bad_value
    with pytest.raises(NeuralCaptureRefusalError, match="closed contract"):
        _view(source_contract, value)


@pytest.mark.parametrize(
    "damage", ["schema", "schema-digest", "cohort", "missing", "extra", "sources", "artifacts"]
)
def test_source_identity_and_closed_population_remain_required(
    source_contract: NeuralSourceContract, damage: str
) -> None:
    """Refuse identity changes, unknown fields and empty source or artifact populations.

    Parameters
    ----------
    source_contract
        Actual selected policy whose structural identity is contradicted.
    damage
        One closed-contract or required-population violation.
    """
    value = source_contract.policy
    if damage == "schema":
        value["schema_id"] = "unsupported"
    elif damage == "schema-digest":
        value["schema_sha256"] = "0" * 64
    elif damage == "cohort":
        value["cohort"] = "unsupported"
    elif damage == "missing":
        del value["tool_versions"]
    elif damage == "extra":
        value["extra"] = True
    elif damage == "sources":
        value["sources"] = {}
    else:
        value["compiled_artifacts"] = {}
    with pytest.raises(NeuralCaptureRefusalError, match="closed contract"):
        _view(source_contract, value)


@pytest.mark.parametrize("bad_version", [True, 1, ["version"]])
def test_tool_versions_require_string_values(
    source_contract: NeuralSourceContract, bad_version: object
) -> None:
    """Keep the reviewed tool-version map consistent with its native string values.

    Parameters
    ----------
    source_contract
        Authentic tool-version map.
    bad_version
        Unsupported type at one original tool entry.
    """
    value = source_contract.policy
    value["tool_versions"][next(iter(value["tool_versions"]))] = bad_version
    with pytest.raises(NeuralCaptureRefusalError, match="closed contract"):
        _view(source_contract, value)


@pytest.mark.parametrize("role", ["source", "checker", "artifact"])
@pytest.mark.parametrize(
    "damage",
    [
        "not-object",
        "extra",
        "missing",
        "sha-type",
        "length-bool",
        "length-float",
        "negative",
        "overflow",
    ],
)
def test_entire_source_and_compiled_references_require_closed_native_types(
    source_contract: NeuralSourceContract, role: str, damage: str
) -> None:
    """Refuse malformed complete pins at every source-policy reference role.

    Parameters
    ----------
    source_contract
        Original source and compiled-object bindings.
    role
        Source pin, checker file or compiled executable reference.
    damage
        Actual JSON shape, field or unsigned-64-bit contradiction.
    """
    value = source_contract.policy
    if role == "source":
        parent = value["sources"]
        name = next(iter(parent))
    elif role == "checker":
        parent, name = value, "checker_policy_ref"
    else:
        parent = next(iter(value["compiled_artifacts"].values()))
        name = "native_executable"
    if damage == "not-object":
        parent[name] = True
    elif damage == "extra":
        parent[name]["extra"] = True
    elif damage == "missing":
        del parent[name]["sha256"]
    elif damage == "sha-type":
        parent[name]["sha256"] = True
    else:
        lengths = {"length-bool": True, "length-float": 1.0, "negative": -1, "overflow": 2**64}
        parent[name]["byte_length"] = lengths[damage]
    with pytest.raises(NeuralCaptureRefusalError, match="closed contract"):
        _view(source_contract, value)


@pytest.mark.parametrize("role", ["checker", "artifact"])
def test_referenced_file_paths_require_strings(
    source_contract: NeuralSourceContract, role: str
) -> None:
    """Refuse a non-string path without opening any source-policy referent.

    Parameters
    ----------
    source_contract
        Original references selected by the consumer.
    role
        Checker or compiled executable reference.
    """
    value = source_contract.policy
    reference = (
        value["checker_policy_ref"]
        if role == "checker"
        else next(iter(value["compiled_artifacts"].values()))["native_executable"]
    )
    reference["path"] = True
    with pytest.raises(NeuralCaptureRefusalError, match="closed contract"):
        _view(source_contract, value)


@pytest.mark.parametrize("damage", ["not-object", "missing", "extra"])
def test_compiled_population_keeps_every_native_artifact_role(
    source_contract: NeuralSourceContract, damage: str
) -> None:
    """Keep the source policy's complete five-role compiled artifact structure.

    Parameters
    ----------
    source_contract
        Authentic six compiled populations.
    damage
        Non-object, absent required object or unknown artifact role.
    """
    value = source_contract.policy
    name = next(iter(value["compiled_artifacts"]))
    if damage == "not-object":
        value["compiled_artifacts"][name] = True
    elif damage == "missing":
        del value["compiled_artifacts"][name]["verilated_threads_object"]
    else:
        value["compiled_artifacts"][name]["extra"] = value["checker_policy_ref"]
    with pytest.raises(NeuralCaptureRefusalError, match="closed contract"):
        _view(source_contract, value)


@pytest.mark.parametrize(
    "raw", [b"{", b"\xff", b"null", b"[]", b"1", b'"text"', b'{"x":NaN}', b'{"x":1,"x":2}']
)
def test_invalid_policy_json_uses_the_domain_refusal(
    source_contract: NeuralSourceContract, raw: bytes
) -> None:
    """Refuse actual non-object, duplicate, non-finite or undecodable policy bytes.

    Parameters
    ----------
    source_contract
        Original checker and installation selection.
    raw
        Invalid caller-supplied policy bytes.
    """
    with pytest.raises(NeuralCaptureRefusalError, match="closed JSON object"):
        _ = NeuralSourceContract(
            raw, source_contract.checker_policy_bytes, source_contract.installation
        ).policy


def test_actual_registered_contract_binds_its_original_bytes(tmp_path: Path) -> None:
    """Select the reviewed image tuple and bind its complete source-policy file.

    Parameters
    ----------
    tmp_path
        Owned original policy copy; this is not a complete acquisition.
    """
    original = _ROOT / "tests/data/neural-selected-original.run.json"
    manifest = load_neural_manifest(original)
    entry = _image_entry()
    policy = entry[0]
    registry = {NeuralSourceContract(*entry).key: lambda: entry}
    manifest["source_contract_ref"] |= {"sha256": _POLICY_SHA, "byte_length": len(policy)}
    target = tmp_path / manifest["source_contract_ref"]["path"]
    target.write_bytes(policy)
    contract = admitted_neural_contract(tmp_path, manifest, registry)
    assert contract.policy_bytes == policy
    assert contract.key[-1] == _POLICY_SHA
    assert not list(tmp_path.glob("checker-observation.json"))
    changed = bytearray(policy)
    changed[0] ^= 1
    target.write_bytes(changed)
    with pytest.raises(
        NeuralCaptureRefusalError,
        match="Acquired neural source contract differs from its reviewed consumer policy",
    ):
        admitted_neural_contract(tmp_path, manifest, registry)
    target.write_bytes(policy + b" ")
    with pytest.raises(NeuralCaptureRefusalError, match="Original file exceeds allocation"):
        admitted_neural_contract(tmp_path, manifest, registry)


def test_unregistered_policy_identity_never_selects_an_executable(tmp_path: Path) -> None:
    """Refuse an unsupported digest before any source or runtime file is required.

    Parameters
    ----------
    tmp_path
        Empty acquisition root for the unsupported public tuple.
    """
    manifest = load_neural_manifest(_ROOT / "tests/data/neural-selected-original.run.json")
    manifest["source_contract_ref"]["sha256"] = "0" * 64
    with pytest.raises(NeuralCaptureRefusalError, match="No reviewed source contract is admitted"):
        admitted_neural_contract(tmp_path, manifest)
    assert list(tmp_path.iterdir()) == []


def test_partial_consumer_upgrade_refuses_the_old_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refuse a real package reload whose policy identity outlives the registry snapshot.

    Parameters
    ----------
    tmp_path
        Owned consumer package and authentic original acquisition declaration.
    monkeypatch
        Selects the operator descriptors adopted by the package copy.
    """
    original = _ROOT / "src/loop_timing_witness"
    installed = tmp_path / "consumer/loop_timing_witness"
    shutil.copytree(original, installed, ignore=shutil.ignore_patterns("__pycache__"))
    adopt_operator_descriptors(installed, tmp_path, monkeypatch)
    policy_module = installed / "neural_run_policy.py"
    expected_source = (original / "neural_run_policy.py").read_bytes()
    assert policy_module.read_bytes() == expected_source
    manifest = tmp_path / "run.json"
    manifest.write_bytes((_ROOT / "tests/data/neural-selected-original.run.json").read_bytes())
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            """
import hashlib, importlib, json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from loop_timing_witness.neural_event_stream import NeuralCaptureRefusalError
from loop_timing_witness.neural_run_manifest import load_neural_manifest
from loop_timing_witness.neural_run_policy import admitted_neural_contract
import loop_timing_witness.neural_run_selected_profile as selected

root = Path(sys.argv[2])
manifest = load_neural_manifest(root / 'run.json')
policy, _, _ = selected.image_neural_profile()
manifest['source_contract_ref'] |= {
    'sha256': hashlib.sha256(policy).hexdigest(), 'byte_length': len(policy)
}
(root / manifest['source_contract_ref']['path']).write_bytes(policy)
before = admitted_neural_contract(root, manifest)
reformatted = (json.dumps(json.loads(policy), sort_keys=True, indent=4) + chr(10)).encode()
old_digest = hashlib.sha256(policy).hexdigest()
new_digest = hashlib.sha256(reformatted).hexdigest()
assert old_digest != new_digest
selector = Path(selected.__file__)
selector_source = selector.read_text()
assert selector_source.count(old_digest) == 1
selector.write_text(selector_source.replace(old_digest, new_digest))
(selector.parent / 'data/neural-image-source-contract.json').write_bytes(reformatted)
importlib.reload(selected)
try:
    admitted_neural_contract(root, manifest)
except NeuralCaptureRefusalError as error:
    print(json.dumps({
        'original_digest': before.key[-1],
        'changed_digest': new_digest,
        'same_policy_values': json.loads(policy) == json.loads(reformatted),
        'refusal': str(error),
    }))
else:
    raise SystemExit(3)
""",
            str(installed.parent),
            str(tmp_path),
        ],
        stdin=subprocess.DEVNULL,
        env={**os.environ, IMAGE_ROOT_VARIABLE: _IMAGE},
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    observed = json.loads(result.stdout)
    assert observed["original_digest"] == _POLICY_SHA
    assert observed["changed_digest"] != _POLICY_SHA
    assert observed["same_policy_values"] is True
    assert observed["refusal"] == (
        "Selected neural source registration differs from its reviewed identity."
    )
    assert policy_module.read_bytes() == expected_source
