# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — pinned Icicle reference source derivation

"""Derive the witness Libero source from one verified official reference commit."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from manifest_io import load_json_object

REFERENCE_COMMIT = "9c34320f91e8e8a144c7d87bf299527fc5f02081"
SOURCE_TREE_SHA256 = "1f720db72fd65fa25a93ffcf6a445b581926a02a6a8f64b6b8d9d415088c109b"
REFERENCE_REMAINDER_SHA256 = "dd589c9bbbd526ee37aaecd3ccfef7e841c8fa5990c313b3d4885eacd58665ca"
SOURCE_HASHES = {
    "MPFS_ICICLE_KIT_REFERENCE_DESIGN.tcl": (
        "28aa2cc9263c8e8bf410ee2a31ee7fc6def82e112c3badb34f2186c51cc06b9d"
    ),
    "script_support/components/CLOCKS_AND_RESETS.tcl": (
        "f9a8ddf551e9b93eab4de55f0a5cac763ad69ebb234216d1f780b85263d44c56"
    ),
    "script_support/components/FIC0_INITIATOR.tcl": (
        "30add476ef4d02e0b03245ab1730395c4576abcf985f35cd483ca89de90d8b99"
    ),
    "script_support/components/MSS_WRAPPER.tcl": (
        "f396a6fe58cf4059a447bbbe19cff21db7e3019206a6c78407fb508f24b61475"
    ),
    "script_support/components/PF_CCC_C0.tcl": (
        "fd5403d96639bdce38d0236f7948a595ccda6a3e0fc84889b29f63a148cca17b"
    ),
}
DERIVED_HASHES = {
    "MPFS_ICICLE_KIT_REFERENCE_DESIGN.tcl": (
        "7ee70f5e29d6bcdc4c1a2d418a990ab814df0688d6e021bcd8962bdd7e43ee77"
    ),
    "script_support/components/CLOCKS_AND_RESETS.tcl": (
        "ccf5a9656c56bad8adf937174df7263ea396f379174544367be05a63b53f18f7"
    ),
    "script_support/components/FIC0_INITIATOR.tcl": (
        "2ac5577bfdb84f1ec262011076fb20a9ed727de2d562f85bc0e2e8780ef0610d"
    ),
    "script_support/components/MSS_WRAPPER.tcl": (
        "ade0d8a635e1f70c8aa5276a77b50b4aad00abafb28456a975ff7b67cc77eb2e"
    ),
    "script_support/components/PF_CCC_C0.tcl": (
        "6efd2d48b6431ca75715b75f2891f0d4e42aa51368e95e26ed9a83fa67c16b98"
    ),
}
REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
WITNESS_SCRIPT = REPOSITORY_ROOT / "hardware/icicle/LOOP_TIMING_WITNESS.tcl"
DERIVED_SCRIPT = "script_support/additional_configurations/LOOP_TIMING_WITNESS.tcl"
RTL_SNAPSHOT = "witness_rtl"
SD_NAME = "$" + "{sd_name}"


def sha256(path: Path) -> str:
    """Return the digest of one source file.

    Parameters
    ----------
    path
        Existing source file.

    Returns
    -------
    str
        Lowercase SHA-256 hexadecimal digest.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_sha256(
    root: Path,
    excluded_files: frozenset[str] = frozenset(),
    excluded_dirs: frozenset[str] = frozenset(),
) -> str:
    """Hash every non-Git file path and its bytes in one reference tree.

    Parameters
    ----------
    root
        Official source or derived tree.
    excluded_files
        Files checked independently after the five vendor edits and witness additions.
    excluded_dirs
        Root-level witness snapshot directories checked independently.

    Returns
    -------
    str
        SHA-256 of the sorted path-and-content digest inventory.

    Raises
    ------
    ValueError
        A source path is a symlink or not a regular file.
    """
    entries: list[tuple[str, str]] = []
    for directory, names, filenames in root.walk():
        names[:] = [
            name
            for name in names
            if not (directory == root and (name == ".git" or name in excluded_dirs))
        ]
        for name in filenames:
            if directory == root and name in excluded_dirs:
                continue
            path = directory / name
            relative = path.relative_to(root).as_posix()
            if relative in excluded_files:
                continue
            if path.is_symlink() or not path.is_file():
                msg = f"reference source is not a regular file: {relative}"
                raise ValueError(msg)
            entries.append((relative, sha256(path)))
    payload = json.dumps(sorted(entries), ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def replace_once(source: str, old: str, new: str, path: str) -> str:
    """Apply one source-bound change and refuse a missing or ambiguous anchor.

    Parameters
    ----------
    source
        Current file content.
    old
        Exact upstream anchor.
    new
        Derived replacement.
    path
        Relative source path for an actionable refusal.

    Returns
    -------
    str
        Updated content.

    Raises
    ------
    ValueError
        The pinned source no longer contains one exact anchor.
    """
    if source.count(old) != 1:
        msg = f"{path}: expected one occurrence of {old!r}"
        raise ValueError(msg)
    return source.replace(old, new)


def edits() -> dict[str, tuple[tuple[str, str], ...]]:
    """Return the exact transformations for the pinned reference source.

    Returns
    -------
    dict[str, tuple[tuple[str, str], ...]]
        Ordered old/new replacements per upstream file.
    """
    clock_port = (
        f"sd_create_scalar_port -sd_name {SD_NAME} "
        "-port_name {WITNESS_CAPTURE_CLK} -port_direction {OUT}\n"
    )
    clock_pin = (
        f"sd_connect_pins -sd_name {SD_NAME} -pin_names "
        '{"CCC_FIC_x_CLK:OUT0_FABCLK_1" "WITNESS_CAPTURE_CLK" }\n'
    )
    irq_port = (
        f"sd_create_scalar_port -sd_name {SD_NAME} "
        "-port_name {MSS_INT_F2M_11} -port_direction {IN}\n"
    )
    irq_slice = (
        f"sd_create_pin_slices -sd_name {SD_NAME} -pin_name "
        "{ICICLE_MSS:MSS_INT_F2M} -pin_slices {[58:12]}"
    )
    irq_pin = (
        f"sd_connect_pins -sd_name {SD_NAME} -pin_names "
        '{"ICICLE_MSS:MSS_INT_F2M[11:11]" "MSS_INT_F2M_11" }\n'
    )
    return {
        "MPFS_ICICLE_KIT_REFERENCE_DESIGN.tcl": (
            (
                "-memory_map_drc_change_error_to_warning 1",
                "-memory_map_drc_change_error_to_warning 0",
            ),
            (
                "-bus_interface_data_width_drc_change_error_to_warning 1",
                "-bus_interface_data_width_drc_change_error_to_warning 0",
            ),
            (
                "-bus_interface_id_width_drc_change_error_to_warning 1 ",
                "-bus_interface_id_width_drc_change_error_to_warning 0",
            ),
            (
                "    if {[info exists MSS_BAREMETAL]} {",
                (
                    "    safe_source script_support/additional_configurations/"
                    "LOOP_TIMING_WITNESS.tcl\n\n"
                    "    if {[info exists MSS_BAREMETAL]} {"
                ),
            ),
        ),
        "script_support/components/CLOCKS_AND_RESETS.tcl": (
            (
                f"sd_create_scalar_port -sd_name {SD_NAME} -port_name {{FIC_1_CLK}}",
                clock_port + f"sd_create_scalar_port -sd_name {SD_NAME} -port_name {{FIC_1_CLK}}",
            ),
            (
                f'sd_connect_pins -sd_name {SD_NAME} -pin_names {{"CCC_FIC_x_CLK:OUT1_FABCLK_0"',
                clock_pin + f"sd_connect_pins -sd_name {SD_NAME} -pin_names "
                '{"CCC_FIC_x_CLK:OUT1_FABCLK_0"',
            ),
        ),
        "script_support/components/FIC0_INITIATOR.tcl": (
            ('"NUM_SLAVES:2"', '"NUM_SLAVES:3"'),
            ('"SLAVE2_END_ADDR:0x60020470"', '"SLAVE2_END_ADDR:0x600200ff"'),
        ),
        "script_support/components/MSS_WRAPPER.tcl": (
            (
                f"sd_create_scalar_port -sd_name {SD_NAME} -port_name {{MSS_INT_F2M_3}}",
                irq_port + f"sd_create_scalar_port -sd_name {SD_NAME} -port_name {{MSS_INT_F2M_3}}",
            ),
            (
                "-pin_slices {[58:11]}",
                "-pin_slices {[11:11]}\n" + irq_slice,
            ),
            (
                "-pin_names {ICICLE_MSS:MSS_INT_F2M[58:11]}",
                "-pin_names {ICICLE_MSS:MSS_INT_F2M[58:12]}",
            ),
            (
                f'sd_connect_pins -sd_name {SD_NAME} -pin_names {{"ICICLE_MSS:MSS_INT_F2M[3:3]"',
                irq_pin + f"sd_connect_pins -sd_name {SD_NAME} -pin_names "
                '{"ICICLE_MSS:MSS_INT_F2M[3:3]"',
            ),
        ),
        "script_support/components/PF_CCC_C0.tcl": (
            ('"GL0_1_FABCLK_USED:false"', '"GL0_1_FABCLK_USED:true"'),
        ),
    }


def verify_reference(source: Path) -> None:
    """Verify the pinned upstream files before deriving.

    Parameters
    ----------
    source
        Official reference Git checkout.

    Raises
    ------
    ValueError
        Any pinned source file digest differs.
    """
    for relative, expected in SOURCE_HASHES.items():
        if sha256(source / relative) != expected:
            msg = f"reference source mismatch: {relative}"
            raise ValueError(msg)
    if tree_sha256(source) != SOURCE_TREE_SHA256:
        msg = "reference source tree differs from pinned commit"
        raise ValueError(msg)


def derive(source: Path, destination: Path) -> None:
    """Copy and transform one pinned reference without modifying its source.

    Parameters
    ----------
    source
        Verified official checkout.
    destination
        New, non-existing output path on the working disk.

    Raises
    ------
    FileExistsError
        Output exists and must be preserved.
    ValueError
        An upstream source anchor or derived digest differs.
    """
    verify_reference(source)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    with tempfile.TemporaryDirectory(prefix=".icicle-derive-", dir=destination.parent) as staging:
        staged_output = Path(staging) / "output"
        shutil.copytree(source, staged_output, symlinks=True)
        for relative, replacements in edits().items():
            path = staged_output / relative
            content = path.read_text(encoding="utf-8")
            for old, new in replacements:
                content = replace_once(content, old, new, relative)
            path.write_text(content, encoding="utf-8")
            if sha256(path) != DERIVED_HASHES[relative]:
                msg = f"derived source mismatch: {relative}"
                raise ValueError(msg)
        script_destination = staged_output / DERIVED_SCRIPT
        shutil.copyfile(WITNESS_SCRIPT, script_destination)
        source_rtl = REPOSITORY_ROOT / "rtl"
        rtl_sources = sorted(source_rtl.glob("*.sv"))
        witness_hashes = {path.name: sha256(path) for path in rtl_sources}
        snapshot = staged_output / RTL_SNAPSHOT
        snapshot.mkdir()
        for path in rtl_sources:
            copied = snapshot / path.name
            shutil.copyfile(path, copied)
            if (
                sha256(path) != witness_hashes[path.name]
                or sha256(copied) != witness_hashes[path.name]
            ):
                msg = f"RTL source changed while deriving: {path.name}"
                raise ValueError(msg)
        excluded = frozenset({*DERIVED_HASHES, DERIVED_SCRIPT, "witness_derivation.json"})
        if (
            tree_sha256(staged_output, excluded, frozenset({RTL_SNAPSHOT}))
            != REFERENCE_REMAINDER_SHA256
        ):
            msg = "derived reference remainder differs from pinned commit"
            raise ValueError(msg)
        manifest = {
            "source_commit": REFERENCE_COMMIT,
            "source_tree_sha256": SOURCE_TREE_SHA256,
            "reference_remainder_sha256": REFERENCE_REMAINDER_SHA256,
            "source_files_sha256": SOURCE_HASHES,
            "derived_files_sha256": DERIVED_HASHES,
            "witness_tcl_sha256": sha256(script_destination),
            "witness_rtl_dir": RTL_SNAPSHOT,
            "witness_rtl_sha256": witness_hashes,
            "validation_scope": "source derivation only; Libero DRC and timing are unverified",
        }
        (staged_output / "witness_derivation.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(destination)
        staged_output.rename(destination)


def verify_derived(destination: Path) -> None:
    """Refuse a derived tree that differs from its current repository inputs.

    Parameters
    ----------
    destination
        Source tree produced by the pinned reference derivation.

    Raises
    ------
    ValueError
        Manifest, vendor Tcl, connection Tcl or RTL snapshot differs.
    """
    rtl_sources = sorted((REPOSITORY_ROOT / "rtl").glob("*.sv"))
    witness_hashes = {path.name: sha256(path) for path in rtl_sources}
    expected = {
        "source_commit": REFERENCE_COMMIT,
        "source_tree_sha256": SOURCE_TREE_SHA256,
        "reference_remainder_sha256": REFERENCE_REMAINDER_SHA256,
        "source_files_sha256": SOURCE_HASHES,
        "derived_files_sha256": DERIVED_HASHES,
        "witness_tcl_sha256": sha256(WITNESS_SCRIPT),
        "witness_rtl_dir": RTL_SNAPSHOT,
        "witness_rtl_sha256": witness_hashes,
        "validation_scope": "source derivation only; Libero DRC and timing are unverified",
    }
    manifest_path = destination / "witness_derivation.json"
    if manifest_path.is_symlink():
        msg = "derived manifest must be a local file"
        raise ValueError(msg)
    manifest = load_json_object(manifest_path)
    if manifest != expected:
        msg = "derived manifest differs from current repository input"
        raise ValueError(msg)
    excluded = frozenset({*DERIVED_HASHES, DERIVED_SCRIPT, "witness_derivation.json"})
    if tree_sha256(destination, excluded, frozenset({RTL_SNAPSHOT})) != REFERENCE_REMAINDER_SHA256:
        msg = "derived reference remainder differs from pinned commit"
        raise ValueError(msg)
    for relative, digest in DERIVED_HASHES.items():
        path = destination / relative
        if path.is_symlink() or sha256(path) != digest:
            msg = f"derived vendor Tcl changed: {relative}"
            raise ValueError(msg)
    connection = destination / DERIVED_SCRIPT
    if connection.is_symlink() or sha256(connection) != expected["witness_tcl_sha256"]:
        msg = "derived witness connection Tcl changed"
        raise ValueError(msg)
    snapshot = destination / RTL_SNAPSHOT
    if (
        snapshot.is_symlink()
        or not snapshot.is_dir()
        or {path.name for path in snapshot.iterdir()} != set(witness_hashes)
    ):
        msg = "derived RTL source set changed"
        raise ValueError(msg)
    for name, digest in witness_hashes.items():
        path = snapshot / name
        if path.is_symlink() or not path.is_file() or sha256(path) != digest:
            msg = f"derived RTL changed: {name}"
            raise ValueError(msg)


def main() -> None:
    """Derive a fresh Libero input tree or verify it before a vendor run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="check an existing derived tree")
    parser.add_argument("source", type=Path, help="clean reference checkout or derived tree")
    parser.add_argument("destination", nargs="?", type=Path, help="new Samsung output directory")
    arguments = parser.parse_args()
    if arguments.verify:
        if arguments.destination is not None:
            parser.error("--verify takes only the derived tree")
        verify_derived(arguments.source.resolve())
        print(f"derived Icicle inputs verified: {arguments.source.resolve()}")
    else:
        if arguments.destination is None:
            parser.error("derivation requires source and new destination")
        derive(arguments.source.resolve(), arguments.destination.absolute())


if __name__ == "__main__":
    main()
