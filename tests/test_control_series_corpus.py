# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — shared CSV, decimal and series corpora for the native analysis

"""Build the CSV, decimal and series corpora from Python and hold them committed.

``control-csv-cases.json`` holds texts with the records ``csv.reader`` gives
and the error that stops it. ``control-series-cases.json`` holds measurement
and count cells with Python's values or refusals, decimal operations with
their exact results, and tracking, observed tracking and energy series with
Python's metrics or refusals. The native crate's unit tests read both files.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final

from conftest import REPOSITORY_ROOT
from loop_timing_witness.event_stream import Event
from loop_timing_witness.manifest_io import load_json_object
from loop_timing_witness.run_series import count, energy_per_cycle, measurement, tracking_error
from loop_timing_witness.tracking_observations import observed_tracking_error

DATA: Final = REPOSITORY_ROOT / "analysis/rust/tests/data"
CSV_CORPUS: Final = DATA / "control-csv-cases.json"
SERIES_CORPUS: Final = DATA / "control-series-cases.json"
RAILS: Final = load_json_object(REPOSITORY_ROOT / "measurement-domain.json")["design_contracts"][
    "power_rails"
]
LIMIT: Final = csv.field_size_limit()
RUN: Final = 1000

if TYPE_CHECKING:
    from collections.abc import Sequence


class _Values:
    """Deterministic pseudo-random values: SHA-256 of a seed and a counter."""

    def __init__(self, seed: str) -> None:
        """Start a stream.

        Parameters
        ----------
        seed
            Stream name.
        """
        self._seed = seed
        self._count = 0

    def _next(self) -> int:
        """Return the next 64-bit value.

        Returns
        -------
        int
            Value below 2**64.
        """
        self._count += 1
        digest = hashlib.sha256(f"{self._seed}:{self._count}".encode()).digest()
        return int.from_bytes(digest[:8], "big")

    def randint(self, low: int, high: int) -> int:
        """Return an integer from ``low`` to ``high`` inclusive.

        Parameters
        ----------
        low
            Smallest value.
        high
            Largest value.

        Returns
        -------
        int
            Value.
        """
        return low + self._next() % (high - low + 1)

    def choice[T](self, items: Sequence[T]) -> T:
        """Return one item.

        Parameters
        ----------
        items
            Nonempty sequence.

        Returns
        -------
        T
            Item.
        """
        return items[self._next() % len(items)]

    def random(self) -> float:
        """Return a float in [0, 1).

        Returns
        -------
        float
            Value.
        """
        return self._next() / 2**64

    def uniform(self, low: float, high: float) -> float:
        """Return a float from ``low`` towards ``high``.

        Parameters
        ----------
        low
            Lower end.
        high
            Upper end.

        Returns
        -------
        float
            Value.
        """
        return low + (high - low) * self.random()


def _records(text: str) -> dict[str, Any]:
    """Return every record of a text and the error that stops the reader.

    Parameters
    ----------
    text
        Decoded CSV text.

    Returns
    -------
    dict[str, Any]
        Records read before any error, and the error text or ``None``.
    """
    records: list[list[str]] = []
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        records.extend(reader)
    except csv.Error as error:
        return {"text": text, "records": records, "error": str(error)}
    return {"text": text, "records": records, "error": None}


def csv_corpus() -> dict[str, Any]:
    """Return the CSV corpus.

    Returns
    -------
    dict[str, Any]
        Texts with their records and stopping errors.
    """
    texts = [
        "",
        "a",
        "a,b\n",
        "a,b\r\nc,d\r\n",
        "a\rb\rc",
        "\n\n\r\n",
        "a,\n,b\n,\n",
        '"a,b",c\n',
        '"a""b"\n',
        '"a\nb",c\r\nd\n',
        '"a\r\nb"\n',
        '""\n',
        '"',
        '"abc',
        '"a"b\n',
        '"a" ,b\n',
        'a"b,c"d\n',
        '"a"\r',
        "a\r\n\r\nb",
        "é,ü\n",
        "x" * LIMIT + "\n",
        "x" * (LIMIT + 1) + "\n",
        '"' + "y" * LIMIT + '"\n',
        '"' + "y" * (LIMIT - 1) + '""z"\n',
        "\x00,\x0b\x0c\x1c\x85" + chr(0x2028) + "\n",
    ]
    cases = [_packed(_records(text)) for text in texts]
    return {"schema": "loop-timing-witness.control-csv-cases.v1", "cases": cases}


def _packed(value: object) -> object:
    """Return a value with every long run of one character written as a run.

    Parameters
    ----------
    value
        Case value: text, list or object.

    Returns
    -------
    object
        The value, with each string holding a run of at least 1000 equal
        characters written as ``{"prefix", "repeat", "count", "suffix"}``.
    """
    if isinstance(value, dict):
        return {key: _packed(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_packed(item) for item in value]
    if isinstance(value, str):
        for start, character in enumerate(value):
            end = start
            while end < len(value) and value[end] == character:
                end += 1
            if end - start >= RUN:
                return {
                    "prefix": value[:start],
                    "repeat": character,
                    "count": end - start,
                    "suffix": value[end:],
                }
    return value


def _canonical(value: Decimal) -> list[Any]:
    """Return a value as sign, digits and exponent with trailing zeros removed.

    Parameters
    ----------
    value
        Exact decimal.

    Returns
    -------
    list[Any]
        ``[negative, digits, exponent]`` of the normalised value.
    """
    sign, digits, exponent = value.normalize().as_tuple()
    return [bool(sign) and value != 0, "".join(map(str, digits)), int(exponent)]


def _cells(generator: _Values) -> list[str]:
    """Return measurement cells covering every form, bound and refusal.

    Parameters
    ----------
    generator
        Seeded random source.

    Returns
    -------
    list[str]
        Cells.
    """
    fixed = [
        "0",
        "-0",
        "+0.000e-900",
        "00012.5000",
        ".5",
        "5.",
        "1e99",
        "9.999e99",
        "1e100",
        "1e-99",
        "0.99e-99",
        "9" * 28,
        "9" * 29,
        "1" + "0" * 60 + "e-60",
        "1.5e+0000005",
        "1e1000000",
        "1e1234567890123456789",
        "1e-0999999",
        "-1E-5",
        "NaN",
        "-sNaN7",
        "+Infinity",
        "inf",
        "nan0x",
        " 1",
        "1_0",
        "1e",
        ".",
        "e1",
        "+",
        "1.2.3",
        "1e+-1",
        chr(0x661),
    ]
    digits = "0123456789"
    produced = []
    for _ in range(60):
        whole = "".join(generator.choice(digits) for _ in range(generator.randint(0, 16)))
        fraction = "".join(generator.choice(digits) for _ in range(generator.randint(0, 16)))
        text = generator.choice(["", "-", "+"]) + (whole or "0") + "." + fraction
        if generator.random() < 0.5:
            text += f"e{generator.randint(-110, 110)}"
        produced.append(text)
    return fixed + produced


def _decimal_cases(generator: _Values) -> dict[str, Any]:
    """Return measurement, count and arithmetic cases.

    Parameters
    ----------
    generator
        Seeded random source.

    Returns
    -------
    dict[str, Any]
        Cells with values or refusals, counts, and operations with results.
    """
    measurements: list[dict[str, Any]] = []
    values: list[Decimal] = []
    for cell in _cells(generator):
        try:
            value = measurement(cell, "value")
        except ValueError as error:
            measurements.append({"cell": cell, "refusal": str(error)})
        else:
            measurements.append({"cell": cell, "value": _canonical(value)})
            values.append(value)
    counts: list[dict[str, Any]] = []
    for cell in ["0", "007", "18446744073709551615", "18446744073709551616", "1" * 21, "-1", ""]:
        try:
            counts.append({"cell": cell, "value": count(cell, "cycle")})
        except ValueError as error:
            counts.append({"cell": cell, "refusal": str(error)})
    ties = [
        (Decimal(1234567890123456789012345678), Decimal("0.5")),
        (Decimal(1234567890123456789012345677), Decimal("0.5")),
        (Decimal(9999999999999999999999999999), Decimal("0.5")),
        (Decimal(1234567890123456789012345678), Decimal("0.5000000000001")),
        (Decimal(1234567890123456789012345678), Decimal("-0.5")),
        (Decimal("1e99"), Decimal("-1e-99")),
        (Decimal(0), Decimal(0)),
    ]
    pairs = ties + [(generator.choice(values), generator.choice(values)) for _ in range(40)]
    operations = []
    for left, right in pairs:
        divisor = generator.choice([1, 2, 3, 7, 10, 1000003, 2**53 + 1, 2**64 - 1])
        operations.append(
            {
                "left": _canonical(left),
                "right": _canonical(right),
                "divisor": divisor,
                "sum": _canonical(left + right),
                "difference": _canonical(left - right),
                "product": _canonical(left * right),
                "quotient": _canonical(abs(left) / divisor),
                "float": float(abs(left) / divisor),
            }
        )
    divisions = []
    for value, divisor in (
        (Decimal(5), 63),
        (Decimal(5), 77),
        (Decimal(2000000000000000000000000001), 2),
        (Decimal(2000000000000000000000000003), 2),
        (Decimal(1), 3),
    ):
        quotient = value / divisor
        divisions.append([_canonical(value), divisor, _canonical(quotient), float(quotient)])
    return {
        "measurements": measurements,
        "counts": counts,
        "operations": operations,
        "divisions": divisions,
    }


def _tracking_text(rows: Sequence[tuple[object, object, object]]) -> str:
    """Return a tracking table.

    Parameters
    ----------
    rows
        Cycle, reference and output cells.

    Returns
    -------
    str
        CSV text with the tracking header.
    """
    body = "".join(f"{cycle},{reference},{output}\n" for cycle, reference, output in rows)
    return "cycle,reference,output\n" + body


def _power_text(samples: list[tuple[int, list[float]]]) -> str:
    """Return a power table with one row per rail and sample.

    Parameters
    ----------
    samples
        Tick and cumulative energy per rail.

    Returns
    -------
    str
        CSV text with the power header.
    """
    rows = [
        f"{ticks},{rail},1.0,0.5,{energy}\n"
        for ticks, energies in samples
        for rail, energy in zip(RAILS, energies, strict=True)
    ]
    return "timebase_ticks,rail,voltage_v,current_a,energy_j\n" + "".join(rows)


def _events(cycles: int, period: int, read: tuple[int, ...] = ()) -> list[list[Any]]:
    """Return anchor and sample-read events.

    Parameters
    ----------
    cycles
        Number of cycles.
    period
        Ticks between cycle anchors.
    read
        Cycles with a SAMPLE_READ event.

    Returns
    -------
    list[list[Any]]
        ``[name, cycle, ticks]`` events.
    """
    events = []
    for cycle in range(cycles):
        events.append(["SAMPLE_READY", cycle, period * cycle + 10])
        events.append(["INPUT_WRITE", cycle, period * cycle + 20])
        if cycle in read:
            events.append(["SAMPLE_READ", cycle, period * cycle + 30])
    return events


def _tracking_cases(generator: _Values) -> list[dict[str, Any]]:
    """Return tracking cases with inputs.

    Parameters
    ----------
    generator
        Seeded random source.

    Returns
    -------
    list[dict[str, Any]]
        Content, cycle count and warm-up of each case.
    """
    random_rows = [
        (cycle, f"{generator.uniform(-5, 5):.9f}", f"{generator.uniform(-5, 5):.12f}")
        for cycle in range(40)
    ]
    texts = {
        "complete": _tracking_text([(0, 1, "0.9"), (1, 2, "1.8"), (2, 3, "2.7")]),
        "random": _tracking_text(random_rows),
        "warm-up only gap": _tracking_text([(1, 1, "0.5"), (2, 2, "2.25")]),
        "reordered": _tracking_text([(2, "1e-99", 0), (0, "9.999e99", "-9.999e99"), (1, 0, 0)]),
        "ties": _tracking_text([(0, "1234567890123456789012345678", "0.5"), (1, 1, 1), (2, 0, 0)]),
        "missing": _tracking_text([(0, 1, 1), (2, 1, 1)]),
        "duplicate": _tracking_text([(0, 1, 1), (0, 1, 1)]),
        "outside": _tracking_text([(3, 1, 1)]),
        "wide cycle": _tracking_text([("18446744073709551616", 1, 1)]),
        "cycle text": _tracking_text([("x", 1, 1)]),
        "range": _tracking_text([(0, "1e100", 1)]),
        "finite": _tracking_text([(0, "nan", 1)]),
        "decimal": _tracking_text([(0, "1x", 1)]),
        "empty": "cycle,reference,output\n",
        "ragged": "cycle,reference,output\n0,1\n",
        "empty cell": "cycle,reference,output\n0,,1\n",
        "header": "cycle,output,reference\n0,1,1\n",
        "no text": "",
        "quote": '"cycle,reference,output\n',
        "row quote": 'cycle,reference,output\n0,"1"x,1\n',
        "not utf-8": chr(0xDCFF),
    }
    return [
        {"name": name, "content": text, "cycle_count": 3, "warmup_cycles": warmup}
        for name, text in texts.items()
        for warmup in ((0, 1) if name in {"complete", "warm-up only gap"} else (0,))
    ] + [{"name": "random", "content": texts["random"], "cycle_count": 40, "warmup_cycles": 5}]


def _encoded(text: str) -> bytes:
    """Return the bytes of a case text; a lone surrogate stands for byte 0xff.

    Parameters
    ----------
    text
        Case text.

    Returns
    -------
    bytes
        Series bytes.
    """
    return text.encode("utf-8", "surrogateescape")


def _undecodable(text: str) -> bool:
    """Tell whether a case text stands for bytes that are not UTF-8.

    Parameters
    ----------
    text
        Case text, with a lone surrogate for an undecodable byte.

    Returns
    -------
    bool
        Whether the text cannot be written as UTF-8.
    """
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return True
    return False


def _tracked(case: dict[str, Any], kind: str) -> dict[str, Any]:
    """Return one tracking or observed tracking entry with Python's outcome.

    Parameters
    ----------
    case
        Content, cycle count and warm-up.
    kind
        ``tracking`` or ``observed``.

    Returns
    -------
    dict[str, Any]
        The case with its result or refusal, and events for observed tracking.
    """
    entry = {"kind": kind, **case}
    content = _encoded(case["content"])
    events = _events(case["cycle_count"], 100, read=(0, 1, 2))
    try:
        if kind == "tracking":
            entry["result"] = tracking_error(
                content, case["cycle_count"], case["warmup_cycles"], "rad"
            )
        else:
            entry["events"] = events
            entry["result"] = observed_tracking_error(
                content,
                tuple(Event(*event) for event in events),
                case["cycle_count"],
                case["warmup_cycles"],
                "rad",
            )
    except ValueError as error:
        entry["refusal"] = str(error)
    return entry


def _observed_cases() -> list[dict[str, Any]]:
    """Return observed tracking cases with partial, empty and mismatched reads.

    Returns
    -------
    list[dict[str, Any]]
        Cases with Python's results or refusals.
    """
    observed = {
        "partial": (_tracking_text([(0, 1, "0.5"), (2, 1, "0.25")]), (0, 2), 1),
        "none after warm-up": (_tracking_text([(0, 1, "0.5")]), (0,), 1),
        "header only": ("cycle,reference,output\n", (), 0),
        "mismatch": (_tracking_text([(0, 1, "0.5")]), (0, 1), 0),
    }
    cases = []
    for name, (text, read, warmup) in observed.items():
        events = _events(3, 100, read=read)
        entry: dict[str, Any] = {
            "kind": "observed",
            "name": name,
            "content": text,
            "cycle_count": 3,
            "warmup_cycles": warmup,
            "events": events,
        }
        try:
            entry["result"] = observed_tracking_error(
                _encoded(text), tuple(Event(*event) for event in events), 3, warmup, "rad"
            )
        except ValueError as error:
            entry["refusal"] = str(error)
        cases.append(entry)
    return cases


def series_corpus() -> dict[str, Any]:
    """Return the decimal and series corpus.

    Returns
    -------
    dict[str, Any]
        Decimal cases and series cases with Python's results or refusals.
    """
    generator = _Values("control-series-2026-11-09")
    cases = [
        _tracked(case, kind)
        for case in _tracking_cases(generator)
        for kind in ("tracking", "observed")
    ]
    cases.append(
        {
            "kind": "tracking",
            "name": "absent",
            "content": None,
            "cycle_count": 3,
            "warmup_cycles": 0,
            "result": tracking_error(None, 3, 0, "rad"),
        }
    )
    cases.extend(_observed_cases())
    cases.extend(_energy_cases(generator))
    for case in cases:
        if isinstance(case["content"], str) and _undecodable(case["content"]):
            case["content"] = {"hex": _encoded(case["content"]).hex()}
    return {
        "schema": "loop-timing-witness.control-series-cases.v1",
        "rails": RAILS,
        "decimal": _decimal_cases(generator),
        "cases": cases,
    }


def _energy_cases(generator: _Values) -> list[dict[str, Any]]:
    """Return energy cases with Python's results or refusals.

    Parameters
    ----------
    generator
        Seeded random source.

    Returns
    -------
    list[dict[str, Any]]
        Power content, events, profile and warm-up of each case.
    """
    rails = len(RAILS)
    steady = [
        (tick, [0.001 * tick * (rail + 1) for rail in range(rails)]) for tick in (0, 250, 500)
    ]
    noisy = []
    energies = [0.0] * rails
    for tick in range(0, 1100, 50):
        energies = [energy + generator.uniform(0, 1e-3) for energy in energies]
        noisy.append((tick, [round(energy, 15) for energy in energies]))
    header = "timebase_ticks,rail,voltage_v,current_a,energy_j\n"
    texts = {
        "steady": (_power_text(steady), 0),
        "noisy": (_power_text(noisy), 0),
        "noisy warm-up": (_power_text(noisy), 1),
        "warm-up overlap": (_power_text([(0, [0] * rails), (500, [1] * rails)]), 1),
        "decreasing": (_power_text([(0, [1] * rails), (500, [0.5] * rails)]), 0),
        "uncovered": (_power_text([(0, [0] * rails), (150, [1] * rails)]), 0),
        "single sample": (_power_text([(0, [0] * rails)]), 0),
        "unknown rail": (header + "0,NOPE,1,1,0\n", 0),
        "repr rail": (header + "0,'a\"\\\x01,1,1,0\n", 0),
        "duplicate rail": (header + f"0,{RAILS[0]},1,1,0\n0,{RAILS[0]},1,1,0\n", 0),
        "negative": (header + f"0,{RAILS[0]},1,-1,0\n", 0),
        "range": (header + f"0,{RAILS[0]},1e100,1,0\n", 0),
        "ticks": (header + f"x,{RAILS[0]},1,1,0\n", 0),
        "incomplete": (_power_text([(0, [0] * rails)]) + f"500,{RAILS[0]},1,1,1\n", 0),
        "warm-up aligned": (_power_text([(110, [0] * rails), (1100, [1] * rails)]), 1),
        "no anchors": (_power_text([(0, [0] * rails), (500, [1] * rails)]), 0),
        "anchor boundary": (
            _power_text([(0, [0] * rails), (510, [1] * rails), (1100, [2] * rails)]),
            0,
        ),
    }
    cases: list[dict[str, Any]] = []
    for name, (text, warmup) in texts.items():
        for profile in ("CONTROL", "COMPUTE"):
            events = [] if name == "no anchors" else _events(10, 100)
            entry: dict[str, Any] = {
                "kind": "energy",
                "name": name,
                "content": text,
                "profile": profile,
                "warmup_cycles": warmup,
                "events": events,
            }
            try:
                entry["result"] = energy_per_cycle(
                    _encoded(text),
                    tuple(Event(*event) for event in events),
                    profile,
                    warmup,
                    RAILS,
                )
            except ValueError as error:
                entry["refusal"] = str(error)
            cases.append(entry)
    cases.append(
        {
            "kind": "energy",
            "name": "absent",
            "content": None,
            "profile": "CONTROL",
            "warmup_cycles": 0,
            "events": [],
            "result": energy_per_cycle(None, (), "CONTROL", 0, RAILS),
        }
    )
    return cases


def _text(corpus: dict[str, Any]) -> str:
    """Return the committed form of a corpus.

    Parameters
    ----------
    corpus
        Corpus object.

    Returns
    -------
    str
        Compact sorted ASCII JSON with a final newline.
    """
    return json.dumps(corpus, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"


def test_committed_csv_corpus_equals_python_records() -> None:
    """The committed CSV corpus is exactly what Python's reader gives."""
    assert CSV_CORPUS.read_text(encoding="utf-8") == _text(csv_corpus())


