// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — run loading, crate-internal controls

//! Accept and refuse the same `started_utc` spellings as the Python rule.

use super::utc_timestamp;

#[test]
fn utc_timestamps_follow_the_python_rule() {
    for accepted in [
        "2026-09-26T00:00:00Z",
        "2026-09-26t00:00:00z",
        "2026-09-26T00:00:00+00:00",
        "2026-09-26T00:00:00-00:00",
        "2026-09-26T00:00:00.123456789Z",
        "2024-02-29T23:59:59Z",
        "2000-02-29T00:00:00Z",
        "0001-01-01T00:00:00Z",
    ] {
        assert!(utc_timestamp(accepted), "{accepted}");
    }
    for refused in [
        "2026-09-26T02:00:00+02:00",
        "2026-09-26T00:00:60Z",
        "2026-02-30T00:00:00Z",
        "1900-02-29T00:00:00Z",
        "2026-04-31T00:00:00Z",
        "2026-13-01T00:00:00Z",
        "2026-00-01T00:00:00Z",
        "0000-01-01T00:00:00Z",
        "2026-09-26T24:00:00Z",
        "2026-09-26T00:60:00Z",
        "2026-09-26T00:00Z",
        "2026-09-26T00:00:00Z\n",
        "2026-09-26 00:00:00Z",
        "2026-09-26T00:00:00.Z",
        "2026-09-26T00:00:00",
        "2026/09/26T00:00:00Z",
        "2026-09/26T00:00:00Z",
        "2026-09-26T00-00:00Z",
        "2026-09-26T00:00-00Z",
        "20x6-09-26T00:00:00Z",
    ] {
        assert!(!utc_timestamp(refused), "{refused}");
    }
}
