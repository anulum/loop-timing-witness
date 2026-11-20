# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — development and test container definition

"""Keep the container definition's pins equal to the hosted workflows' and its downloads checked."""

from __future__ import annotations

import re
from typing import Final

from conftest import REPOSITORY_ROOT

DOCKERFILE: Final = REPOSITORY_ROOT / "container" / "Dockerfile"
WORKFLOWS: Final = REPOSITORY_ROOT / ".github" / "workflows"
PIN: Final = re.compile(r"(?<![\w=-])([a-z0-9][a-z0-9.+-]*)=([^\s\\]+)")


def _joined(text: str) -> str:
    """Join backslash-continued lines.

    Parameters
    ----------
    text
        Shell or Dockerfile text.

    Returns
    -------
    str
        The same text with every continuation joined to its line.
    """
    return text.replace("\\\n", " ")


def _apt_pins(text: str) -> dict[str, set[str]]:
    """Return the ``name=version`` pins of every ``apt-get install`` command in a text.

    Parameters
    ----------
    text
        Shell or Dockerfile text.

    Returns
    -------
    dict[str, set[str]]
        Versions pinned for each package.
    """
    pins: dict[str, set[str]] = {}
    for line in _joined(text).splitlines():
        if "apt-get install" in line:
            command = line.split("apt-get install", 1)[1].split("&&", 1)[0]
            for name, version in PIN.findall(command):
                pins.setdefault(name, set()).add(version)
    return pins


def test_base_image_is_pinned_by_digest() -> None:
    """The base image is Ubuntu 26.04, the hosted runners' release, pinned by digest."""
    assert re.search(
        r"^FROM ubuntu:26\.04@sha256:[0-9a-f]{64}$",
        DOCKERFILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )


def test_every_workflow_apt_pin_is_in_the_container_with_its_version() -> None:
    """Each package a workflow installs is installed in the container at the same version."""
    container = _apt_pins(DOCKERFILE.read_text(encoding="utf-8"))
    assert container
    assert all(len(versions) == 1 for versions in container.values())
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        for name, versions in _apt_pins(workflow.read_text(encoding="utf-8")).items():
            assert container.get(name) == versions, f"{workflow.name}: {name}"


def test_every_container_package_is_pinned() -> None:
    """The container's apt command installs only pinned packages."""
    text = _joined(DOCKERFILE.read_text(encoding="utf-8"))
    command = text.split("apt-get install", 1)[1].split("&&", 1)[0]
    words = [word for word in command.split() if not word.startswith("-")]
    assert words
    assert all(PIN.fullmatch(word) for word in words)


def test_toolchain_versions_equal_the_workflows() -> None:
    """Python, Go and Rust versions in the container are the workflows' versions."""
    container = DOCKERFILE.read_text(encoding="utf-8")
    workflows = "\n".join(path.read_text(encoding="utf-8") for path in WORKFLOWS.glob("*.yml"))
    pythons = set(re.findall(r'python-version: "([^"]+)"', workflows))
    gos = set(re.findall(r'go-version: "([^"]+)"', workflows))
    rusts = set(re.findall(r"rustup toolchain install (\S+)", workflows))
    assert pythons == {"3.15.2"}
    assert gos == {"1.27.4"}
    assert rusts == {"1.100.0"}
    assert "cpython-3.15.2%2B" in container
    assert "go1.27.4.linux-amd64.tar.gz" in container
    assert set(re.findall(r"rustup toolchain install (\S+)", container)) == rusts
    assert "rustup default 1.100.0" in container


def test_every_download_is_checked_before_use() -> None:
    """Each ``curl -o`` download is followed by a strict SHA-256 check of the same file."""
    text = _joined(DOCKERFILE.read_text(encoding="utf-8"))
    downloads = re.findall(r"curl [^&]*-o (\S+)", text)
    checks = re.findall(r'echo "[0-9a-f]{64}  (\S+)"\s*\|\s*sha256sum --check --strict', text)
    assert len(downloads) == 3
    assert downloads == checks
