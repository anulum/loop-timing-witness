# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — series value rules and receipt refusal texts

"""Check the measurement and count rules and the authored refusal texts."""

from __future__ import annotations

from decimal import Decimal

import pytest

from loop_timing_witness.host_load_receipt import validate_host_load
from loop_timing_witness.native_completion import completion_statistics
from loop_timing_witness.run_series import count, measurement, tracking_error
from loop_timing_witness.tracking_observations import observed_tracking_error


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("0", Decimal(0)),
        ("-0.000e-500", Decimal("-0")),
        ("+12.5e3", Decimal(12500)),
        (".5", Decimal("0.5")),
        ("5.", Decimal(5)),
        ("9" * 28, Decimal("9" * 28)),
        ("1" + "0" * 40 + "e-40", Decimal(1)),
        ("9.99e99", Decimal("9.99e99")),
        ("1e-99", Decimal("1e-99")),
        ("0." + "0" * 98 + "1", Decimal("1e-99")),
    ],
)
def test_measurement_accepts_plain_values_in_range(text: str, value: Decimal) -> None:
    """Plain ASCII decimals within the digit and magnitude bounds are exact.

    Parameters
    ----------
    text
        CSV cell.
    value
        Expected exact value.
    """
    assert measurement(text, "output") == value


@pytest.mark.parametrize(
    ("text", "refusal"),
    [
        ("NaN", "output must be finite"),
        ("-infinity", "output must be finite"),
        ("sNaN12", "output must be finite"),
        (chr(0x17F) + "nan", "output is not a decimal"),
        (" 1", "output is not a decimal"),
        ("1_000", "output is not a decimal"),
        (chr(0x661), "output is not a decimal"),
        ("1e", "output is not a decimal"),
        (".", "output is not a decimal"),
        ("1e100", "output is outside the supported decimal range"),
        ("1e-100", "output is outside the supported decimal range"),
        ("1" * 29, "output is outside the supported decimal range"),
        ("1e1000000", "output is outside the supported decimal range"),
        ("1e-0000001000000", "output is outside the supported decimal range"),
    ],
)
def test_measurement_refuses_other_forms(text: str, refusal: str) -> None:
    """Whitespace, separators, non-ASCII digits and out-of-range values are refused.

    Parameters
    ----------
    text
        CSV cell.
    refusal
        Expected refusal text.
    """
    with pytest.raises(ValueError, match=f"^{refusal}$"):
        measurement(text, "output")


@pytest.mark.parametrize(
    ("text", "outcome"),
    [
        ("0", 0),
        ("000123", 123),
        ("0" * 200 + "18446744073709551615", 2**64 - 1),
        ("18446744073709551616", "cycle must be below 2**64"),
        ("1" * 21, "cycle must be below 2**64"),
        ("-1", "cycle must be a nonnegative decimal integer"),
        (chr(0x661), "cycle must be a nonnegative decimal integer"),
    ],
)
def test_count_bounds(text: str, outcome: int | str) -> None:
    """Counts are canonical ASCII integers below 2**64, leading zeros allowed.

    Parameters
    ----------
    text
        CSV cell.
    outcome
        Expected value or refusal text.
    """
    if isinstance(outcome, int):
        assert count(text, "cycle") == outcome
    else:
        with pytest.raises(ValueError, match=f"^{outcome.replace('*', '[*]')}$"):
            count(text, "cycle")


def test_damaged_header_is_a_refusal_in_both_readers() -> None:
    """A quoting error in the header is a refusal, not an uncaught CSV error."""
    damaged = b'"cycle,reference,output\n'
    with pytest.raises(ValueError, match=r"^invalid CSV: unexpected end of data$"):
        tracking_error(damaged, 3, 0, "rad")
    with pytest.raises(
        ValueError, match=r"^invalid observed tracking CSV: unexpected end of data$"
    ):
        observed_tracking_error(damaged, (), 3, 0, "rad")


def test_observed_tracking_must_be_utf8() -> None:
    """Undecodable observed tracking bytes have an authored refusal."""
    with pytest.raises(ValueError, match=r"^observed tracking file is not UTF-8$"):
        observed_tracking_error(b"\xff", (), 3, 0, "rad")


def test_receipt_schema_refusals_name_the_first_location() -> None:
    """Receipt schema refusals name a document location, not a library message."""
    with pytest.raises(
        ValueError, match=r"^host load receipt \(root\): does not satisfy the host load schema$"
    ):
        validate_host_load(b"{}")
    with pytest.raises(
        ValueError, match=r"^native metadata \(root\): does not satisfy the native run schema$"
    ):
        completion_statistics(b"{}", {}, 0, {})