def test_committed_series_corpus_equals_python_series() -> None:
    """The committed series corpus is exactly what Python's series analysis gives."""
    assert SERIES_CORPUS.read_text(encoding="utf-8") == _text(series_corpus())


def test_corpora_cover_every_refusal() -> None:
    """Hold each CSV error and each series refusal text."""
    errors = {case["error"] for case in csv_corpus()["cases"]}
    assert errors == {
        None,
        "unexpected end of data",
        "',' expected after '\"'",
        f"field larger than field limit ({LIMIT})",
    }
    refusals = {case["refusal"] for case in series_corpus()["cases"] if "refusal" in case}
    expected_parts = [
        "series file is not UTF-8",
        "observed tracking file is not UTF-8",
        "CSV header must be",
        "observed tracking CSV header must be",
        "invalid CSV: unexpected end of data",
        "invalid observed tracking CSV: ',' expected",
        "CSV has no data or contains an incomplete row",
        "observed tracking contains an incomplete row",
        "must be a nonnegative decimal integer",
        "must be below 2**64",
        "duplicated or outside the run",
        "lacks an analysed cycle",
        "is outside the supported decimal range",
        "must be finite",
        "is not a decimal",
        "do not match captured SAMPLE_READ events",
        "is unknown or duplicated at tick",
        "cannot be negative",
        "at least two complete four-rail samples",
        "overlaps discarded warm-up cycles",
        "cumulative energy decreases",
        "do not cover every analysed cycle",
    ]
    for part in expected_parts:
        assert any(part in refusal for refusal in refusals), part
    for name in (CSV_CORPUS, SERIES_CORPUS):
        assert name.with_name(name.name + ".license").is_file()
