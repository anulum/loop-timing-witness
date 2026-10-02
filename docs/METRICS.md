<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — download history and coverage metrics
-->

# Repository metrics

Codecov receives the verified Python host and repository-tool statement/branch
report from the main-branch CI run. The native C/Rust and RTL proofs have separate
denominators in [the coverage guide](CONTROLLER_COVERAGE.md); the Python badge does
not describe hardware acceptance or C++ compiler exception arcs.

The daily **PyPI downloads** workflow imports the public
[PyPIStats overall series](https://pypistats.org/api/) for `loop-timing-witness`.
It first verifies all seven source workflows at its exact source revision. Its
writer stores only `downloads/loop-timing-witness.csv` on the `metrics` branch;
source code and documentation remain on `main`. Checkout credentials are disabled,
and the write token is passed only to the final Git push.

The CSV contains ISO dates, `without_mirrors` and `with_mirrors` counts. It preserves
earlier snapshots beyond the provider's rolling history and upserts refreshed
dates. Dates with no `without_mirrors` observation retain an empty field. Missing
observations are never converted into zero downloads. A header-only history means
the provider has not supplied an observation yet.

404, rate limiting and server failures retain existing history. The scheduled
workflow explicitly permits that unavailable state and reports it. Malformed
identity, duplicate keys/pairs, invalid dates/counts, broken retained CSV and other
HTTP refusals fail without replacing established data. Updates use a flushed,
atomic file replacement; unchanged data produces no Git commit.

```bash
python tools/pypi_downloads.py --csv downloads/loop-timing-witness.csv
python tools/pypi_downloads.py --allow-missing --project-csv-only
```

An explicitly downloaded provider response can be imported with `--response FILE`.
An explicitly selected HTTP(S) endpoint can be supplied with `--url URL` for a
relay or transport verification. Such imports validate project identity and values;
their source remains the caller's responsibility. The hosted writer uses the fixed
official endpoint. Transport tests use actual owned HTTP and certificate-verified
TLS sockets; their declared test observations are never published as provider data.

Download badges require actual provider values. A new package may not appear in
PyPIStats immediately, and a blocked PePy endpoint does not establish a download
count. The sponsor link, package versions and coverage badge describe their own
services independently.
