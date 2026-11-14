# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — declared host timeout scales shared with the native tests

"""Hold the native tests' reading of the host timeout scale to the Python module.

The corpus lists declarations of ``WITNESS_HOST_TIMEOUT_SCALE``, absent ones
included, with the scale and the ten-second guard in whole seconds that
``loop_timing_witness.host_profile`` derives, or its refusal. The native
integration tests read the same file and require the same outcomes.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Final

from conftest import REPOSITORY_ROOT
from loop_timing_witness.host_profile import SCALE_VARIABLE, scaled_seconds, timeout_scale

if TYPE_CHECKING:
    import pytest

CORPUS: Final = REPOSITORY_ROOT / "analysis/rust/tests/data/host-timeout-scales.json"
DECLARATIONS: Final = (
    None,
    "1",
    "2",
    "0.5",
    "0.25",
    "1e-3",
    "1E+2",
    "+2",
    "2.",
    ".5",
    "0.1",
    "3.3333333333333335",
    "1e-300",
    "1e15",
    "0",
    "-0",
    "-1",
    "1e-400",
    "1e400",
    "nan",
    "NaN",
    "inf",
    "infinity",
    "",
    " 2",
    "2 ",
    "2\n",
    "1_0",
    "0x10",
    "two",
    chr(0x661),
    "1e",
    ".",
    "e5",
    "--2",
    "+-2",
    "1.2.3",
)


def _outcome(monkeypatch: pytest.MonkeyPatch, declared: str | None) -> dict[str, Any]:
    """Return what the Python module derives from one declaration.

    Parameters
    ----------
    monkeypatch
        Environment fixture.
    declared
        Declared scale text, or ``None`` when the variable is absent.

    Returns
    -------
    dict[str, Any]
        The declaration with its scale as Python's ``repr`` and the ten-second
        guard in whole seconds, or with its refusal.
    """
    if declared is None:
        monkeypatch.delenv(SCALE_VARIABLE, raising=False)
    else:
        monkeypatch.setenv(SCALE_VARIABLE, declared)
    try:
        scale = timeout_scale()
    except ValueError as error:
        return {"declared": declared, "refusal": str(error)}
    return {"declared": declared, "scale": repr(scale), "ten_seconds": scaled_seconds(10)}


def test_committed_corpus_equals_python_outcomes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rebuild the corpus with the Python module and require the committed file.

    Parameters
    ----------
    monkeypatch
        Environment fixture.
    """
    document = {
        "schema": "loop-timing-witness.host-timeout-scales.v1",
        "description": (
            "WITNESS_HOST_TIMEOUT_SCALE declarations (null when absent) with Python's repr of "
            "the scale and the ten-second guard in whole seconds rounded up, or the refusal."
        ),
        "cases": [_outcome(monkeypatch, declared) for declared in DECLARATIONS],
    }
    text = json.dumps(document, ensure_ascii=True, indent=1, sort_keys=True) + "\n"
    assert CORPUS.read_text(encoding="utf-8") == text
    assert CORPUS.with_name(CORPUS.name + ".license").is_file()
