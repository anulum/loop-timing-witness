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

- Fabric timebase and dual-clock event witness with known-period, overflow, saturation, reset,
  pointer-wrap and configured-capacity simulations; the drain stream reaches the host reports.
  Physical CDC timing, RAM mapping and board acceptance remain unqualified.

- Mechanical and thermal Q8.24 plants, step/ramp/sine references, strict deadline monitor,
  latched safe actuator and drop/delay/freeze/overload-request injector, integrated with
  simultaneous event capture and the buffered host report path. Injected delay is verified
  in simulation; processor overload execution and physical acceptance remain unqualified.

- C, Rust and RTL Q8.24 PID with conditional integration and discrete LQR, integrated
  fabric feedback and native command replay through the drained host report path.
  Full-range arithmetic, reset/refusal, 64,000-sample trajectories and independent
  fault handling are verified in simulation. Native kernels and streaming CLIs
  have complete line/branch coverage; matching native benchmark records establish
  local regression evidence only. See [`docs/CONTROLLERS.md`](docs/CONTROLLERS.md).
  Completed locally on 2026-09-26; the atomic controller commit records the implementation.

## Planned — in implementation order, without dates

1. Vendor tool project generation scripts and constraints.
2. Linux run controller, UIO access and power-monitor logger.
3. Bare-metal controller on a dedicated application core.
4. Instrument acceptance on the board (known period, injected delay, overflow, bus-offset floor),
   then measured runs with manifests; evidence maturity advances only at this step.
   Blocked: no physical board is available; simulation does not close this item.

## Not planned in this repository

Accelerator-library adapters, controllers or plant models from other projects, redistribution of
vendor tools or IP, comparisons with other vendors, and any statement about platform performance
without a measured run.
