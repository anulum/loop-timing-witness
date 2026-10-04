# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — installed public analysis API

"""Hash-bound timing, tracking and power analysis for Loop Timing Witness.

Manifest utilities load independently of analysis and schema validation.
The public analysis exports are resolved when they are first requested.
"""

from __future__ import annotations

from importlib import import_module as _import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .analyze_run import build_report
    from .run_manifest import RunInputs, load_run

__all__ = ["RunInputs", "build_report", "load_run"]

_EXPORT_MODULES = {
    "RunInputs": ".run_manifest",
    "build_report": ".analyze_run",
    "load_run": ".run_manifest",
}


def __getattr__(name: str) -> object:
    """Resolve and retain one public analysis export.

    Parameters
    ----------
    name
        Public export requested through normal module attribute access.

    Returns
    -------
    object
        Original run-input class or analysis function from its owning module.

    Raises
    ------
    AttributeError
        The name is not part of the public analysis interface.
    """
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        message = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(message)
    value: object = getattr(_import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Include unresolved public exports in module introspection.

    Returns
    -------
    list[str]
        Sorted module attributes, including the complete public interface.
    """
    return sorted(set(globals()) | set(__all__))
