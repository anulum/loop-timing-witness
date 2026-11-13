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

- Native firmware ELF reading in the Rust analysis crate: the public `amp_elf` module admits
  the load segments of an AMP firmware image inside its reservation and reads its global
  symbols, with the Python readers' values and refusal texts. Two committed real images and a
  corpus of their changes hold both implementations to the same outcomes.
- Native device-tree reading in the Rust analysis crate: the public `device_tree` module
  decodes an original blob and reads register regions translated to root addresses, scalar,
  string-list and phandle properties, and the dedicated PLIC binding, with the Python
  readers' values and refusal texts for the same first defect. A corpus that the Python tests
  build from real `dtc` output holds both implementations to the same outcomes.
- The native `loop-timing-witness-campaign-native` command analyses a repeat campaign as the
  Python campaign command does: the same statuses and printed lines, the same refusal texts,
  and a byte-equal report directory. A campaign binding an AMP capture is refused by the
  native command.
- Native control-run loading in the Rust analysis crate: `load_control_run`,
  `load_control_run_bytes` and `decode_control_events` validate a CONTROL or COMPUTE
  run, its hash-bound measurement domain and every input, and decode its events,
  refusing with the same texts as the Python `load_run` and `decode_events`.
  `control_events_summary` builds the report's `events` block and interval rows as
  the Python analysis does. `control_run_report` builds the complete per-run report:
  tracking error, observed tracking, energy per cycle, validity, input digests, stated
  limits, native completion counters and the host load receipt, with floats equal to
  the Python report's bit for bit. A run that binds an AMP capture is refused there
  until AMP completion is implemented natively.
- The native `loop-timing-witness-analyze-native` command analyses CONTROL and COMPUTE
  runs end to end and publishes the same report directory as the Python command, byte
  for byte: `report.json`, the interval, jitter, adjacent-cycle and per-cycle CSV
  tables and the SVG plots. The output parent is resolved as Python's non-strict
  `Path.resolve`; existing destinations, missing parents and publication faults are
  refused with Python's texts, and nothing staged is left behind.
- Complete C controller coverage gate: `make controller-tests` ends with
  `make controller-coverage`, which runs the C API test and the stream and refusal tests
  against GCC-instrumented programs. `tools/c_coverage_gate.py` adds their counts and
  requires every line and branch of every `.c` file in `controllers/c` to have run.
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

- The sources of a Rust dependency record are checked and read in sorted order. When several
  sources fail, the refusal or read error reported is the first in that order; it no longer
  depends on the interpreter's string hash seed.
- A compiler or Rust dependency record, or raw native tracking, that is not UTF-8 is refused
  with an authored text (`AMP original compiler dependency record is not UTF-8`, `Rust
  dependency record is not UTF-8`, `native tracking is not UTF-8`) instead of the codec's
  message.
