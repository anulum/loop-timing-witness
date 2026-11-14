# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — AMP image receipt corpus shared with the native analysis

"""Hold Python's image receipt check in a shared corpus.

The base case is a real ISA image directory: the whole firmware committed in
``amp-elf-cases.json``, the platform of ``tests/test_amp_platform.py``
compiled with the real ``dtc``, the run configuration of
``tests/test_amp_image_flow.py`` and the verification vector its request
records, with a C-kernel preparation and an image document reduced to the
members ``validate_image_receipt`` reads. The cases break and keep each
declaration, every rule of the recorded vector and its canonical integers,
each file, the firmware's contract and exit channel, and the declared
platform, run, stack and segments, Python's numeric equality included.

The committed form keeps the tree without ``firmware.elf`` (the native test
writes it from the ELF corpus), the base image and preparation documents, and
per case the entries removed and written, ``[offset, hex]`` edits of the
firmware, and patches of the two documents (``{"path": [...], "set"|"remove"}``).
An outcome is ``{"value": true}``, Python's refusal text or its ``OSError``
text, with the case directory written ``<root>``.
"""

from __future__ import annotations

import copy
import json
from dataclasses import asdict
from typing import TYPE_CHECKING, Any, Final

from test_amp_contract import RUN
from test_amp_elf_corpus import _apply
from test_amp_image_contract_corpus import _firmware
from test_amp_image_flow import CONFIGURATION, REQUEST
from test_amp_platform import SOURCE
from test_device_tree_corpus import _compile

from conftest import REPOSITORY_ROOT
from loop_timing_witness.amp_image_contract import admit_image_contract
from loop_timing_witness.amp_image_options import verification_arguments
from loop_timing_witness.amp_image_receipt import validate_image_receipt
from loop_timing_witness.amp_platform import bind_platform
from loop_timing_witness.device_tree_blob import decode_device_tree

if TYPE_CHECKING:
    from pathlib import Path

CORPUS: Final = REPOSITORY_ROOT / "analysis/rust/tests/data/amp-image-receipt-cases.json"
DIGEST: Final = "ab" * 32
COMPILER: Final = "/usr/bin/riscv64-linux-gnu-gcc-13"
PREFIX: Final = ["/usr/bin/python3", "source/tools/verify_amp_image.py", "--directory", "."]
Case = dict[str, Any]


def _vector(**changes: str) -> list[str]:
    """Return the recorded verification vector with option values replaced.

    Parameters
    ----------
    **changes
        New values by option name without dashes, underscores for inner dashes.

    Returns
    -------
    list[str]
        The whole vector.
    """
    words = [*PREFIX, *verification_arguments(REQUEST)]
    for name, value in changes.items():
        index = words.index("--" + name.replace("_", "-"))
        words[index + 1] = value
    return words


def _commands(vector: object) -> dict[str, Any]:
    """Return a tree write of ``build_commands.json`` holding one verification vector.

    Parameters
    ----------
    vector
        The ``verify`` member.

    Returns
    -------
    dict[str, Any]
        Tree edits writing the document.
    """
    return {"remove": [], "write": {"build_commands.json": json.dumps({"verify": vector})}}


def _case(
    tree: dict[str, Any] | None = None,
    firmware: list[list[Any]] | None = None,
    image: list[dict[str, Any]] | None = None,
    preparation: list[dict[str, Any]] | None = None,
) -> Case:
    """Return one case with absent parts empty.

    Parameters
    ----------
    tree
        Entries removed and written.
    firmware
        Firmware edits.
    image
        Image document patch.
    preparation
        Preparation document patch.

    Returns
    -------
    Case
        The case.
    """
    return {
        "tree": tree or {"remove": [], "write": {}},
        "firmware": firmware or [],
        "image": image or [],
        "preparation": preparation or [],
    }


def _set(*path: str | int, value: object) -> dict[str, Any]:
    """Return a patch operation that sets one member.

    Parameters
    ----------
    *path
        Member path.
    value
        New value.

    Returns
    -------
    dict[str, Any]
        The operation.
    """
    return {"path": list(path), "set": value}


