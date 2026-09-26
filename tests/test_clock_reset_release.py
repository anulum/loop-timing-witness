# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — reset release tests

"""Verify asynchronous assertion and clock-dependent reset release."""

from __future__ import annotations

import subprocess
from collections.abc import Callable

RunRtl = Callable[[str, dict[str, int], list[str]], subprocess.CompletedProcess[str]]


def test_reset_assertion_and_stopped_clock_release(run_rtl: RunRtl) -> None:
    """Require two local rising edges before release, even after a clock stop.

    Parameters
    ----------
    run_rtl
        Real compiler and simulator runner.
    """
    result = run_rtl("clock_reset_release_tb", {}, [])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RESET_RELEASE_PASS" in result.stdout
