# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual pinned Icicle source derivation and refusal tests

"""Exercise the public derivation and pre-Libero gate on the real reference source."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "9c34320f91e8e8a144c7d87bf299527fc5f02081"
DERIVE = ROOT / "hardware/icicle/derive_reference.sh"
RUN = ROOT / "hardware/icicle/run_reference.sh"
VERIFY = ROOT / "tools/derive_icicle_reference.py"
PYTHON = ROOT / ".venv/bin/python"


@pytest.fixture(scope="module")
def derivation_race_interposer(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Compile a syscall shim for deterministic test-owned derivation races.

    Parameters
    ----------
    tmp_path_factory
        Exclusive native library output directory.

    Returns
    -------
    Path
        Native interposer that forwards all opens to the real kernel.
    """
    directory = tmp_path_factory.mktemp("icicle-derivation-race")
    library = directory / "race.so"
    result = subprocess.run(
        [
            "gcc",
            "-std=gnu11",
            "-shared",
            "-fPIC",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wconversion",
            "-Wshadow",
            "-Wstrict-prototypes",
            "-Wmissing-prototypes",
            "-o",
            str(library),
            "tests/native/icicle_derivation_race.c",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return library


def invoke(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run one real source-control or repository command without a shell.

    Parameters
    ----------
    arguments
        Executable and exact argument vector.

    Returns
    -------
    subprocess.CompletedProcess[str]
        Actual exit status and diagnostic streams.
    """
    return subprocess.run(arguments, capture_output=True, text=True, check=False)


@pytest.fixture(scope="module")
def official_reference(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Use a clean exact official checkout, fetching it when none was supplied.

    Parameters
    ----------
    tmp_path_factory
        Owned source checkout for the network-fetch path.

    Returns
    -------
    Path
        Clean pinned official Icicle reference source.
    """
    selected = os.environ.get("WITNESS_ICICLE_REFERENCE")
    if selected:
        source = Path(selected).resolve()
    else:
        source = tmp_path_factory.mktemp("icicle-upstream") / "source"
        for command in (
            ("git", "init", str(source)),
            (
                "git",
                "-C",
                str(source),
                "remote",
                "add",
                "origin",
                "https://github.com/polarfire-soc/icicle-kit-reference-design.git",
            ),
            ("git", "-C", str(source), "fetch", "--depth", "1", "origin", COMMIT),
            ("git", "-C", str(source), "checkout", "--detach", COMMIT),
        ):
            result = invoke(*command)
            assert result.returncode == 0, result.stdout + result.stderr
    assert invoke("git", "-C", str(source), "rev-parse", "HEAD").stdout.strip() == COMMIT
    assert not invoke("git", "-C", str(source), "status", "--porcelain").stdout
    return source


@pytest.fixture(scope="module")
def derived_tree(official_reference: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Prepare one real derived tree through the executable public entry point.

    Parameters
    ----------
    official_reference
        Clean pinned upstream checkout.
    tmp_path_factory
        New output path on the same disk as the canonical repository.

    Returns
    -------
    Path
        Source-verified reference tree with copied production RTL.
    """
    output = tmp_path_factory.mktemp("icicle-derivation") / "derived"
    assert output.parent.stat().st_dev == ROOT.stat().st_dev, (
        "run this test with --basetemp on the canonical working disk"
    )
    result = invoke(str(DERIVE), str(official_reference), str(output))
    assert result.returncode == 0, result.stdout + result.stderr
    return output


def test_public_derivation_and_vendor_preflight(derived_tree: Path) -> None:
    """Bind actual upstream Tcl and all current RTL before requesting Libero.

    Parameters
    ----------
    derived_tree
        Real source produced by the public derivation command.
    """
    result = invoke(str(PYTHON), str(VERIFY), "--verify", str(derived_tree))
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((derived_tree / "witness_derivation.json").read_text())
    assert manifest["source_commit"] == COMMIT
    assert manifest["witness_rtl_dir"] == "witness_rtl"
    for name, digest in manifest["witness_rtl_sha256"].items():
        assert (
            hashlib.sha256((derived_tree / "witness_rtl" / name).read_bytes()).hexdigest() == digest
        )
    assert set(manifest["witness_rtl_sha256"]) == {
        path.name for path in (ROOT / "rtl").glob("*.sv")
    }
    missing_libero = derived_tree / "not-installed-libero"
    for device in ("MPFS250T", "MPFS250T_ES"):
        refusal = invoke(str(RUN), str(derived_tree), str(missing_libero), device)
        assert refusal.returncode == 2
        assert "an executable Libero binary is required" in refusal.stderr
    bad_device = invoke(str(RUN), str(derived_tree), str(missing_libero), "WRONG_DEVICE")
    assert bad_device.returncode == 2
    assert "device must match" in bad_device.stderr


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        ("witness_rtl/icicle_witness.sv", "derived RTL changed"),
        ("script_support/components/MSS_WRAPPER.tcl", "derived vendor Tcl changed"),
        (
            "script_support/constraints/fic_clocks.sdc",
            "derived reference remainder differs from pinned commit",
        ),
        (
            "script_support/additional_configurations/LOOP_TIMING_WITNESS.tcl",
            "derived witness connection Tcl changed",
        ),
        ("witness_derivation.json", "derived manifest differs"),
    ],
)
def test_public_verifier_refuses_changed_real_inputs(
    derived_tree: Path, tmp_path: Path, relative: str, expected: str
) -> None:
    """Refuse changed bytes in each source class before a vendor tool exists.

    Parameters
    ----------
    derived_tree
        Actual successful source derivation.
    tmp_path
        Test-owned copy of the complete real source.
    relative
        Original source file to change in the owned copy.
    expected
        Path-specific refusal.
    """
    changed = tmp_path / "changed"
    shutil.copytree(derived_tree, changed, symlinks=True)
    path = changed / relative
    if relative == "witness_derivation.json":
        manifest = json.loads(path.read_text())
        manifest["source_commit"] = "changed"
        path.write_text(json.dumps(manifest), encoding="utf-8")
    else:
        path.write_bytes(path.read_bytes() + b"\n# changed after derivation\n")
    refusal = invoke(str(PYTHON), str(VERIFY), "--verify", str(changed))
    assert refusal.returncode != 0
    assert expected in refusal.stderr
    runner = invoke(str(RUN), str(changed), str(tmp_path / "not-installed-libero"), "MPFS250T")
    assert runner.returncode != 0
    assert expected in runner.stderr
    assert not (changed / "BASE_DESIGN_9C34320F").exists()


def test_public_verifier_refuses_extra_reference_input(derived_tree: Path, tmp_path: Path) -> None:
    """Refuse an unexpected file that a vendor glob could import.

    Parameters
    ----------
    derived_tree
        Actual successful source derivation.
    tmp_path
        Test-owned derived tree and extra file.
    """
    changed = tmp_path / "changed"
    shutil.copytree(derived_tree, changed, symlinks=True)
    extra = changed / "script_support/constraints/extra.sdc"
    extra.write_text("# unexpected vendor input\n", encoding="utf-8")
    refusal = invoke(str(PYTHON), str(VERIFY), "--verify", str(changed))
    assert refusal.returncode != 0
    assert "derived reference remainder differs from pinned commit" in refusal.stderr


def test_public_verifier_refuses_aliased_reference_constraint(
    derived_tree: Path, tmp_path: Path
) -> None:
    """Reject a symlinked SDC even when it resolves to unchanged bytes.

    Parameters
    ----------
    derived_tree
        Actual successful source derivation.
    tmp_path
        Test-owned derived tree with a symlinked original constraint.
    """
    changed = tmp_path / "aliased"
    shutil.copytree(derived_tree, changed, symlinks=True)
    constraint = changed / "script_support/constraints/fic_clocks.sdc"
    original = constraint.with_name("fic_clocks.original.sdc")
    constraint.rename(original)
    constraint.symlink_to(original.name)
    refusal = invoke(str(PYTHON), str(VERIFY), "--verify", str(changed))
    assert refusal.returncode != 0
    assert "reference source is not a regular file" in refusal.stderr


def test_public_verifier_refuses_live_rtl_alias(derived_tree: Path, tmp_path: Path) -> None:
    """Refuse a symlink that would replace the frozen RTL snapshot with live RTL.

    Parameters
    ----------
    derived_tree
        Actual successful source derivation.
    tmp_path
        Test-owned copy with only its snapshot directory replaced.
    """
    changed = tmp_path / "aliased"
    shutil.copytree(derived_tree, changed, symlinks=True)
    snapshot = changed / "witness_rtl"
    shutil.rmtree(snapshot)
    snapshot.symlink_to(ROOT / "rtl", target_is_directory=True)
    refusal = invoke(str(PYTHON), str(VERIFY), "--verify", str(changed))
    assert refusal.returncode != 0
    assert "derived RTL source set changed" in refusal.stderr


def test_public_verifier_refuses_extra_rtl_snapshot_file(
    derived_tree: Path, tmp_path: Path
) -> None:
    """Reject unrecorded files within the derived RTL snapshot.

    Parameters
    ----------
    derived_tree
        Actual successful source derivation.
    tmp_path
        Test-owned copy with one extra snapshot file.
    """
    changed = tmp_path / "extra-rtl"
    shutil.copytree(derived_tree, changed, symlinks=True)
    (changed / "witness_rtl/icicle_witness.sv.bak").write_text(
        "unrecorded RTL snapshot input\n", encoding="utf-8"
    )
    refusal = invoke(str(PYTHON), str(VERIFY), "--verify", str(changed))
    assert refusal.returncode != 0
    assert "derived RTL source set changed" in refusal.stderr


@pytest.mark.parametrize("replacement", ["symlink", "directory"])
def test_public_verifier_refuses_non_file_rtl_snapshot(
    derived_tree: Path, tmp_path: Path, replacement: str
) -> None:
    """Reject a redirected or non-regular RTL source before vendor generation.

    Parameters
    ----------
    derived_tree
        Actual successful source derivation.
    tmp_path
        Test-owned derived tree and replacement object.
    replacement
        Filesystem object substituted for one original snapshot file.
    """
    changed = tmp_path / "non-file-rtl"
    shutil.copytree(derived_tree, changed, symlinks=True)
    source = changed / "witness_rtl/icicle_witness.sv"
    original = tmp_path / "original-icicle-witness.sv"
    source.rename(original)
    if replacement == "symlink":
        source.symlink_to(original)
    else:
        source.mkdir()
    refusal = invoke(str(PYTHON), str(VERIFY), "--verify", str(changed))
    assert refusal.returncode != 0
    assert "derived RTL changed: icicle_witness.sv" in refusal.stderr


def test_public_verifier_refuses_manifest_alias(derived_tree: Path, tmp_path: Path) -> None:
    """Reject a manifest alias even when it resolves to unchanged bytes.

    Parameters
    ----------
    derived_tree
        Actual successful source derivation.
    tmp_path
        Test-owned copy with a manifest symlink.
    """
    changed = tmp_path / "aliased"
    shutil.copytree(derived_tree, changed, symlinks=True)
    manifest = changed / "witness_derivation.json"
    original = changed / "original-witness-derivation.json"
    manifest.rename(original)
    manifest.symlink_to(original.name)
    refusal = invoke(str(PYTHON), str(VERIFY), "--verify", str(changed))
    assert refusal.returncode != 0
    assert "derived manifest must be a local file" in refusal.stderr


def test_public_verifier_refuses_repeated_manifest_member(
    derived_tree: Path, tmp_path: Path
) -> None:
    """Reject an ambiguous receipt even when its final repeated value matches.

    Parameters
    ----------
    derived_tree
        Actual successful source derivation.
    tmp_path
        Test-owned derived tree with one repeated receipt member.
    """
    changed = tmp_path / "repeated-manifest-member"
    shutil.copytree(derived_tree, changed, symlinks=True)
    manifest = changed / "witness_derivation.json"
    original = manifest.read_text(encoding="utf-8")
    marker = '  "source_commit": '
    assert original.count(marker) == 1
    manifest.write_text(
        original.replace(marker, '  "source_commit": "wrong",\n' + marker, 1),
        encoding="utf-8",
    )
    refusal = invoke(str(PYTHON), str(VERIFY), "--verify", str(changed))
    assert refusal.returncode != 0
    assert "duplicate JSON key: source_commit" in refusal.stderr


@pytest.mark.parametrize(
    ("device", "project_name"),
    [
        ("MPFS250T", "BASE_DESIGN_9C34320F"),
        ("MPFS250T_ES", "BASE_DESIGN_ES_9C34320F"),
    ],
)
def test_vendor_runner_preserves_existing_project(
    derived_tree: Path, tmp_path: Path, device: str, project_name: str
) -> None:
    """Refuse either device's existing generated project before invoking Libero.

    Parameters
    ----------
    derived_tree
        Actual successful source derivation.
    tmp_path
        Test-owned tree and project sentinel.
    device
        Explicit selected silicon variant.
    project_name
        Project path selected for that variant.
    """
    changed = tmp_path / "derived"
    shutil.copytree(derived_tree, changed, symlinks=True)
    project = changed / project_name
    project.mkdir()
    sentinel = project / "keep"
    sentinel.write_text("unchanged", encoding="utf-8")
    refusal = invoke(str(RUN), str(changed), str(tmp_path / "not-installed-libero"), device)
    assert refusal.returncode == 2
    assert "generated project already exists" in refusal.stderr
    assert sentinel.read_text(encoding="utf-8") == "unchanged"


def test_public_derivation_refuses_dirty_official_source(
    official_reference: Path, tmp_path: Path
) -> None:
    """Refuse a locally edited vendor source before creating an output tree.

    Parameters
    ----------
    official_reference
        Original clean pinned checkout, copied before mutation.
    tmp_path
        Test-owned source and output paths.
    """
    source = tmp_path / "dirty-reference"
    shutil.copytree(official_reference, source, symlinks=True)
    vendor = source / "script_support/components/MSS_WRAPPER.tcl"
    vendor.write_bytes(vendor.read_bytes() + b"\n# changed in owned test source\n")
    output = tmp_path / "must-not-exist"
    refusal = invoke(str(DERIVE), str(source), str(output))
    assert refusal.returncode == 2
    assert "official reference checkout is not clean" in refusal.stderr
    assert not output.exists()


def test_public_python_derivation_refuses_changed_reference(
    official_reference: Path, tmp_path: Path
) -> None:
    """Reject changed official bytes at the Python CLI boundary.

    Parameters
    ----------
    official_reference
        Original clean pinned checkout, copied before mutation.
    tmp_path
        Test-owned source and output paths.
    """
    source = tmp_path / "changed-reference"
    shutil.copytree(official_reference, source, symlinks=True)
    vendor = source / "script_support/components/MSS_WRAPPER.tcl"
    vendor.write_bytes(vendor.read_bytes() + b"\n# changed in owned test source\n")
    output = tmp_path / "must-not-exist"
    refusal = invoke(str(PYTHON), str(VERIFY), str(source), str(output))
    assert refusal.returncode != 0
    assert "reference source mismatch: script_support/components/MSS_WRAPPER.tcl" in refusal.stderr
    assert not output.exists()


def test_public_python_derivation_refuses_changed_reference_constraint(
    official_reference: Path, tmp_path: Path
) -> None:
    """Reject changed official SDC bytes before creating a derived output.

    Parameters
    ----------
    official_reference
        Original clean pinned checkout, copied before mutation.
    tmp_path
        Test-owned source and output paths.
    """
    source = tmp_path / "changed-reference"
    shutil.copytree(official_reference, source, symlinks=True)
    constraint = source / "script_support/constraints/fic_clocks.sdc"
    constraint.write_bytes(constraint.read_bytes() + b"\n# changed in owned test source\n")
    output = tmp_path / "must-not-exist"
    refusal = invoke(str(PYTHON), str(VERIFY), str(source), str(output))
    assert refusal.returncode != 0
    assert "reference source tree differs from pinned commit" in refusal.stderr
    assert not output.exists()


def test_public_python_derivation_refuses_source_directory_alias(
    official_reference: Path, tmp_path: Path
) -> None:
    """Reject a redirected official constraint directory before copying input.

    Parameters
    ----------
    official_reference
        Original clean pinned checkout, copied before mutation.
    tmp_path
        Test-owned source and output paths.
    """
    source = tmp_path / "aliased-reference"
    shutil.copytree(official_reference, source, symlinks=True)
    constraints = source / "script_support/constraints"
    original = constraints.with_name("constraints-original")
    constraints.rename(original)
    constraints.symlink_to(original.name, target_is_directory=True)
    output = tmp_path / "must-not-exist"
    refusal = invoke(str(PYTHON), str(VERIFY), str(source), str(output))
    assert refusal.returncode != 0
    assert "reference source is not a regular file" in refusal.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    "race",
    [
        (
            "/output/script_support/components/MSS_WRAPPER.tcl",
            1,
            "expected one occurrence",
        ),
        (
            "/output/script_support/components/MSS_WRAPPER.tcl",
            2,
            "derived source mismatch: script_support/components/MSS_WRAPPER.tcl",
        ),
        (
            "/output/witness_rtl/icicle_witness.sv",
            1,
            "RTL source changed while deriving: icicle_witness.sv",
        ),
        (
            "/output/LICENSE.md",
            1,
            "derived reference remainder differs from pinned commit",
        ),
    ],
    ids=["anchor", "edited-source", "rtl-snapshot", "reference-remainder"],
)
def test_public_derivation_refuses_staging_input_race(
    official_reference: Path,
    tmp_path: Path,
    derivation_race_interposer: Path,
    race: tuple[str, int, str],
) -> None:
    """Refuse real staging-byte changes at each guarded derivation boundary.

    Parameters
    ----------
    official_reference
        Clean pinned official source copied only into temporary staging.
    tmp_path
        Exclusive output and syscall receipt paths.
    derivation_race_interposer
        Native open forwarder that changes only the selected staging file.
    race
        Staging suffix, required write count and production refusal text.
    """
    suffix, writes, expected = race
    output = tmp_path / "must-not-publish"
    marker = tmp_path / "race-observed"
    environment = {
        **os.environ,
        "LD_PRELOAD": str(derivation_race_interposer),
        "WITNESS_ICICLE_RACE_SUFFIX": suffix,
        "WITNESS_ICICLE_RACE_WRITES": str(writes),
        "WITNESS_ICICLE_RACE_MARKER": str(marker),
    }
    refusal = subprocess.run(
        [str(PYTHON), str(VERIFY), str(official_reference), str(output)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert refusal.returncode != 0
    assert marker.is_file()
    assert expected in refusal.stderr
    assert not output.exists()


def test_public_derivation_preserves_competing_destination(
    official_reference: Path, tmp_path: Path, derivation_race_interposer: Path
) -> None:
    """Preserve a destination created by another owner immediately before publication.

    Parameters
    ----------
    official_reference
        Clean pinned official source used by the normal public derivation CLI.
    tmp_path
        Exclusive competing destination and syscall receipt paths.
    derivation_race_interposer
        Native open forwarder that creates the competing output at manifest write.
    """
    output = tmp_path / "competing-output"
    marker = tmp_path / "race-observed"
    environment = {
        **os.environ,
        "LD_PRELOAD": str(derivation_race_interposer),
        "WITNESS_ICICLE_RACE_SUFFIX": "/output/witness_derivation.json",
        "WITNESS_ICICLE_RACE_DESTINATION": str(output),
        "WITNESS_ICICLE_RACE_MARKER": str(marker),
    }
    refusal = subprocess.run(
        [str(PYTHON), str(VERIFY), str(official_reference), str(output)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert refusal.returncode != 0
    assert marker.is_file()
    assert "FileExistsError" in refusal.stderr
    assert sorted(path.name for path in output.iterdir()) == ["keep"]
    assert (output / "keep").read_text(encoding="ascii") == "preserved\n"


def test_derivation_module_load_has_no_cli_side_effects() -> None:
    """Load the derivation module without accidentally starting either CLI mode."""
    result = invoke(
        str(PYTHON),
        "-c",
        (
            "import runpy, sys; "
            "sys.path.insert(0, sys.argv[1]); "
            "runpy.run_path(sys.argv[2], run_name='icicle_derivation_import')"
        ),
        str(ROOT / "tools"),
        str(VERIFY),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not result.stdout
    assert not result.stderr


def test_public_derivation_refuses_ignored_reference_input(
    official_reference: Path, tmp_path: Path
) -> None:
    """Catch ignored source files that Git's clean-status check cannot see.

    Parameters
    ----------
    official_reference
        Original clean pinned checkout, copied before the ignored addition.
    tmp_path
        Test-owned source and output paths.
    """
    source = tmp_path / "ignored-reference"
    shutil.copytree(official_reference, source, symlinks=True)
    ignored = source / "script_support/Unsupported_Cores_List.txt"
    ignored.write_text("unexpected vendor input\n", encoding="utf-8")
    assert not invoke("git", "-C", str(source), "status", "--porcelain").stdout
    output = tmp_path / "must-not-exist"
    refusal = invoke(str(DERIVE), str(source), str(output))
    assert refusal.returncode != 0
    assert "reference source tree differs from pinned commit" in refusal.stderr
    assert not output.exists()


def test_public_derivation_preserves_existing_output(
    official_reference: Path, tmp_path: Path
) -> None:
    """Refuse an existing destination without disturbing its contents.

    Parameters
    ----------
    official_reference
        Clean pinned upstream checkout.
    tmp_path
        Test-owned output path and sentinel.
    """
    output = tmp_path / "existing-output"
    output.mkdir()
    sentinel = output / "keep"
    sentinel.write_text("unchanged", encoding="utf-8")
    refusal = invoke(str(DERIVE), str(official_reference), str(output))
    assert refusal.returncode == 2
    assert "destination parent must exist and destination must be new" in refusal.stderr
    assert sentinel.read_text(encoding="utf-8") == "unchanged"


def test_public_python_derivation_preserves_existing_output(
    official_reference: Path, tmp_path: Path
) -> None:
    """Preserve an existing destination when the Python CLI is invoked directly.

    Parameters
    ----------
    official_reference
        Clean pinned upstream checkout.
    tmp_path
        Test-owned output path and sentinel.
    """
    output = tmp_path / "existing-output"
    output.mkdir()
    sentinel = output / "keep"
    sentinel.write_text("unchanged", encoding="utf-8")
    refusal = invoke(str(PYTHON), str(VERIFY), str(official_reference), str(output))
    assert refusal.returncode != 0
    assert "FileExistsError" in refusal.stderr
    assert sentinel.read_text(encoding="utf-8") == "unchanged"


@pytest.mark.parametrize("command", [DERIVE, VERIFY])
def test_public_derivation_refuses_dangling_destination_alias(
    official_reference: Path, tmp_path: Path, command: Path
) -> None:
    """Never redirect a requested new output through a dangling symlink.

    Parameters
    ----------
    official_reference
        Clean pinned upstream checkout.
    tmp_path
        Test-owned alias and target paths.
    command
        Public shell or Python derivation command.
    """
    target = tmp_path / "unrequested-target"
    alias = tmp_path / "requested-output"
    alias.symlink_to(target)
    arguments = (str(PYTHON), str(command)) if command == VERIFY else (str(command),)
    refusal = invoke(*arguments, str(official_reference), str(alias))
    assert refusal.returncode != 0
    assert not target.exists()
    assert alias.is_symlink()


def test_public_python_cli_refuses_ambiguous_arguments(derived_tree: Path) -> None:
    """Keep verification and derivation as separate unambiguous CLI modes.

    Parameters
    ----------
    derived_tree
        Actual successful source derivation.
    """
    missing_output = invoke(str(PYTHON), str(VERIFY), str(derived_tree))
    assert missing_output.returncode == 2
    assert "derivation requires source and new destination" in missing_output.stderr
    extra_output = invoke(str(PYTHON), str(VERIFY), "--verify", str(derived_tree), "extra")
    assert extra_output.returncode == 2
    assert "--verify takes only the derived tree" in extra_output.stderr


def test_public_shell_derivation_propagates_actual_git_status_failure(
    official_reference: Path, tmp_path: Path
) -> None:
    """Stop on a real status error after successful pinned-commit verification.

    Parameters
    ----------
    official_reference
        Unmodified official pinned reference checkout.
    tmp_path
        Owned source copy and unopened derivation output.
    """
    source = tmp_path / "bare-reference"
    shutil.copytree(official_reference, source, symlinks=True)
    configured = invoke("git", "-C", str(source), "config", "core.bare", "true")
    assert configured.returncode == 0, configured.stderr
    commit = invoke("git", "-C", str(source), "rev-parse", "HEAD")
    assert commit.returncode == 0
    assert commit.stdout.strip() == COMMIT
    failed_status = invoke("git", "-C", str(source), "status", "--porcelain")
    assert failed_status.returncode == 128
    assert not failed_status.stdout
    output = tmp_path / "derived"
    result = invoke(str(DERIVE), str(source), str(output))
    assert result.returncode == failed_status.returncode
    assert failed_status.stderr.strip() in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("command", [DERIVE, RUN], ids=["derive", "run"])
def test_public_shell_entrypoint_propagates_actual_missing_repository_failure(
    tmp_path: Path, command: Path
) -> None:
    """A real non-Git directory cannot be accepted as verified reference source.

    Parameters
    ----------
    tmp_path
        Existing owned directory with no Git metadata.
    command
        Actual public derivation or pre-Libero executable.
    """
    source = tmp_path / "not-a-repository"
    source.mkdir()
    arguments = [str(source), str(tmp_path / "unopened-output")]
    if command == RUN:
        arguments.append("MPFS250T")
    result = invoke(str(command), *arguments)
    assert result.returncode == 128
    assert "not a git repository" in result.stderr
    assert not (tmp_path / "unopened-output").exists()


@pytest.mark.parametrize(
    ("command", "argument_count"),
    [
        (DERIVE, 0),
        (DERIVE, 1),
        (DERIVE, 3),
        (DERIVE, 4),
        (RUN, 0),
        (RUN, 1),
        (RUN, 2),
        (RUN, 4),
        (RUN, 5),
    ],
)
def test_public_shell_entrypoint_refuses_wrong_argument_count(
    command: Path, argument_count: int
) -> None:
    """Reject ambiguous shell modes before resolving any source or output path.

    Parameters
    ----------
    command
        Actual public derivation or vendor-runner entry point.
    argument_count
        Missing or excess arguments for that command's fixed interface.
    """
    result = invoke(str(command), *(["unused"] * argument_count))
    assert result.returncode == 2
    assert result.stderr.startswith("usage: ")
    assert not result.stdout


@pytest.mark.parametrize("parent_kind", ["missing", "regular-file"])
def test_public_shell_derivation_refuses_unusable_destination_parent(
    official_reference: Path, tmp_path: Path, parent_kind: str
) -> None:
    """Refuse unavailable parent directories while preserving existing bytes.

    Parameters
    ----------
    official_reference
        Clean pinned official checkout used as the real source.
    tmp_path
        Test-owned invalid destination parent.
    parent_kind
        Absent parent or an existing file in place of a directory.
    """
    parent = tmp_path / "unusable-parent"
    if parent_kind == "regular-file":
        parent.write_bytes(b"preserved parent bytes\n")
    output = parent / "unopened-output"
    result = invoke(str(DERIVE), str(official_reference), str(output))
    assert result.returncode == 2
    assert "destination parent must exist and destination must be new" in result.stderr
    assert not result.stdout
    assert not output.exists()
    if parent_kind == "regular-file":
        assert parent.read_bytes() == b"preserved parent bytes\n"
    else:
        assert not parent.exists()


def test_public_shell_derivation_preserves_existing_output_file(
    official_reference: Path, tmp_path: Path
) -> None:
    """Preserve a regular output file as well as the existing directory case.

    Parameters
    ----------
    official_reference
        Actual clean pinned official source.
    tmp_path
        Exclusive output file and original byte sentinel.
    """
    output = tmp_path / "existing-output-file"
    original = b"preserved output bytes\n"
    output.write_bytes(original)
    result = invoke(str(DERIVE), str(official_reference), str(output))
    assert result.returncode == 2
    assert "destination parent must exist and destination must be new" in result.stderr
    assert not result.stdout
    assert output.read_bytes() == original


def test_public_shell_derivation_refuses_destination_within_reference(
    official_reference: Path, tmp_path: Path
) -> None:
    """Keep generated source outside the official checkout even with spaced paths.

    Parameters
    ----------
    official_reference
        Pinned vendor checkout copied before the production command.
    tmp_path
        Owned checkout whose path includes spaces.
    """
    source = tmp_path / "official source with spaces"
    shutil.copytree(official_reference, source, symlinks=True)
    output = source / "unopened derived tree"
    result = invoke(str(DERIVE), str(source), str(output))
    assert result.returncode == 2
    assert "destination must be outside the official source checkout" in result.stderr
    assert not result.stdout
    assert not output.exists()
    assert not invoke("git", "-C", str(source), "status", "--porcelain").stdout


@pytest.mark.parametrize("command", [DERIVE, RUN], ids=["derive", "run"])
def test_public_shell_entrypoint_refuses_actual_other_filesystem(
    official_reference: Path, tmp_path: Path, command: Path
) -> None:
    """Reject the real procfs device before any output or vendor invocation.

    Parameters
    ----------
    official_reference
        Original pinned source used by the derivation entry point.
    tmp_path
        Exclusive case identity and unopened local output.
    command
        Actual derivation or vendor-runner entry point.
    """
    other_disk = Path("/proc")
    assert other_disk.stat().st_dev != ROOT.stat().st_dev
    output = tmp_path / "unopened-output"
    arguments: tuple[str, ...]
    if command == DERIVE:
        arguments = (str(official_reference), str(other_disk / output.name))
        expected = "destination must be on the canonical Samsung working disk"
    else:
        arguments = (str(other_disk), str(output), "MPFS250T")
        expected = "derived project must run on the canonical Samsung working disk"
    result = invoke(str(command), *arguments)
    assert result.returncode == 2
    assert expected in result.stderr
    assert not result.stdout
    assert not output.exists()


def test_public_vendor_runner_refuses_regular_file_tree(tmp_path: Path) -> None:
    """Reject a regular file before consulting Git or the vendor executable.

    Parameters
    ----------
    tmp_path
        Actual owned file supplied at the derived-tree boundary.
    """
    source = tmp_path / "not-a-directory"
    original = b"unchanged input bytes\n"
    source.write_bytes(original)
    output = tmp_path / "unopened-output"
    result = invoke(str(RUN), str(source), str(output), "MPFS250T")
    assert result.returncode == 2
    assert "derived tree is required" in result.stderr
    assert not result.stdout
    assert source.read_bytes() == original
    assert not output.exists()


@pytest.mark.parametrize("command", [DERIVE, RUN], ids=["derive", "run"])
def test_public_shell_entrypoint_refuses_unpinned_actual_commit(
    official_reference: Path, tmp_path: Path, command: Path
) -> None:
    """Reject a clean real Git commit whose vendor file bytes are unchanged.

    Parameters
    ----------
    official_reference
        Pinned vendor source copied before the local empty commit.
    tmp_path
        Exclusive repository and unopened output.
    command
        Actual derivation or vendor-runner command.
    """
    source = tmp_path / "unpinned-reference"
    shutil.copytree(official_reference, source, symlinks=True)
    committed = invoke(
        "git",
        "-C",
        str(source),
        "-c",
        "user.name=Witness Test",
        "-c",
        "user.email=witness-test@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "-c",
        "core.hooksPath=/dev/null",
        "commit",
        "--allow-empty",
        "--no-gpg-sign",
        "-m",
        "Exercise refusal of an unpinned reference commit",
    )
    assert committed.returncode == 0, committed.stdout + committed.stderr
    commit = invoke("git", "-C", str(source), "rev-parse", "HEAD")
    assert commit.returncode == 0
    assert commit.stdout.strip() != COMMIT
    assert not invoke("git", "-C", str(source), "status", "--porcelain").stdout
    vendor = Path("script_support/components/MSS_WRAPPER.tcl")
    assert (source / vendor).read_bytes() == (official_reference / vendor).read_bytes()
    output = tmp_path / "unopened-output"
    arguments = [str(source), str(output)]
    if command == RUN:
        arguments.append("MPFS250T")
        expected = "derived tree has the wrong official reference commit"
    else:
        expected = "official reference commit differs from the pinned source"
    result = invoke(str(command), *arguments)
    assert result.returncode == 2
    assert expected in result.stderr
    assert not result.stdout
    assert not output.exists()