def _declaration_cases() -> dict[str, Case]:
    """Return the cases of the image and preparation declarations.

    Returns
    -------
    dict[str, Case]
        Cases by name.
    """
    inputs = {"compiler": DIGEST, "source/contract.c": DIGEST}
    return {
        "ISA image": _case(),
        "preparation of another schema": _case(preparation=[_set("schema", value="other")]),
        "preparation not for ISA": _case(preparation=[_set("isa", value=False)]),
        "preparation ISA as one": _case(preparation=[_set("isa", value=1)]),
        "preparation of another compiler": _case(preparation=[_set("compiler", value="/bin/cc")]),
        "preparation without compiler": _case(preparation=[{"path": ["compiler"], "remove": True}]),
        "preparation of another compiler digest": _case(
            preparation=[_set("compiler_sha256", value="cd" * 32)]
        ),
        "preparation inputs naming the compiler": _case(
            preparation=[_set("inputs", value=inputs)], image=[_set("inputs", value=inputs)]
        ),
        "image inputs without the compiler": _case(
            image=[_set("inputs", value={"source/contract.c": DIGEST})]
        ),
        "image inputs with another file": _case(
            image=[_set("inputs", "source/other.c", value=DIGEST)]
        ),
        "image of another schema": _case(image=[_set("schema", value="other")]),
        "image simulation as one": _case(image=[_set("simulation_only", value=1)]),
        "image not simulation": _case(image=[_set("simulation_only", value=False)]),
        "image physical as zero": _case(image=[_set("physical_verified", value=0)]),
        "image physically verified": _case(image=[_set("physical_verified", value=True)]),
        "image of the parked exit": _case(image=[_set("exit_mode", value="parked")]),
        "preparation for the Rust kernel": _case(
            preparation=[_set("kernel_backend", value="rust")]
        ),
        "image with a Rust receipt": _case(image=[_set("rust_kernel", value={})]),
    }


def _vector_cases() -> dict[str, Case]:
    """Return the cases of the recorded verification vector.

    Returns
    -------
    dict[str, Case]
        Cases by name.
    """
    vector = _vector()
    swapped = [*vector[:8], vector[10], vector[11], vector[8], vector[9], *vector[12:]]
    return {
        "commands missing": _case(tree={"remove": ["build_commands.json"], "write": {}}),
        "commands not JSON": _case(tree={"remove": [], "write": {"build_commands.json": "{"}}),
        "commands without a vector": _case(
            tree={"remove": [], "write": {"build_commands.json": "{}"}}
        ),
        "vector a string": _case(tree=_commands(" ".join(vector))),
        "vector one word short": _case(tree=_commands(vector[:-1])),
        "vector with a number": _case(tree=_commands([*vector[:-1], 16384])),
        "relative interpreter": _case(tree=_commands(["python3", *vector[1:]])),
        "empty interpreter": _case(tree=_commands(["", *vector[1:]])),
        "another verifier": _case(tree=_commands([vector[0], "verify.py", *vector[2:]])),
        "another directory": _case(tree=_commands([*vector[:3], "image", *vector[4:]])),
        "options out of order": _case(tree=_commands(swapped)),
        "another blob name": _case(tree=_commands(_vector(dtb="other.dtb"))),
        "another configuration name": _case(tree=_commands(_vector(configuration="run.txt"))),
        "stack with a plus sign": _case(tree=_commands(_vector(stack_bytes="+16384"))),
        "stack with a leading zero": _case(tree=_commands(_vector(stack_bytes="016384"))),
        "hart negative zero": _case(tree=_commands(_vector(hart="-0"))),
        "interrupt in exponent form": _case(tree=_commands(_vector(interrupt="4e1"))),
        "hart in another script": _case(tree=_commands(_vector(hart=chr(0x661)))),
        "stack of 21 characters": _case(tree=_commands(_vector(stack_bytes="1" + "0" * 20))),
        "smallest 64-bit stack": _case(tree=_commands(_vector(stack_bytes=str(-(1 << 63))))),
        "stack beyond 64 bits": _case(tree=_commands(_vector(stack_bytes=str(1 << 63)))),
        "Spike layout": _case(tree=_commands(_vector(plic_layout="spike"))),
        "unknown layout": _case(tree=_commands(_vector(plic_layout="other"))),
        "unknown layout and no stack": _case(
            tree=_commands(_vector(plic_layout="other", stack_bytes="0"))
        ),
        "another firmware node": _case(
            tree=_commands(_vector(firmware_node="/reserved-memory/other"))
        ),
    }


