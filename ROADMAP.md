<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — roadmap
-->

# Roadmap

Implemented work and planned work are kept apart. Nothing under "Planned" exists in this
repository, and nothing is claimed for it until it appears in the capability inventory with its
evidence.

## Implemented — repository infrastructure, not instrument capability

- Measurement-domain manifest with JSON Schema and a validator for its cross-field consistency
  (event record layout, timebase counter width, event profiles and intervals, event buffer sizing,
  controller placements) and, in the canonical workspace, for its registry identity.
- Generated capability inventory, empty, with a byte-exact drift check.
- Hashed development lock with a reviewed licence record for every pinned package.
- Local gates: lint, formatting, strict typing, tests with complete statement and branch
  coverage, provenance headers, documentation links and anchors, workflow policy, REUSE licensing,
  workflow security analysis, workflow lint, typographical check and secret scan.
- Workflow definitions for correctness, pre-commit parity, code scanning, security audit,
  documentation, software inventory and supply-chain analysis. Hosted runs exist; their live
  conclusions must be checked at the exact commit being assessed.
- Architecture, measurement protocol, threat model and repository-boundary decision record.
- Versioned run manifest, hash-bound measurement-domain snapshot, simulation event capture and
  host analysis with JSON, CSV and SVG reports exercised from RTL-produced event files. This
  establishes a simulation tool path; it does not qualify a board instrument.

## Planned — in implementation order, without dates

1. Timebase and event witness in fabric logic, with simulation tests including the known-period
   and overflow tests.
2. Plant emulator, deadline and safe-state monitor and fault injector, with simulation tests
   including the injected-delay test.
3. Fabric and C controllers (PID with anti-windup, discrete LQR) with bit-exact fixed-point parity
   tests.
4. Vendor tool project generation scripts and constraints.
5. Linux run controller, UIO access and power-monitor logger.
6. Bare-metal controller on a dedicated application core.
7. Instrument acceptance on the board (known period, injected delay, overflow, bus-offset floor),
   then measured runs with manifests; evidence maturity advances only at this step.

## Not planned in this repository

Accelerator-library adapters, controllers or plant models from other projects, redistribution of
vendor tools or IP, comparisons with other vendors, and any statement about platform performance
without a measured run.