- A compiler or Rust dependency record that leaves a quotation or an escape unbalanced is
  refused with the reader's own text (`AMP original compiler dependency record is malformed:
  unbalanced quotation or escape`, `Rust dependency rule is malformed or uses ambient
  environment`) instead of `shlex`'s message.
- A recorded AMP image verification vector whose `--hart`, `--interrupt` or `--stack-bytes`
  argument is not a canonical decimal (`0` or `-?[1-9][0-9]*`) within the signed 64-bit range
  is refused as `AMP original image verification arguments disagree`. A plus sign, digit
  separators or other digits no longer pass through Python's `int`, and its error texts no
  longer leak.
- An AMP capture or plugin build receipt that breaks its schema is refused with the first
  broken location in path order and an authored text (`AMP capture receipt <location>: does
  not satisfy the AMP capture schema`, `AMP plugin build receipt <location>: does not satisfy
  the AMP plugin build schema`) instead of the schema validator's first, unsorted message.
- An AMP capture's `started_utc` and `completed_utc` must each be one RFC 3339 date-time in
  UTC, the rule of the run manifest's `started_utc`: another offset, an impossible date or a
  leap second is refused (`AMP capture receipt <field> must be an RFC 3339 date-time in UTC`).
  The check no longer depends on whether an optional date-time validator is installed, which
  the runtime lock does not provide.
- Every AMP input is decoded with the bounded JSON rules of run-bound documents: the capture,
  completion and plugin build receipts, the retained measurement domain, and the captured
  preparation, command, image, build-command and source-index files. A document nested more
  than 64 deep, holding an integer outside the 64-bit range or an unpaired surrogate escape is
  refused with the decoder's text.
- A repeat campaign whose valid repeats together span more than the 64-bit tick range is
  refused (`pooled duration exceeds the 64-bit tick range`). Every integer a report holds
  then fits 64 bits, as every integer a run-bound document may hold does.
- A repeat campaign that breaks its schema is refused as `repeat campaign <location>: does not
  satisfy the repeat campaign schema`, naming the first failing location in path order as a run
  manifest refusal does. The schema validator's own wording is no longer part of the text.
- The repeat campaign manifest is decoded with the bounded JSON rules of every run-bound
  document: a campaign nested more than 64 deep, holding an integer outside the 64-bit range
  or an unpaired surrogate escape is refused with the decoder's text before its schema is
  checked.
- The analysis command chooses between the neural and the CONTROL/COMPUTE analysis
  by decoding the manifest nested at most 64 deep, checked before decoding, with
  integers kept as text and unpaired surrogate escapes kept. A deeper manifest is
  refused by the dispatcher (`analysis manifest: JSON input exceeds decoder limits`)
  instead of by the analysis it would have reached, and the choice no longer depends
  on the interpreter's recursion or integer-conversion limits. Both analyses choose
  alike.
- A repeated JSON member name is compared exactly, unpaired surrogates included, and
  named with `\udXXX` for an unpaired surrogate, as standard error prints it.
- The native command refuses a manifest it cannot read with the Python dispatcher's
  text, `A finite regular strict JSON manifest is required. Cannot acquire a finite
  regular run manifest for analysis.`, and names a published output as Python's
  `str(Path)` does.
- Run-bound JSON documents nest at most 64 deep, hold integers within the 64-bit
  ranges and no unpaired surrogate escape; the shared decoding limits keep the
  Python and native refusals identical.
- A run manifest that breaks its schema is refused with its first failing location and
  an authored sentence, and a run-bound measurement domain with every distinct failing
  location, instead of the schema validator's wording. `started_utc` is checked by one
  authored RFC 3339 UTC rule that no longer depends on an optional format checker; a
  leap second, an impossible date or year 0000 is refused with
  `started_utc must be an RFC 3339 date-time in UTC`.
- Tracking and power series values have one plain form: ASCII, an optional sign,
  digits with an optional decimal point and an optional exponent, at most 28
  significant digits, and zero or a magnitude from 10^-99 up to 10^100. Whitespace,
  digit separators, non-ASCII digits and values outside that range are refused
  (`… is not a decimal`, `… is outside the supported decimal range`), so every result
  stays exact or correctly rounded and finite. Cycle and tick counts must be below
  2**64. Observed tracking uses the same rules with the prefix `observed tracking`.
- A neural declaration is read with the bounded run JSON rules: nesting at most 64
  deep, integers within the 64-bit ranges, no repeated member name and no unpaired
  surrogate escape. A document outside them is refused with `Neural manifest must
  contain a strict UTF-8 JSON object.` before the schema is checked, and the result
  no longer depends on the interpreter's recursion or integer-conversion limits.
- The native neural declaration reader refuses with the Python texts and in the Python
  order: the closed schema with exact integers, the exact run identifier and source
  pins, each source reference (its digest, then its path and length), repeated source
  paths, then the root and channel references. A digest that only the schema's line
  anchor admits is refused as `Neural file reference requires an exact lowercase
  SHA-256.`; a path holding NUL, a directory and a descriptor that cannot be inspected
  or read are refused with Python's texts. The former native-only texts are gone.
- Native metadata and host load receipts are read with the bounded run JSON rules, and
  a receipt that breaks its schema is refused with its first failing location
  (`native metadata <location>: does not satisfy the native run schema`,
  `host load receipt <location>: does not satisfy the host load schema`) instead of the
  schema validator's wording.
- Every documentation website page shows the copyright, the AGPL-3.0-or-later licence
  of the exact source revision, the commercial licence offer and the contact addresses
  in its footer; the provenance headers of the Markdown sources stay hidden comments.
- The Rust analysis command runs through `public_command::run`, which also takes a
  consumer's own registry; `Installation::with_embedded_workers` is public and
  checks every worker role and body before writing an owned copy. Operator
  descriptors are read as in Python: unavailable, not regular or differing.
  The packaged host entry refuses the current workers with the Python message.
- The hosted tests build the native analysis crate once with branch coverage
  instrumentation, run its tests and the Python parity tests against it, and
  require every line and branch of every crate source to be covered.
- Run the hosted Python tests in four duration-balanced shards with one coverage
  union holding the unchanged 100 % threshold; restore the pinned Spike build
  from an exact-input cache.

### Fixed

- A repeat campaign whose refused repeat names a repeated JSON member holding an unpaired
  surrogate, or a path with bytes that are not UTF-8, failed while its report was written. The
  report now holds such a refusal with each of those code points as its backslash escape, as
  the command prints a refusal, and the campaign is published.
- The native `load_control_run` refuses a directory named as the manifest with Python's
  text, `[Errno 21] Is a directory: '<path>'`; it named no path.
- The native analysis resolves a declared input path as Python's `Path` names it: a final
  separator, a repeated separator and a `.` part are dropped. A file declared with a final
  separator, such as `events.bin/`, was refused as not a regular file.
- The native analysis quotes a CSV cell holding a comma, a quote or a line break, and doubles
  its quotes, as Python's CSV writer does. A run identifier ending with the line feed its schema
  pattern admits was written unquoted.
- Series values are built from their digits, so a CPython without the C decimal module
  (built without libmpdec, as the hosted runners' 3.15) reads a value with a long run of
  leading zeros as the C module does instead of refusing it at the integer-string limit.
- The checker trace readers of both analyses skip every own kernel file of a process,
  `/proc/self/…`, `/proc/thread-self/…` and `/proc/<number>/…`, as they skipped
  `/proc/self/maps`. CPython 3.15 reads its memory map by number when ctypes loads, and
  some builds read the process status through libffi; a host checker run on them was
  refused as unavailable or as differing from its reviewed installation. A line feed
  in the file part no longer makes the Python reader refuse a name the Rust reader skips.
  A name such as `/proc/mounts`, which resolves through `/proc/self`, is skipped by its
  resolved path as well: each reader resolved it to its own process's file, so the
  native consumer found a file outside the binding that the Python consumer calibrated.
- A measurement domain with a Gray-pointer buffer depth written as an integral
  float, and a COMPUTE run whose domain gives COMPUTE a sample rate, raised an
  internal error; they are now checked and refused like other declarations. A
  CONTROL run declaring its cycle or warm-up count as an integral float is analysed
  instead of failing in the deadline pass.
- A tracking or power series whose CSV header has a quoting error, an undecodable
  observed tracking file, a series value with an extreme exponent, and a CONTROL run
  with an integral-float cycle count and a tracking series raised an internal error;
  each is now refused or analysed like other inputs.
- Check the checker image executor alike in Python and Rust: the binding must be its
  closed typed form in both (host boundary, image inventory, command, environment,
  deadline and file lists), invalid JSON is refused by name, an unreadable image
  directory or a name or link target that is not UTF-8 cannot match the bound
  inventory, and any operating-system failure reading an image file or a link is the
  same refusal. Image tests now change the binding, the host boundary, the image
  tree and the worker observation in both languages.
- Read the traced checker opens and run the checker alike in Python and Rust: one
  open-record grammar, shared by both test suites, with plain or hexadecimal path
  characters and lines ending only at a line feed; a non-UTF-8 trace, path or
  working directory, or an opened file that is gone, is a named refusal; the trace
  is read bounded and without links; runtime paths are compared resolved; any
  operating-system failure starting, waiting for or stopping the checker is one
  refusal, after the whole process group is stopped.
- Refuse damaged capture, counter, receipt, policy, reset and trace inputs with the
  same message in Python and Rust: capture records and counter receipts name the
  exact defect; the producer completion, native clock, native runtime, joint reset
  and historical checker receipts refuse invalid JSON by name and any other shape
  as an incomplete receipt; file reads name the file and the step that failed;
  checker sources are bound from the run as their own files; any operating-system
  failure while staging the checker is one refusal. Hermetic acquisition tests now
  run 159 further single faults, including real host faults, through both languages.
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
- Move the whole development and runtime Python chain to its newest releases under one
  upload cut-off (2026-11-10): Ruff 0.17, mypy 2.4.1, pytest 9.2, coverage 7.17, typos
  1.52, REUSE 6.3, zizmor 1.32, CycloneDX 8, pre-commit 4.7, Flit Core 4.2 and their
  dependencies, with the hook revisions, the pinned typos version and the licence
  record moved together.
- The source package requires Python 3.15 and is developed and tested on CPython 3.15.2,
  and the native crates build with Rust 1.99.1, also their minimum supported version. The
  published 0.1.0 release still accepts Python 3.13. The native text table follows CPython
  3.15's Unicode 17.0.0 for printable and decimal characters. PyYAML publishes no CPython
  3.15 wheel; it is built from its hashed source distribution with the hash-pinned
  setuptools of `requirements-build.txt` and without the libyaml extension, and the licence
  record covers both development locks.
- Move the analysis crate to its newest dependencies, rustix 1.1.6, serde 1.0.229,
  serde_json 1.0.154 and sha2 0.11.1, with the lock, the reviewed licence record and the
  third-party notices moved together.
- Hosted workflows use Go 1.27.3, the CodeQL action 4.39.3 and cargo-cyclonedx 0.5.10.
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
