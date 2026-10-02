<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — changelog
-->

# Changelog

## [Unreleased]

## [0.1.0] - 2026-10-01

### Fixed

- Resume the reset testbench clock between edges so Icarus and Verilator both observe the
  original two-edge release assertions.
- Install the pinned Ubuntu Icarus package in the test workflow so RTL-to-host tests do not
  depend on an undeclared runner tool.

### Added

- Source-bound Python Codecov badge and daily validated PyPI download history on
  the isolated `metrics` data branch; missing provider observations remain unknown.
- Complete original-width RTL source-flow proof: 826 executed identities and eight
  checked source invariants out of 834 raw identities, with no excluded or unresolved points.
  Public reproduction includes both full 32-bit saturation programmes and Yosys counterexamples.
- Native C++ lifecycle regressions for a command commit crossing run completion, final FIFO
  drain without callbacks, and real run/final-drain timeout supervision through acquisition hooks.
- Production-register proofs for command staging and persistent run, finished and safe states,
  each checked against an intentionally false variant with a retained counterexample.
- Python statement and branch reports for the complete host/tool surface, uploaded separately
  from native and RTL evidence; API-site provenance binds generated pages to the source commit.

- Published Python host analysis wheel and source archive with typed API, packaged schemas and
  the `loop-timing-witness-analyze` command.
- Published standalone `no_std` Rust controller crate, with independently tested API and
  WASM/RV64 consumers. The platform-bound AMP kernel remains a source dependency.
- Documentation website with Python, Rust and C/C++ native API references and source provenance.
- Dual-clock fabric event witness with Gray-pointer FIFO, common run reset, drop-newest overflow
  accounting and real buffered RTL streams analysed by the host command.

- Versioned run manifest and host analysis for hash-bound RTL-simulation event streams,
  measurement-domain snapshots, tracking and rail-energy series; deterministic JSON, CSV and SVG
  reports keep simulation provenance visible.
- Synthesizable timestamp-record capture and a CONTROL/COMPUTE Icarus testbench used by the
  host-tool tests. Board instrument acceptance and measured results remain pending.
- Measurement-domain manifest and JSON Schema with the planned timebase, event record, event
  profiles and derived intervals, event buffer, controller placements and run plan; validator
  for repeated keys, schema, cross-field consistency and registry identity.
- Generated capability inventory (empty at `architecture_only`) with drift check.
- Hashed development lock, reviewed licence record for every pinned package and its guard.
- Guards for provenance headers, documentation links and anchors, workflow policy and commit
  messages; preflight runner with build-provenance checks of the Go-built tools and a version
  check of the spelling checker.
- Tests for every tool through its command-line and file surfaces.
- Workflow definitions: coordinator with required gate, static policy, tests, pre-commit parity,
  CodeQL, security audit, documentation, software inventory and Scorecard.
- Architecture, measurement protocol, threat model and repository-boundary decision record.
- Governance, contribution, security, support, licensing and citation metadata; manuscript
  collection index.

### Changed

- Reserve the initial source archive DOI, with an explicit distinction from the
  already published immutable registry distributions. Publication follows exact-source CI.
- Pin Yosys in hosted native validation to the same Ubuntu package as local proof execution.
- Retain GCC control-flow dumps alongside instrumented native lifecycle builds so compiler
  exception edges can be inspected without changing the production optimisation level.
- Publish Python and Rust packages through project-specific trusted publishing identities.
- Keep only project information in the README image metadata, preserving its decoded pixels.
- Update development dependency locks, licence records and repository quality tools.
