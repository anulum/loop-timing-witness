# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — independent consumer of the actual Cargo archive

"""Build a packaged dependency and exercise its public arithmetic from a separate Cargo project."""

from __future__ import annotations

import json
import shutil
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_packaged_rust_public_api(tmp_path: Path) -> None:
    """Verify the actual archive as a dependency through real public state and refusal tests.

    Parameters
    ----------
    tmp_path
        Exclusive producer output, unpacked archive, independent client and raw Cargo logs.
        The client resolves the unpacked package rather than the working-tree source.
    """
    package_target = tmp_path / "producer"
    package = [
        "cargo",
        "package",
        "--offline",
        "--locked",
        "--allow-dirty",
        "--manifest-path",
        str(ROOT / "controllers/rust/Cargo.toml"),
        "--target-dir",
        str(package_target),
    ]
    (tmp_path / "package.argv.json").write_text(json.dumps(package, indent=2))
    result = subprocess.run(package, cwd=ROOT, capture_output=True, text=True, check=False)
    (tmp_path / "package.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    archives = list((package_target / "package").glob("*.crate"))
    assert len(archives) == 1
    dependency = tmp_path / "dependency"
    with tarfile.open(archives[0]) as archive:
        archive.extractall(dependency, filter="data")
    unpacked = list(dependency.iterdir())
    assert len(unpacked) == 1
    client = tmp_path / "client"
    (client / "src").mkdir(parents=True)
    (client / "tests").mkdir()
    (client / "Cargo.toml").write_text(
        '[package]\nname = "witness-package-consumer"\nversion = "0.0.0"\n'
        'edition = "2024"\npublish = false\n\n[dependencies]\n'
        f'witness-controller = {{ path = "{unpacked[0].as_posix()}" }}\n'
    )
    (client / "src/lib.rs").write_text(
        "//! An independent allocator-free client of the packaged public API.\n"
        "#![no_std]\n#![deny(missing_docs)]\n#![forbid(unsafe_code)]\n"
        "pub use witness_controller::{\n"
        "    Command, Coefficients, InvalidCoefficients, PidState, lqr_step,\n};\n"
    )
    original = ROOT / "controllers/rust/tests/controller_api.rs"
    shipped = unpacked[0] / "tests/controller_api.rs"
    assert original.read_bytes() == shipped.read_bytes()
    shutil.copy2(shipped, client / "tests/controller_api.rs")
    commands = [
        ["cargo", "generate-lockfile", "--offline"],
        ["cargo", "test", "--offline", "--locked"],
        ["cargo", "clippy", "--offline", "--locked", "--all-targets", "--", "-D", "warnings"],
        ["cargo", "build", "--offline", "--locked", "--lib", "--target", "wasm32-unknown-unknown"],
        [
            "cargo",
            "build",
            "--offline",
            "--locked",
            "--lib",
            "--target",
            "riscv64imac-unknown-none-elf",
        ],
    ]
    (client / "commands.json").write_text(json.dumps(commands, indent=2))
    for index, argv in enumerate(commands):
        observed = subprocess.run(argv, cwd=client, capture_output=True, text=True, check=False)
        (client / f"command_{index}.log").write_text(observed.stdout + observed.stderr)
        assert observed.returncode == 0, observed.stdout + observed.stderr
    assert "2 passed" in (client / "command_1.log").read_text()
    # Inspect the shipped kernel's actual generated target objects, beyond Cargo's exit status.
    libraries = list(
        (client / "target/riscv64imac-unknown-none-elf/debug/deps").glob(
            "libwitness_controller-*.rlib"
        )
    )
    assert len(libraries) == 1
    members = subprocess.check_output(["ar", "t", str(libraries[0])], text=True).splitlines()
    objects = [member for member in members if member.endswith(".o")]
    assert objects
    for member in objects:
        data = subprocess.check_output(["ar", "p", str(libraries[0]), member])
        assert data[:6] == b"\x7fELF\x02\x01", "little-endian ELF64 target object required"
        assert int.from_bytes(data[18:20], "little") == 243, "RISC-V target object required"
        assert int.from_bytes(data[48:52], "little") & 6 == 0, "soft-float target ABI required"
