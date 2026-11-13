# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — AMP plugin build schema locations shared with the native analysis

"""Keep the AMP plugin build receipt's schema-location corpus.

The base document is a real plugin build receipt, reduced to the fewest
entries its schema and cross-checks admit and with its build root written
``/build`` (``tests/data/amp-plugin-build-reduced.json``). Every node of it is
changed as the run manifest corpus changes its nodes, and each change records
the locations Python's validator reports against the committed schema, which
uses local references, ``maxProperties`` and ``propertyNames``. One more change
gives the six link inputs a seventh valid one, so that only ``maxProperties``
fails. The native crate's unit tests read the same committed file.
"""

from __future__ import annotations

import json
from typing import Any, Final

from test_control_schema_corpus import apply, cases_of

from conftest import REPOSITORY_ROOT
from loop_timing_witness.manifest_io import load_json_object
from loop_timing_witness.validate_measurement_domain import schema_locations

BASE: Final = REPOSITORY_ROOT / "tests/data/amp-plugin-build-reduced.json"
SCHEMA: Final = REPOSITORY_ROOT / "amp-plugin-build.schema.json"
CORPUS: Final = REPOSITORY_ROOT / "analysis/rust/tests/data/amp-plugin-schema-locations.json"


def corpus() -> dict[str, Any]:
    """Build the plugin build schema-location corpus.

    Returns
    -------
    dict[str, Any]
        The base receipt and one group of changes per node.
    """
    base = load_json_object(BASE)
    schema = load_json_object(SCHEMA)
    groups = cases_of("plugin", base, schema, 99)
    seventh = {"set": {**base["link_inputs"], "/build/plugin/extra.o": "0" * 64}}
    mutated = apply(base, ["link_inputs"], seventh)
    assert isinstance(mutated, dict)
    locations = schema_locations(mutated, schema)
    groups.append({"base": "plugin", "path": ["link_inputs"], "changes": [[seventh, locations]]})
    return {
        "schema": "loop-timing-witness.amp-plugin-schema-locations.v1",
        "bases": {"plugin": base},
        "plugin": groups,
    }


def _text() -> str:
    """Return the committed text form of the corpus.

    Returns
    -------
    str
        Compact sorted JSON and a final newline.
    """
    return json.dumps(corpus(), ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"


def test_committed_corpus_equals_python_locations() -> None:
    """The committed corpus is exactly what Python reports for every change."""
    assert CORPUS.read_text(encoding="utf-8") == _text()
    assert CORPUS.with_name(CORPUS.name + ".license").is_file()


def test_corpus_reaches_the_plugin_schema_constructs() -> None:
    """The valid receipt passes, most changes fail, and the bounded maps reach both bounds."""
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    groups = data["plugin"]
    assert groups[0]["path"] == []
    assert groups[0]["changes"][0] == [None, []]
    changed = [pair for group in groups for pair in group["changes"] if pair[0] is not None]
    failing = [locations for _, locations in changed if locations]
    assert len(failing) > 0.8 * len(changed)
    link, seventh = [group for group in groups if group["path"] == ["link_inputs"]]
    removed = [locations for change, locations in link["changes"] if "remove" in change]
    assert len(removed) == 6
    assert all(locations == ["link_inputs"] for locations in removed)
    assert seventh["changes"][0][1] == ["link_inputs"]
