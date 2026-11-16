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

Completed work and open work are kept apart. Open items may contain an implementation under
verification; they remain open until the whole item is verified and committed locally.
Software implementation does not qualify a board capability or advance measurement maturity.

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

- Native Linux PID/LQR run lifecycle, AXI register/IRQ transport, final event drain, UIO
  adapter and raw PAC1934 IIO journal, with exclusive outputs, configuration custody and
  scheduling metadata. Five owned host workload profiles feed source-bound simulation
  captures and host reports with explicit observed tracking coverage and live completion
  counters. Native and RV64 builds, simulation integration and actual host/device refusals
  are verified; successful physical MMIO, IRQ, IIO acquisition and energy-window alignment
  remain unqualified. See [`VALIDATION.md`](VALIDATION.md#native-linux-runtime-verification)
  for verification scope and coverage limits. Completed locally on 2026-09-27; the atomic
  Linux implementation commit records the software, with board acceptance still open below.

- Repeat campaign manifest and campaign report: ordered hash-bound repeats, configuration
  agreement, raw-sample pooling of valid repeats, spread between repeats and run-plan
  conformance. Exercised with RTL simulation repeats; no board campaign exists.

- Native control-run and campaign analysis in the [standalone Rust crate](analysis/rust/README.md):
  the run and campaign commands write the Python analysis's reports byte for byte, including runs
  that bind an AMP capture, and refuse with Python's texts; a hosted gate requires every line and
  branch of the crate. Closed-loop benchmark data from the production plant witness and a pinned
  timing of both analyses are committed under `benchmarks/`. See
  [native control-run loading](docs/HOST_ANALYSIS.md#native-control-run-loading) and
  [control-run analysis timing](docs/HOST_ANALYSIS.md#control-run-analysis-timing).

- Source-bound Python coverage publication and a daily download-history importer with
  actual HTTP/TLS transport tests, explicit missing-data handling and a dedicated
  `metrics` data branch. See [repository metrics](docs/METRICS.md).

## Planned — in implementation order, without dates

Software publication includes the Python analysis package at version 0.2.0 and the standalone
Rust controller crate at version 0.1.0, plus the public Python, C/C++ and Rust API references.
Source releases are recorded in [CHANGELOG.md](CHANGELOG.md); they do not alter those immutable
registry artifacts. The versioned source archives
([0.1.0](https://doi.org/10.5281/zenodo.23092361), [0.2.0](https://doi.org/10.5281/zenodo.24222960),
[0.3.0](https://doi.org/10.5281/zenodo.24263979))
and GitHub releases
([v0.1.0](https://github.com/anulum/loop-timing-witness/releases/tag/v0.1.0),
[v0.2.0](https://github.com/anulum/loop-timing-witness/releases/tag/v0.2.0),
[v0.3.0](https://github.com/anulum/loop-timing-witness/releases/tag/v0.3.0))
are published with verified hashes and explicit software-only evidence scope.

The original-width RTL source-flow obligation is complete: 818 of 824 raw identities executed,
with six checked source invariants and no unresolved or excluded points. C++ lifecycle evidence
is tracked separately in [the coverage guide](docs/CONTROLLER_COVERAGE.md). Physical UIO/PAC1934
operation, privileged scheduling and board timing require their actual resources.

1. Vendor tool project generation scripts and constraints. The generation scripts produce a Libero
   project for MPFS250T and a [recorded timing run](hardware/icicle/README.md#recorded-libero-run);
   its static timing meets every clock there, including the 100 MHz witness capture clock, with
   the witness clock-domain crossings constrained. Board timing belongs to item 3.
2. Bare-metal controller on a dedicated application core. The C and Rust controller firmware
   runs on a dedicated hart in [ISA simulation](docs/AMP_SIMULATION.md) against the production
   RTL, and the [Linux AMP collector](docs/AMP_LINUX.md) builds. The deployment depends on the
   board: its silicon selects the device trees, and the HSS payload, OpenSBI, PMP isolation and
   shared-memory coherence must be shown on its boot artefacts.
   Blocked: no physical board is available.
3. Instrument acceptance on the board (known period, injected delay, overflow, bus-offset floor),
   then measured runs with manifests; evidence maturity advances only at this step.
   Blocked: no physical board is available; simulation does not close this item.

## Not planned in this repository

Accelerator-library adapters, controllers or plant models from other projects, redistribution of
vendor tools or IP, comparisons with other vendors, and any statement about platform performance
without a measured run.