def _file_cases(content: bytes) -> dict[str, Case]:
    """Return the cases of the image's files and its firmware.

    Parameters
    ----------
    content
        Firmware image.

    Returns
    -------
    dict[str, Case]
        Cases by name.
    """
    run_offset = 4096 + 0xAD8
    return {
        "blob missing": _case(tree={"remove": ["platform.dtb"], "write": {}}),
        "blob not a device tree": _case(tree={"remove": [], "write": {"platform.dtb": "text"}}),
        "configuration missing": _case(tree={"remove": ["configuration.txt"], "write": {}}),
        "configuration incomplete": _case(
            tree={"remove": [], "write": {"configuration.txt": "pid 10"}}
        ),
        "firmware missing": _case(tree={"remove": ["firmware.elf"], "write": {}}),
        "firmware run constant changed": _case(
            firmware=[[run_offset, f"{content[run_offset] ^ 1:02x}"]]
        ),
        "firmware channel preloaded": _case(firmware=[[8192, "01"]]),
        "configuration of another run": _case(
            tree={"remove": [], "write": {"configuration.txt": "lqr" + _ascii(CONFIGURATION)[3:]}}
        ),
    }


def _ascii(content: bytes) -> str:
    """Return ASCII bytes as text.

    Parameters
    ----------
    content
        ASCII bytes.

    Returns
    -------
    str
        The text.
    """
    return content.decode("ascii")


def _comparison_cases() -> dict[str, Case]:
    """Return the cases of the declared platform, run, stack and segments.

    Returns
    -------
    dict[str, Case]
        Cases by name.
    """
    return {
        "declared hart differs": _case(image=[_set("platform", "hart", value=2)]),
        "declared hart as a float": _case(image=[_set("platform", "hart", value=1.0)]),
        "declared platform without its source": _case(
            image=[{"path": ["platform", "source"], "remove": True}]
        ),
        "declared cycles differ": _case(image=[_set("run", "cycles", value=11)]),
        "declared controller as false": _case(image=[_set("run", "lqr", value=False)]),
        "declared controller as true": _case(image=[_set("run", "lqr", value=True)]),
        "declared stack differs": _case(image=[_set("stack_bytes", value=8192)]),
        "declared stack as a float": _case(image=[_set("stack_bytes", value=16384.0)]),
        "declared stack as a fraction": _case(image=[_set("stack_bytes", value=16384.5)]),
        "declared stack missing": _case(image=[{"path": ["stack_bytes"], "remove": True}]),
        "declared segments empty": _case(image=[_set("segments", value=[])]),
        "declared run missing": _case(image=[{"path": ["run"], "remove": True}]),
    }


