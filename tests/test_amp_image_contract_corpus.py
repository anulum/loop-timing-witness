# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — AMP image contract and exit channel corpus shared with the native analysis

"""Hold Python's image contract and ISA exit channel admission in a shared corpus.

The firmware is the whole image committed in ``amp-elf-cases.json``, compiled
from the platform of ``tests/test_amp_platform.py`` and the run of
``tests/test_amp_contract.py`` with a 16384-byte stack. The platform is bound
here from that test's source with the real ``dtc``. Every case changes the
image's bytes (``[offset, hex]`` edits, mostly symbol records) or the inputs
(``[path, value]`` changes of the platform, the run and the stack), and keeps
or breaks one rule of ``admit_image_contract``: the ELF admission, the
required symbols, the controller entry points, the two constants and the BSS
and stack geometry, each at and beside its bounds. The exit channel is
admitted as the image receipt admits it, for ISA images and on the contract's
segments, so a case reaches it only when the contract admits the image.

An outcome holds ``contract``, the segments as ``dataclasses.asdict`` writes
them or the refusal, and ``exit``, ``"admitted"``, the refusal, or ``null``
where the contract refused.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict
from typing import TYPE_CHECKING, Any, Final

from test_amp_contract import RUN
from test_amp_device import PATH
from test_amp_device import SELECTION as PLIC_SELECTION
from test_amp_elf_corpus import DIGESTS, SYMBOL, _apply, _tables
from test_amp_memory import SELECTION as MEMORY_SELECTION
from test_amp_platform import SOURCE
from test_device_tree_corpus import _compile

from conftest import REPOSITORY_ROOT
from loop_timing_witness.amp_contract import AmpRun
from loop_timing_witness.amp_device import WitnessDevice
from loop_timing_witness.amp_elf_symbols import read_symbols
from loop_timing_witness.amp_exit_channel import admit_exit_channel
from loop_timing_witness.amp_image_contract import admit_image_contract
from loop_timing_witness.amp_memory import ReservedMemory
from loop_timing_witness.amp_platform import AmpPlatform, bind_platform
from loop_timing_witness.device_tree_blob import decode_device_tree
from loop_timing_witness.device_tree_interrupts import PlicRegisters
from loop_timing_witness.device_tree_resources import Region

if TYPE_CHECKING:
    from pathlib import Path

DATA: Final = REPOSITORY_ROOT / "analysis/rust/tests/data"
CORPUS: Final = DATA / "amp-image-contract-cases.json"
STACK: Final = 16384
FUNCTIONS: Final = ("witness_amp_main", "witness_amp_trap", "witness_amp_exit")
REQUIRED: Final = (
    "_start",
    *FUNCTIONS,
    "witness_amp_platform",
    "witness_amp_run",
    "__bss_start",
    "__bss_end",
    "__stack_top",
)
FIELDS: Final = {"info": 1, "value": 4, "size": 5}
Case = tuple[list[list[Any]], list[list[Any]]]


def _firmware() -> bytes:
    """Return the whole firmware committed in the ELF corpus, after checking its digest.

    Returns
    -------
    bytes
        The firmware image.
    """
    images = json.loads((DATA / "amp-elf-cases.json").read_text(encoding="utf-8"))["images"]
    content = bytes.fromhex(images["firmware"]["hex"])
    assert hashlib.sha256(content).hexdigest() == DIGESTS["firmware"]
    return content


def _records(content: bytes) -> dict[str, tuple[int, list[int]]]:
    """Return each global or weak symbol's record offset and fields, by name.

    Parameters
    ----------
    content
        Firmware image.

    Returns
    -------
    dict[str, tuple[int, list[int]]]
        Offset and ``[name, info, other, section, value, size]`` fields.
    """
    _, _, symbols, _, names = _tables(content)
    found = {}
    for offset in symbols:
        fields = list(SYMBOL.unpack_from(content, offset))
        if fields[1] >> 4 in (1, 2):
            name = names[fields[0] : names.index(b"\0", fields[0])].decode("ascii")
            found[name] = (offset, fields)
    return found


def _symbol(content: bytes, name: str, **changes: int) -> list[Any]:
    """Return the edit that changes fields of one symbol record.

    Parameters
    ----------
    content
        Firmware image.
    name
        Symbol name.
    **changes
        New ``info``, ``value`` or ``size``.

    Returns
    -------
    list[Any]
        ``[offset, hex]`` of the whole record.
    """
    offset, fields = _records(content)[name]
    for field, value in changes.items():
        fields[FIELDS[field]] = value
    return [offset, SYMBOL.pack(*fields).hex()]


def _kind(content: bytes, name: str, kind: int, binding: int | None = None) -> list[Any]:
    """Return the edit that gives one symbol another type, or another binding.

    Parameters
    ----------
    content
        Firmware image.
    name
        Symbol name.
    kind
        New symbol type.
    binding
        New binding, or ``None`` to keep it.

    Returns
    -------
    list[Any]
        ``[offset, hex]`` of the whole record.
    """
    info = _records(content)[name][1][1]
    return _symbol(content, name, info=((info >> 4 if binding is None else binding) << 4) | kind)


def _stack(content: bytes, *, start: int | None = None, end: int | None = None, top: int) -> Case:
    """Return the BSS and stack edits with the stack size that matches them.

    Parameters
    ----------
    content
        Firmware image.
    start
        New ``__bss_start``, or ``None`` to keep it.
    end
        New ``__bss_end``, or ``None`` to keep it.
    top
        New ``__stack_top``.

    Returns
    -------
    Case
        The symbol edits and the stack input whose top is ``top``.
    """
    symbols = read_symbols(content)
    end = symbols["__bss_end"].address if end is None else end
    edits = [_symbol(content, "__bss_end", value=end), _symbol(content, "__stack_top", value=top)]
    if start is not None:
        edits.append(_symbol(content, "__bss_start", value=start))
    return edits, [[["stack"], top - (end + 15) // 16 * 16]]


def _symbol_cases(content: bytes) -> dict[str, Case]:
    """Return the ELF admission, required symbol and entry point cases.

    Parameters
    ----------
    content
        Firmware image.

    Returns
    -------
    dict[str, Case]
        Edits and input changes by case name.
    """
    symbols = read_symbols(content)
    code = 0x80000000 + 2896
    cases: dict[str, Case] = {
        "compiled ISA firmware": ([], []),
        "firmware reservation moved": (
            [],
            [[["platform", "memory", "firmware", "address"], 0x80001000]],
        ),
        "start misplaced": ([_symbol(content, "_start", value=0x80000002)], []),
    }
    for name in REQUIRED:
        cases[f"{name} local"] = ([_kind(content, name, symbols[name].kind, binding=0)], [])
    for name in FUNCTIONS:
        size = symbols[name].size
        cases |= {
            f"{name} an object": ([_kind(content, name, 1)], []),
            f"{name} without size": ([_symbol(content, name, size=0)], []),
            f"{name} in writable memory": ([_symbol(content, name, value=0x80001000)], []),
            f"{name} at the code start": ([_symbol(content, name, value=0x80000000)], []),
            f"{name} ending at the code end": ([_symbol(content, name, value=code - size)], []),
            f"{name} past the code end": ([_symbol(content, name, value=code - size + 1)], []),
            f"{name} weak": ([_kind(content, name, 2, binding=2)], []),
        }
    return cases


def _constant_cases(content: bytes) -> dict[str, Case]:
    """Return the cases of the two compiled constants.

    Parameters
    ----------
    content
        Firmware image.

    Returns
    -------
    dict[str, Case]
        Edits and input changes by case name.
    """
    symbols = read_symbols(content)
    cases: dict[str, Case] = {}
    for name in ("witness_amp_platform", "witness_amp_run"):
        size = symbols[name].size
        offset = 4096 + symbols[name].address - 0x80000000
        cases |= {
            f"{name} a function": ([_kind(content, name, 2)], []),
            f"{name} one byte shorter": ([_symbol(content, name, size=size - 1)], []),
            f"{name} one byte longer": ([_symbol(content, name, size=size + 1)], []),
            f"{name} in writable memory": ([_symbol(content, name, value=0x80001000)], []),
            f"{name} at the code start": ([_symbol(content, name, value=0x80000000)], []),
            f"{name} before the code": ([_symbol(content, name, value=0x7FFFFFF8)], []),
            f"{name} ending at the code end": (
                [_symbol(content, name, value=0x80000B50 - size)],
                [],
            ),
            f"{name} past the code end": ([_symbol(content, name, value=0x80000B51 - size)], []),
            f"{name} first byte changed": ([[offset, f"{content[offset] ^ 1:02x}"]], []),
            f"{name} last byte changed": (
                [[offset + size - 1, f"{content[offset + size - 1] ^ 1:02x}"]],
                [],
            ),
        }
    return cases


def _input_cases(_: bytes) -> dict[str, Case]:
    """Return the cases whose platform or run differs from the one the image was compiled for.

    Parameters
    ----------
    _
        Firmware image, unchanged by these cases.

    Returns
    -------
    dict[str, Case]
        Input changes by case name.
    """
    return {
        "another hart": ([], [[["platform", "hart"], 2]]),
        "another source": ([], [[["platform", "source"], 41]]),
        "another aperture": ([], [[["platform", "device", "aperture", "address"], 0x40001000]]),
        "another priority word": ([], [[["platform", "device", "plic", "priority"], 0xC0000A4]]),
        "another enable word": ([], [[["platform", "device", "plic", "enable_word"], 0xC002108]]),
        "another threshold": ([], [[["platform", "device", "plic", "threshold"], 0xC201000]]),
        "another claim": ([], [[["platform", "device", "plic", "claim"], 0xC201008]]),
        "another telemetry address": (
            [],
            [[["platform", "memory", "shared", "address"], 0x80090000]],
        ),
        "another cycle count": ([], [[["run", "cycles"], 11]]),
        "another period": ([], [[["run", "period_ticks"], 32769]]),
        "the LQR controller": ([], [[["run", "lqr"], 1]]),
        "another overload": ([], [[["run", "overload_iterations"], 1]]),
        "another last coefficient": ([], [[["run", "coefficients", 10], 10]]),
    }


def _stack_cases(content: bytes) -> dict[str, Case]:
    """Return the BSS and stack geometry cases, each failing one condition or none.

    Parameters
    ----------
    content
        Firmware image.

    Returns
    -------
    dict[str, Case]
        Edits and input changes by case name.
    """
    end, top = 0x80001060, 0x80005060
    return {
        "stack below a page": _stack(content, top=end + 4080),
        "stack of one page": _stack(content, top=end + 4096),
        "stack not 16-byte aligned": _stack(content, top=end + 4104),
        "stack one aligned step larger": ([], [[["stack"], STACK + 16]]),
        "stack one aligned step smaller": ([], [[["stack"], STACK - 16]]),
        "stack past the writable memory": _stack(content, top=top + 16),
        "BSS start misaligned": _stack(content, start=0x8000104C, top=top),
        "BSS start moved by a word": _stack(content, start=0x80001050, top=top),
        "BSS start at the writable start": _stack(content, start=0x80001000, top=top),
        "BSS start before the writable memory": _stack(content, start=0x80000FF8, top=top),
        "BSS end misaligned": _stack(content, end=end + 4, top=top),
        "BSS end moved by a word": _stack(content, end=end + 8, top=top),
        "BSS end before its start": _stack(content, end=0x80001040, top=top),
        "empty BSS": _stack(content, end=0x80001048, top=top),
        "stack top one step higher": ([_symbol(content, "__stack_top", value=top + 16)], []),
        "stack top one step lower": ([_symbol(content, "__stack_top", value=top - 16)], []),
    }


def _exit_cases(content: bytes) -> dict[str, Case]:
    """Return the ISA exit channel cases, each admitted by the contract.

    Parameters
    ----------
    content
        Firmware image.

    Returns
    -------
    dict[str, Case]
        Edits by case name.
    """
    cases: dict[str, Case] = {}
    for name, address in (("tohost", 0x80001000), ("fromhost", 0x80001040)):
        offset = 8192 + address - 0x80001000
        cases |= {
            f"{name} local": ([_kind(content, name, 1, binding=0)], []),
            f"{name} weak": ([_kind(content, name, 1, binding=2)], []),
            f"{name} a function": ([_kind(content, name, 2)], []),
            f"{name} of four bytes": ([_symbol(content, name, size=4)], []),
            f"{name} of sixteen bytes": ([_symbol(content, name, size=16)], []),
            f"{name} misaligned": ([_symbol(content, name, value=address ^ 8)], []),
            f"{name} past the data bytes": ([_symbol(content, name, value=0x80001080)], []),
            f"{name} in the code": ([_symbol(content, name, value=0x80000B00)], []),
            f"{name} outside every segment": ([_symbol(content, name, value=0x80000FC0)], []),
            f"{name} first byte preloaded": ([[offset, "01"]], []),
            f"{name} last byte preloaded": ([[offset + 7, "80"]], []),
        }
    return cases | {
        "fromhost at tohost": ([_symbol(content, "fromhost", value=0x80001000)], []),
        "tohost at fromhost": ([_symbol(content, "tohost", value=0x80001040)], []),
    }


def _inputs(platform: AmpPlatform) -> dict[str, Any]:
    """Return the base inputs as the corpus writes them.

    Parameters
    ----------
    platform
        Bound platform.

    Returns
    -------
    dict[str, Any]
        The platform and run as ``dataclasses.asdict`` writes them, and the stack.
    """
    run = {**asdict(RUN), "coefficients": list(RUN.coefficients)}
    return {"platform": asdict(platform), "run": run, "stack": STACK}


def _changed(inputs: dict[str, Any], changes: list[list[Any]]) -> tuple[AmpPlatform, AmpRun, int]:
    """Apply a case's input changes and rebuild the Python inputs.

    Parameters
    ----------
    inputs
        Base inputs.
    changes
        ``[path, value]`` changes.

    Returns
    -------
    tuple[AmpPlatform, AmpRun, int]
        The platform, the run and the stack.
    """
    document = copy.deepcopy(inputs)
    for path, value in changes:
        node = document
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
    platform, memory = document["platform"], document["platform"]["memory"]
    device = document["platform"]["device"]
    built = AmpPlatform(
        ReservedMemory(Region(**memory["firmware"]), Region(**memory["shared"])),
        WitnessDevice(Region(**device["aperture"]), PlicRegisters(**device["plic"])),
        platform["hart"],
        platform["source"],
    )
    run = document["run"]
    return built, AmpRun(**{**run, "coefficients": tuple(run["coefficients"])}), document["stack"]


def _outcome(content: bytes, platform: AmpPlatform, run: AmpRun, stack: int) -> dict[str, Any]:
    """Admit one case as the image receipt does and return both outcomes.

    Parameters
    ----------
    content
        Changed firmware image.
    platform
        Platform.
    run
        Run.
    stack
        Stack bytes.

    Returns
    -------
    dict[str, Any]
        ``contract`` and ``exit`` outcomes.
    """
    try:
        segments = admit_image_contract(content, platform, run, stack)
    except ValueError as error:
        return {"contract": {"refusal": str(error)}, "exit": None}
    contract = {"segments": [asdict(segment) for segment in segments]}
    try:
        admit_exit_channel(content, segments, isa=True)
    except ValueError as error:
        return {"contract": contract, "exit": {"refusal": str(error)}}
    return {"contract": contract, "exit": "admitted"}


def corpus(directory: Path) -> dict[str, Any]:
    """Bind the platform, admit every case and return the corpus.

    Parameters
    ----------
    directory
        Owned directory for the compiler's files.

    Returns
    -------
    dict[str, Any]
        The inputs and the cases with their outcomes.
    """
    content = _firmware()
    tree = decode_device_tree(_compile(SOURCE, directory, force=False))
    platform = bind_platform(tree, MEMORY_SELECTION, PATH, PLIC_SELECTION)
    inputs = _inputs(platform)
    cases: dict[str, Case] = {}
    for group in (_symbol_cases, _constant_cases, _input_cases, _stack_cases, _exit_cases):
        cases |= group(content)
    return {
        "schema": "loop-timing-witness.amp-image-contract-cases.v1",
        "description": (
            "Python's admit_image_contract and ISA admit_exit_channel on the firmware of "
            "amp-elf-cases.json. A case applies [offset, hex] edits to the image and [path, value] "
            "changes to inputs; contract is the segments as dataclasses.asdict writes them or the "
            "refusal; exit is admitted, the refusal, or null where the contract refused."
        ),
        "firmware_sha256": DIGESTS["firmware"],
        "inputs": inputs,
        "cases": [
            {
                "name": name,
                "edits": edits,
                "changes": changes,
                **_outcome(_apply(content, edits), *_changed(inputs, changes)),
            }
            for name, (edits, changes) in cases.items()
        ],
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
    """Rebuild the corpus with the real ``dtc`` and Python's admission; require the committed file.

    Parameters
    ----------
    tmp_path
        Owned directory for the compiler's files.
    """
    assert CORPUS.read_text(encoding="utf-8") == _text(corpus(tmp_path))
    assert CORPUS.with_name(CORPUS.name + ".license").is_file()
