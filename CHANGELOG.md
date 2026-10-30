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

### Added

- Repeat campaign manifest and `loop-timing-witness-campaign` command: hash-bound
  ordered repeats with reboot declarations, refusal of mixed configurations, every
  repeat listed with its outcome, latency and jitter pooled from raw samples of
  valid repeats, per-statistic spread between repeats and run-plan conformance,
  written as JSON and CSV in one atomic directory.
- Neural step-run analysis (`load_neural_run`, `build_neural_run_report`) in Python
  and in the Rust analysis crate: hash-bound source, capture and checker receipts,
  a consumer-owned registry of reviewed checker profiles, and a second registry
  entry that runs the checker inside an immutable extracted image selected by the
  operator. The image is verified file by file before and after each run, under a
  deadline, and every opened source must match the reviewed digests.
  Host-specific installation and executor descriptors are selected by the
  operator (`LOOP_TIMING_WITNESS_CHECKER_INSTALLATION`,
  `LOOP_TIMING_WITNESS_CHECKER_IMAGE_BINDING`) and checked against pinned
  digests; they are not packaged.
  Consumers may pass their own reviewed entries as the keyword-only `registry`
  argument in Python or through `load_neural_run_with_registry` in Rust; the hermetic test acquisition runs the whole chain through both the
  image and a traced host installation.
- Per-run absolute adjacent-cycle latency jitter with Type-7 distributions,
  missing-pair coverage, separate peak-to-peak spread, auditable pair CSV and
  labelled SVG output for both event profiles. Warm-up and gaps are excluded.
- Source-release verification and OIDC/Sigstore signatures for the immutable
  `v0.1.0` source archive and provenance manifest, with separate verification,
  signing and release-attachment jobs and portable verification instructions.

### Changed

- Run the hosted Python tests in four duration-balanced shards with one coverage
  union holding the unchanged 100 % threshold; restore the pinned Spike build
  from an exact-input cache.

### Fixed

- Refuse the same neural acquisitions with the same messages in Python and Rust:
  malformed JSON names only the refused document; the image runtime contract,
  checker policy and worker observation must have their closed typed forms in
  Python too; a linked, nonregular or excessive observation or log is refused
  instead of ignored; tool receipts, reset prefixes and observed inventories
  are checked in one order. Hermetic acquisition tests now run the Rust API on
  every scenario and require the same report or refusal.
- Pin the development file-lock library to 4.2.4 and the virtual environment tool to
  21.15.1, both fixed releases of reported vulnerabilities, keeping hashes and upload cut-offs.
- Refresh the development certificate bundle and virtual environment dependencies
  to their fixed releases while retaining hashes and reproducible upload cut-offs.
- Validate JSON attribution sidecars without changing original JSON bytes;
  reject missing, linked, nonregular or malformed ownership records.
- Keep complete preflight available on an allocated runner while normal pushes
  use source enrolment and retain all hosted test, coverage and policy gates.
- Preserve authored native refusals through explicit exception types and return
  a fixed failure message for unexpected standard-library errors.
- Parse native integer arguments without exposing library overflow diagnostics,
  and preserve Linux scheduling refusals with authored numeric-errno messages.
- Retain strict Verilator warnings for counter saturation, including a deadline
  monitor configured to latch on its first miss.
- Preserve a report destination created during staging using capability-checked
  Linux atomic publication; also refuse an existing dangling output symlink.
- Reject native completion receipts whose fault kind, cycle or delay duration
  contradicts the run's declared schedule, including rehashed metadata.
- Refuse nonfinite JSON tokens and numeric overflow in run, readiness and receipt
  inputs through the shared source and installed-package decoder.
- Bind the actual loaded parent Python producer implementation and environment
  to each native capture; refuse changed source or context before acceptance.
- Accept schema-valid UTC timestamps with lowercase RFC3339 separators while
  preserving the original timestamp in run reports.
- Show repository-relative source and schema paths in Python API references
  instead of the documentation builder's absolute filesystem paths.
- Wrap long documentation links and inline values on narrow screens while
  retaining formatted code blocks and their own horizontal scrolling.
- Describe the implemented software and simulation paths in the bug-report form
  while retaining the pending physical instrument qualification.
- Declare the original source ZIP's timezone during reconstruction so UTC CI
  runners verify the exact published bytes without changing the frozen digest.

## [0.1.0] - 2026-10-01

### Fixed

- Resume the reset testbench clock between edges so Icarus and Verilator both observe the
  original two-edge release assertions.
- Install the pinned Ubuntu Icarus package in the test workflow so RTL-to-host tests do not
  depend on an undeclared runner tool.

### Added

- Published source release and permanent [Zenodo archive](https://doi.org/10.5281/zenodo.23092361),
  binding commit `1d12e0342d5320f62182fef41709773f3c555b50` and verified source/provenance hashes.
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

- Bind the source archive DOI to the validated software snapshot, with an explicit
  distinction from the already published immutable registry distributions.
- Pin Yosys in hosted native validation to the same Ubuntu package as local proof execution.
- Retain GCC control-flow dumps alongside instrumented native lifecycle builds so compiler
  exception edges can be inspected without changing the production optimisation level.
- Publish Python and Rust packages through project-specific trusted publishing identities.
- Keep only project information in the README image metadata, preserving its decoded pixels.
- Update development dependency locks, licence records and repository quality tools.