def _documents(blob: bytes, content: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the base image and preparation documents.

    Parameters
    ----------
    blob
        Compiled platform.
    content
        Firmware image.

    Returns
    -------
    tuple[dict[str, Any], dict[str, Any]]
        The image and the preparation.
    """
    platform = bind_platform(
        decode_device_tree(blob), REQUEST.memory, REQUEST.device_path, REQUEST.plic
    )
    segments = admit_image_contract(content, platform, RUN, REQUEST.memory.stack_bytes)
    inputs = {"source/contract.c": DIGEST}
    preparation = {
        "schema": "loop-timing-witness.amp-image-preparation.v1",
        "isa": True,
        "compiler": COMPILER,
        "compiler_sha256": DIGEST,
        "toolchain": {"driver": {"path": COMPILER, "sha256": DIGEST}},
        "inputs": inputs,
    }
    image = {
        "schema": "loop-timing-witness.amp-image.v1",
        "simulation_only": True,
        "physical_verified": False,
        "exit_mode": "isa_htif",
        "inputs": {"compiler": DIGEST, **inputs},
        "platform": asdict(platform),
        "run": {**asdict(RUN), "coefficients": list(RUN.coefficients)},
        "stack_bytes": REQUEST.memory.stack_bytes,
        "segments": [asdict(segment) for segment in segments],
    }
    return image, preparation


def _patched(base: dict[str, Any], patch: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a document with members set or removed.

    Parameters
    ----------
    base
        Base document.
    patch
        Operations in order.

    Returns
    -------
    dict[str, Any]
        Patched copy.
    """
    document = copy.deepcopy(base)
    for operation in patch:
        *parents, last = operation["path"]
        node = document
        for part in parents:
            node = node[part]
        if "remove" in operation:
            del node[last]
        else:
            node[last] = operation["set"]
    return document


def _write_tree(directory: Path, template: dict[str, Any], content: bytes, case: Case) -> None:
    """Write the base tree, the edited firmware and a case's tree edits.

    Parameters
    ----------
    directory
        Case folder.
    template
        Base tree without the firmware.
    content
        Firmware image.
    case
        The case.
    """
    for name, entry in template.items():
        if isinstance(entry, str):
            (directory / name).write_text(entry, encoding="utf-8")
        else:
            (directory / name).write_bytes(bytes.fromhex(entry["hex"]))
    (directory / "firmware.elf").write_bytes(_apply(content, case["firmware"]))
    for name in case["tree"]["remove"]:
        (directory / name).unlink()
    for name, text in case["tree"]["write"].items():
        (directory / name).write_text(text, encoding="utf-8")


def _outcome(directory: Path, image: dict[str, Any], preparation: dict[str, Any]) -> dict[str, Any]:
    """Check one case and return the value, the refusal or the ``OSError`` text.

    Parameters
    ----------
    directory
        Case folder.
    image
        Image document.
    preparation
        Preparation document.

    Returns
    -------
    dict[str, Any]
        ``{"value": true}``, ``{"refusal": text}`` or ``{"os_error": text}``, with ``<root>``.
    """
    root = str(directory)
    try:
        validate_image_receipt(directory, image, preparation)
    except ValueError as error:
        return {"refusal": str(error).replace(root, "<root>")}
    except OSError as error:
        return {"os_error": str(error).replace(root, "<root>")}
    return {"value": True}


def corpus(directory: Path) -> dict[str, Any]:
    """Build every case under ``directory`` and return the corpus.

    Parameters
    ----------
    directory
        Owned directory for the compiler's files and the case folders.

    Returns
    -------
    dict[str, Any]
        The tree, the documents and the cases with their outcomes.
    """
    content = _firmware()
    compiled = directory / "compiled"
    compiled.mkdir()
    blob = _compile(SOURCE, compiled, force=False)
    template = {
        "build_commands.json": json.dumps({"verify": _vector()}),
        "configuration.txt": _ascii(CONFIGURATION),
        "platform.dtb": {"hex": blob.hex()},
    }
    image, preparation = _documents(blob, content)
    cases = _declaration_cases() | _vector_cases() | _file_cases(content) | _comparison_cases()
    written = []
    for index, (name, case) in enumerate(cases.items()):
        folder = directory / f"case-{index}"
        folder.mkdir()
        _write_tree(folder, template, content, case)
        documents = _patched(image, case["image"]), _patched(preparation, case["preparation"])
        written.append({"name": name, **case, **_outcome(folder, *documents)})
    return {
        "schema": "loop-timing-witness.amp-image-receipt-cases.v1",
        "description": (
            "Python's validate_image_receipt on a real ISA image directory. tree is the folder "
            "without firmware.elf, which is the firmware of amp-elf-cases.json; a case removes and "
            "writes entries, applies [offset, hex] firmware edits and patches the image and "
            "preparation documents. The outcome is value, refusal or os_error, with <root> for the "
            "case folder."
        ),
        "tree": template,
        "image": image,
        "preparation": preparation,
        "cases": written,
    }


def _text(document: dict[str, Any]) -> str:
    """Return the committed text form of the corpus.

    Parameters
    ----------
    document
        Corpus.

    Returns
    -------
    str
        Compact sorted JSON and a final newline.
    """
    return json.dumps(document, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"


def test_committed_corpus_equals_python_outcomes(tmp_path: Path) -> None:
    """Rebuild the corpus with the real ``dtc`` and Python's check; require the committed file.

    Parameters
    ----------
    tmp_path
        Owned directory for the compiler's files and the case folders.
    """
    assert CORPUS.read_text(encoding="utf-8") == _text(corpus(tmp_path))
    assert CORPUS.with_name(CORPUS.name + ".license").is_file()
