# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — actual capture producer source context

"""Bind loaded project implementations and refuse source drift during capture."""

from __future__ import annotations

import hashlib
import platform
import sys
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

import loop_timing_witness
from manifest_io import canonical_json_bytes


@dataclass(frozen=True)
class FrozenProducerSource:
    """One actual source origin and its retained immutable identity.

    Attributes
    ----------
    origin
        Source pathname used by the producer or its loaded project package.
    resolved_origin
        Physical source location when the bytes were captured.
    snapshot
        Retained source member inside the capture.
    digest
        SHA-256 of the exact source bytes.
    """

    origin: Path
    resolved_origin: Path
    snapshot: Path
    digest: str

    def verify(self) -> None:
        """Refuse changed source locations, source bytes, or frozen bytes.

        Raises
        ------
        OSError
            If an original or retained source cannot be read.
        ValueError
            If either source identity differs from the recorded capture.
        """
        if (
            self.origin.resolve(strict=True) != self.resolved_origin
            or hashlib.sha256(self.origin.read_bytes()).hexdigest() != self.digest
            or hashlib.sha256(self.snapshot.read_bytes()).hexdigest() != self.digest
        ):
            message = f"capture producer source changed: {self.origin}"
            raise ValueError(message)


@dataclass(frozen=True)
class ProducerSourceContext:
    """A run-linked context and all source identities required for its producer.

    Attributes
    ----------
    sources
        Native, worker, and actual parent project source identities.
    document
        Immutable interpreter, environment, and source-origin record.
    document_digest
        SHA-256 of the context document when it was created.
    """

    sources: tuple[FrozenProducerSource, ...]
    document: Path
    document_digest: str

    def verify(self) -> None:
        """Require unchanged originals, frozen members, and context metadata.

        Raises
        ------
        OSError
            If a recorded source or context document cannot be read.
        ValueError
            If any recorded identity has changed.
        """
        for source in self.sources:
            source.verify()
        if hashlib.sha256(self.document.read_bytes()).hexdigest() != self.document_digest:
            message = "capture producer context changed"
            raise ValueError(message)

    def artifacts(self) -> list[Path]:
        """Return every retained member that the run must bind by digest.

        Returns
        -------
        list of Path
            Source members and their immutable context document.
        """
        return [*(source.snapshot for source in self.sources), self.document]


def _parent_sources(output: Path) -> dict[Path, Path]:
    """Map actual loaded project code to separate parent-source destinations.

    Parameters
    ----------
    output
        Existing capture directory.

    Returns
    -------
    dict of Path to Path
        Actual package and loaded parent-tool origins mapped to retained members.
    """
    package = Path(loop_timing_witness.__file__).parent
    files = [*package.rglob("*.py"), *(package / "data").glob("*.json")]
    parents = {
        path: output / "source/parent_package/loop_timing_witness" / path.relative_to(package)
        for path in files
    }
    tools = Path(__file__).parent.resolve()
    for module in tuple(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if isinstance(filename, str):
            origin = Path(filename)
            if origin.suffix == ".py" and origin.resolve().parent == tools:
                parents[origin] = output / "source/parent_tools" / origin.name
    return parents


def snapshot_producer_context(
    root: Path, output: Path, native_snapshots: list[Path]
) -> ProducerSourceContext:
    """Freeze actual producer code and link its interpreter and environment identity.

    Parameters
    ----------
    root
        Root whose native and optional worker inputs were already snapshotted.
    output
        Existing exclusive capture directory.
    native_snapshots
        Original native and worker members retained beneath ``source``.

    Returns
    -------
    ProducerSourceContext
        Immutable identities to verify before accepting the run.

    Raises
    ------
    OSError
        If actual source bytes or exclusive outputs cannot be accessed.
    ValueError
        If the prior source copy already differs from its origin.
    """
    parents = _parent_sources(output)
    origins = {path: root / path.relative_to(output / "source") for path in native_snapshots}
    parent_origins = {destination: origin for origin, destination in parents.items()}
    sources = []
    for destination, origin in sorted((origins | parent_origins).items()):
        raw = origin.read_bytes()
        if destination in parent_origins:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as stream:
                stream.write(raw)
        source = FrozenProducerSource(
            origin, origin.resolve(strict=True), destination, hashlib.sha256(raw).hexdigest()
        )
        source.verify()
        sources.append(source)
    context: dict[str, object] = {
        "native_source_root": str(root.resolve()),
        "python": {
            "executable": str(Path(sys.executable).resolve()),
            "prefix": sys.prefix,
            "version": sys.version,
            "implementation": sys.implementation.name,
            "cache_tag": sys.implementation.cache_tag,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "dependencies": {
            name: version(name)
            for name in (
                "jsonschema",
                "attrs",
                "referencing",
                "jsonschema-specifications",
                "rpds-py",
            )
        },
        "sources": {
            source.snapshot.relative_to(output).as_posix(): {
                "origin": str(source.origin.absolute()),
                "resolved_origin": str(source.resolved_origin),
                "sha256": source.digest,
            }
            for source in sources
        },
    }
    document = output / "producer_context.json"
    raw_context = canonical_json_bytes(context)
    with document.open("xb") as stream:
        stream.write(raw_context)
    return ProducerSourceContext(tuple(sources), document, hashlib.sha256(raw_context).hexdigest())
