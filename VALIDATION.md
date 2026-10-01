<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — validation
-->

# Validation

## Installed Python distribution

`make python-package-tests` prepares binary runtime wheels using the hashes in
`requirements-runtime.txt`, then runs `tests/test_python_distribution.py`. The test builds the
canonical wheel and source archive through the pinned Flit backend. A wheel rebuilt from the
archive must contain the same files and bytes as the direct wheel. Each artifact is installed
offline into a fresh environment with the complete hashed runtime dependency set.

The consumer runs outside the checkout. Its public `load_run` and `build_report` API and
`loop-timing-witness-analyze` command analyse binary events produced by the real Icarus capture
path and must agree with repository analysis. An altered event digest must fail without creating
a report directory. Installed import origin, packaged schemas and the typing marker are checked.
The CI test job prepares the same hashed wheelhouse before pytest; no package-registry upload is
performed. `WITNESS_PYTHON_WHEELHOUSE` may select an existing wheelhouse for offline verification.

Every gate that exists in this repository, with its exact scope. No board instrument exists, so no
board measurement is validated; these gates validate repository infrastructure, the internal
consistency of the measurement contracts, the RTL-simulation-to-host-analysis path and the
truthfulness of the `architecture_only` state.

## Environment

- Python 3.13 in `.venv`, created by `make venv` from `requirements-dev.txt`, which pins every
  development package with its hashes and is installed with `pip install --require-hashes`.
- Flit Core 4.1.0 is the hash-pinned Python distribution build backend in the same development
  lock, with the current complete-chain upload cut-off recorded in both lock headers.
- Icarus Verilog 12.0 (`iverilog` and `vvp`), Ubuntu noble package `12.0-2build2`, to compile the
  synthesizable capture and buffered witness modules and produce binary event files consumed by
  the host CLI tests. The reusable test workflow installs that exact package through Ubuntu's signed APT
  repositories and prints both tool versions. A missing simulator fails the tests; simulation
  is not evidence of board acceptance.
- Rust 1.99.0 (Cargo, rustfmt, Clippy and matching LLVM profiling tools), installed explicitly with rustup in native CI jobs;
  C uses GNU 128-bit integers and strict GCC compilation with all warnings as errors.
  Tool versions are printed by the jobs. The controller kernels have no third-party native dependencies.
- Verilator 5.020 (`verilator`), Ubuntu noble package `5.020-1`, builds the native controller
  against the production AXI top. C++17 and Linux headers are required for the native adapters.
- The [dedicated-hart ISA capture tests](docs/AMP_SIMULATION.md) require actual Spike execution,
  matching original source/generated headers, both production RTL plugins and a publicly built
  RV64 firmware image. The plugin uses C++20; firmware uses the freestanding RV64IMAC/Zicsr/Zifencei
  ABI. Supply `WITNESS_SPIKE`, `WITNESS_SPIKE_SOURCE`, `WITNESS_SPIKE_BUILD`,
  `WITNESS_SPIKE_PLUGIN`, `WITNESS_SPIKE_THERMAL_PLUGIN` and `WITNESS_AMP_IMAGE` explicitly.
  `dtc` compiles the retained original topology. Missing actual dependencies fail these tests.
  Host library paths must expose the selected actual RV64 compiler dependencies. Native Make
  builds retain complete `-MD` source/system/SDK header records and exclusive plugin build
  receipts. Image verification records the actual driver, frontend, collect2, assembler and
  linker identities; source/receipt drift requires a fresh build.
- Strace 6.8, Ubuntu noble package `6.8-0ubuntu2`, is required for owned-process refusal tests.
  Tests delay syscall entry and retain actual kernel results; they neither substitute return
  values nor modify process memory. Tracing starts with test-owned children and uses existing
  kernel permissions. A missing tracer fails the tests; no security settings are changed.
- OpenSSL 3 headers and `libcrypto` are required for native artifact SHA-256 receipts. The
  reusable test workflow installs `libssl-dev=3.0.13-0ubuntu3.16` and `libssl3t64=3.0.13-0ubuntu3.16`, prints the actual development
  and runtime packages, and links the adapters with `-lcrypto`. Native metadata records both
  header and runtime version numbers. This dependency belongs to the run adapters; it is not
  linked into the standalone C/Rust controller kernels.
- `actionlint` v1.7.12 and `gitleaks` v8.30.1 built with `go install` from their module sources; the
  preflight runner reads each binary's recorded module version and checksum with
  `go version -m` and refuses any other build.
- `typos` 1.50.3, installed from the same lock and checked by its reported version.

The lock is regenerated only with the command recorded in its header, followed by a licence review
of every new or changed package in `development-dependency-licences.json`.

## Local gates

`python tools/preflight.py` runs every gate below in order and fails if any gate fails or its tool
is missing; `--only NAME` runs one gate and `--list` prints the plan.

| Gate | Command | Scope |
|---|---|---|
| `ruff-check` | `ruff check .` | every Python file; all rule groups enabled, exclusions listed with reasons in `pyproject.toml` |
| `ruff-format` | `ruff format --check .` | every Python file |
| `mypy` | `mypy` | `tools/`, `tests/`, `conftest.py` and native build support in strict mode |
| `controller-build` | `make controller-build` | strict C build, Rust format/Clippy, dependency-free release build and native API documentation |
| `controller-tests` | `make controller-tests` | public C APIs under undefined-behaviour sanitization and Rust public state/refusal tests |
| Rust AMP image | `.venv/bin/pytest -q tests/test_amp_rust_image.py` | actual public preparation, strict original RV64 C/assembly and Rust compilation, linking, metadata/final dependency reconciliation, immutable image receipt and offline captured-byte admission; requires dtc, RV64 GCC and the RV64IMAC Rust target |
| Rust toolchain custody | `.venv/bin/pytest -q tests/test_amp_rust_toolchain.py` | actual Rustup proxy/compiler identity and owned real-compiler toolchain refusal when Cargo or RV64 core libraries are missing; requires Rustup and an installed RV64IMAC target |
| Rust original source custody | `.venv/bin/pytest -q tests/test_amp_rust_sources.py` | actual Rust metadata/final dependency records, archive admission, captured source/library bytes and refusal of missing or escaping original source paths; requires the installed RV64IMAC Rust target |
| Rust AMP panic refusal | `.venv/bin/pytest -q tests/test_amp_rust_panic.py` | source-bound fault image exercises the original Rust panic handler and terminal `0x109` refusal through public capture on both mechanical and thermal production plants; requires the CI AMP image, Spike, plugins, RV64 GCC and RV64IMAC Rust target |
| Rust package consumer | `.venv/bin/pytest -q tests/test_rust_package_consumer.py` | real Cargo archive extraction, separate dependency client, state/refusal tests, strict Clippy, allocator-free WebAssembly and RV64IMAC builds, and actual RISC-V ELF64 soft-float object checks; requires both installed Rust targets |
| Icicle reference derivation | `.venv/bin/pytest -q tests/test_icicle_reference_derivation.py` | fetches the pinned official reference commit unless `WITNESS_ICICLE_REFERENCE` names a clean local checkout; exercises the public derivation, complete reference-tree receipt, copied RTL hashes and pre-Libero refusal paths; place pytest's base temporary directory on the repository disk |
| `tests` | `pytest --cov --cov-branch --cov-report=term-missing --cov-fail-under=100` | every test; 100 % statement and branch coverage of `tools/` and native build support, including subprocess runs of the host CLI against event files produced by Icarus RTL simulation |
| `measurement-domain` | `python tools/validate_measurement_domain.py` | repeated-key rejection, JSON Schema, cross-field rules, and — where the canonical project registry is present — group and project identity |
| `capability-inventory` | `python tools/generate_capability_inventory.py --check` | committed inventory byte-identical to a fresh generation from a valid manifest |
| `provenance-headers` | `python tools/check_provenance_headers.py` | seven-line provenance header in every publishable file with a comment syntax; Markdown header inside an HTML comment with rendered content after it |
| `documentation` | `python tools/check_documentation.py` | every relative link and image in publishable Markdown reaches a publishable path; every fragment names a heading |
| `dependency-licences` | `python tools/check_dependency_licences.py` | lock pins and licence records match exactly; every licence expression parses and uses allowed identifiers |
| `workflows` | `python tools/audit_workflows.py` | workflow inventory, ownership taxonomy, permissions, triggers, concurrency, timeouts, action and image pinning, checkout credentials, coordinator gate |
| `reuse` | `reuse lint` | REUSE 3.x compliance of the whole tree |
| `zizmor` | `zizmor --offline --persona pedantic --strict-collection .` | workflow, Dependabot and pre-commit configuration security analysis; one audit disabled with its reason in `.github/zizmor.yml` |
| `actionlint` | `actionlint` | every workflow file |
| `typos` | `typos` | every file except the lock, the licence record and the licence texts |
| `secrets` | `gitleaks dir` on a copy of the publishable files | tracked and non-ignored untracked files |

Dependency vulnerabilities are checked with
`pip-audit --require-hashes --disable-pip -r requirements-dev.txt` (`make security`); it needs
network access to the vulnerability database and is therefore not part of the offline preflight.

## Fabric simulation and synthesis

Dedicated RTL tests are `tests/test_clock_reset_release.py`, `tests/test_event_record_fifo.py`
`tests/test_event_witness.py`, `tests/test_control_plant_witness.py` and
`tests/test_control_faults.py`. Controller parity, design, 64,000-sample trajectories and
closed fabric/native replay are exercised by `tests/test_controller_*.py` and
`tests/test_fabric_controller*.py`. They compile the actual modules with Icarus and check public
ports with scoreboards, including the default 16,384-record capacity, clock ratios, queued-data
reset, wrap, overflow and saturation. Buffered binary drain output reaches the host report CLI.
The CI test workflow runs these with the same pinned simulator as the capture tests.

Local RTL review also runs Verilator 5.020 strict `--lint-only --Wall`, and Yosys 0.33 preparation,
memory inference checks and post-optimisation equivalence at a four-record configuration. The
plant integration additionally runs component optimization proofs with
`rtl/check_control_equivalence.ys`; the controller uses
`rtl/check_controller_equivalence.ys` (2,246 proven cells, zero unproven). Monolithic technology-mapped system equivalence remains
unqualified. The
Yosys proof normalises asynchronous resets with `async2sync` before synthesis; it does not
qualify metastability, Gray-bus physical timing or a board bitstream. See
[`docs/FABRIC_WITNESS.md`](docs/FABRIC_WITNESS.md) for ports and remaining board gates. Python
coverage measures tools, not SystemVerilog; the simulations do not provide a numeric RTL
statement/branch coverage verdict.

The board-facing `icicle_witness` top is also checked against every production RTL source:

```bash
verilator --lint-only --Wall --top-module icicle_witness rtl/*.sv
yosys -Q -T -q -p 'read_verilog -sv rtl/*.sv; hierarchy -check -top icicle_witness; proc; opt; check -assert'
```

These checks establish source elaboration and obvious structural consistency. They do not
replace the derived Libero project, device-specific DRC, physical CDC review or timing reports.

## Hooks

`make hooks` installs the hooks in `.pre-commit-config.yaml`:

- before each commit: upstream checks for large files, case conflicts, executable bits, JSON,
  merge markers, TOML, YAML, private keys, final newlines, line endings and trailing whitespace;
  staged secret scan; REUSE; typographical check; and the local gates through
  `tools/preflight.py --only`;
- on the commit message: `tools/check_commit_trailers.py` (conventional subject, seat and
  authorship trailers, no other trailers, no generated-by attribution, no self-applied quality
  terms);
- before each push: the complete preflight.

Upstream hook repositories are pinned to verified commit objects.

## Workflow definitions

The definitions have run on a hosted platform. This table describes their intended checks, not a
current success verdict: a workflow that has not run on the exact assessed commit is no evidence.
Every action is pinned to a verified commit object.

| Workflow | Purpose | Category |
|---|---|---|
| `ci.yml` | coordinator: calls the two reusable workflows and holds the one required gate | coordinator and required gate |
| `reusable-static-policy.yml` | lint, format, typing, manifest, inventory, headers, licences, workflow policy | static analysis and policy |
| `reusable-tests.yml` | tests with 100 % statement and branch coverage | unit and component quality |
| `pre-commit.yml` | every pre-commit stage hook on all files | static analysis and policy |
| `codeql.yml` | code scanning of C, Rust, Python and the workflow definitions | security and supply chain |
| `security-audit.yml` | secret scan of the full history, vulnerability audit, licence guard, REUSE, actionlint, zizmor | security and supply chain |
| `scorecard.yml` | OpenSSF Scorecard analysis and public project-bound results | security and supply chain |
| `sbom.yml` | CycloneDX inventory of the development lock, kept as a 30-day artefact | security and supply chain |
| `docs.yml` | strict source, Python, C/C++ and Rust API build; Pages deploys only verified main builds | documentation |
| `controller-comparison.yml` | matching native workload measurements and retained runner receipts | performance and benchmarking |
| `publish.yml` | manually dispatched exact-revision validation, real wheel/sdist consumers and PyPI OIDC publication | release and registry publication |
| `publish-rust.yml` | manually dispatched exact-revision validation, independent packaged API consumers and crates.io OIDC publication | release and registry publication |

Ownership of every job and the omitted categories are declared in
`.github/workflow-inventory.json` and enforced by the `workflows` gate.

## Native API documentation

`make documentation-toolchain` installs the official Doxygen 1.18.0 Linux binary
archive only after verifying SHA-256
`14fa81bdc34171edb5f1f02b1d60e74802f0439b77fa44e592565d517d72df90`.
Local and hosted builds use that same archive and Rust 1.99.0.
`make native-api` treats Doxygen warnings, undocumented public members and enum
values as errors. Both Rust crates deny missing public documentation; Rustdoc
also denies warnings and broken intra-doc links. Tests remove descriptions from
actual C and Rust public fields and require the native builders to refuse them.

`make docs-site` combines those strict native references, installed-package
Python pydoc and every Git-publishable Markdown document. It validates source
links, preserves heading fragments, excludes ignored private content and records
the source revision and output hashes in `site-provenance.json`. Hosted PR builds
have read-only source access; the separate Pages job requires a successful build
and the main-branch `github-pages` environment.

Registry workflows run only by manual dispatch on main, require completed green
validation at that exact revision, and exercise the actual package consumers.
PyPI uses the `pypi` environment and a configured trusted publisher. Crates.io
uses the `crates-io` environment and a configured trusted publisher; its first
crate creation requires a separate initial token-authenticated publication
before that trusted publisher can be configured. Neither registry release nor
rendered API documentation establishes physical instrument qualification.

## Native controller coverage and regression

[`docs/CONTROLLER_COVERAGE.md`](docs/CONTROLLER_COVERAGE.md) reproduces GCC line/branch
and LLVM line/region/function/branch analysis of the kernels and streaming CLIs.
[`benchmarks/controller_coverage.json`](benchmarks/controller_coverage.json) retains
source and raw-report hashes. Coverage is host execution evidence; no numeric RTL
coverage or physical timing qualification is inferred. The production Rust compiler
remains 1.99.0; the separate branch analysis pins nightly-2026-08-21.

`make controller-benchmarks` executes matching million-sample native workloads.
[`benchmarks/controller_regression.json`](benchmarks/controller_regression.json)
records five repeats per language/controller from the earlier Rust 1.98.1 build, with
compiler, source/binary hashes, load, affinity and governor. This retained historical
snapshot is not a performance measurement of the current compiler. Non-isolated timings
are local regression evidence only.
C/Rust command checksums must agree; host wall time cannot establish fabric speedup.

## Native Linux runtime verification

`make run-simulation` compiles the in-process native controller with the actual production
AXI top; `make run-uio` builds the same lifecycle with Linux UIO and the PAC1934 journal.
`make run-amp-uio` builds the separate IRQ-free Linux logger for a dedicated firmware hart,
using the ABI 2 startup handshake and actual firmware run-contract comparison described in
[`docs/AMP_LINUX.md`](docs/AMP_LINUX.md).
`tests/test_amp_uio_run.py` exercises its public command, resource parsing and actual
unavailable-device refusals; `tests/test_amp_architectural_refusals.py` exercises actual
firmware traps and mismatched published contracts through Spike and production RTL.
`tests/test_amp_logger.py` additionally links a real RV64 wrapper around the unchanged production
IRQ handler. Its zero baseline completes both plant models, including 300 samples that
reuse all 256 ring slots; raw cycles, IRQ generations and snapshot timestamps match actual
`SAMPLE_READ` records. Deliberate target RAM writes
exercise full-ring refusal and post-IRQ ABI, cursor, status, reserved-field and trap-state
consistency checks. Invalid sample flags, out-of-range/repeated cycles, regressed snapshot
timestamps and repeated IRQ generations are also refused. Actual child file-size limits exercise header and final-close failures.
These deliberately altered test ELFs run directly in Spike and produce no admitted capture
or measurement manifest.
`tests/test_amp_logger_api.py` links a diagnostic client against hash-verified production
RTL objects and the unchanged logger and transport. Both plants exercise the public lifecycle,
waiting for actual firmware arming, delayed telemetry consumption across the eight-record batch
bound, invalid mailbox addresses, contract mismatch, premature completion, repeated polling and
acquisition callback failures. Public Spike memory stores deliberately damage one real initial
or arming field at a time; the logger refuses each changed word. A source-bound diagnostic ELF
also selects the genuine LQR kernel, with matching published configuration. Successful runs retain the actual ten samples and forty events;
refusals retain native diagnostics. Diagnostic clients produce no capture or measurement manifest.
The AMP logger also compiled with the genuine RV64 compiler and target OpenSSL libraries
listed below; QEMU verified usage and missing-device refusals. Neither those checks nor
the ISA handshake establish successful Linux shared-memory acquisition on a board.
Simulation verifies PID/LQR feedback, real sample/command events, fault handling, reset custody,
final FIFO drain and capture-to-manifest-to-report integration. Real host-file and process tests
exercise exclusive output, write/flush failures, hashing errors, concurrent artifact mutation,
affinity/scheduler requests and metadata refusal. The dedicated public API tests are:

- `tests/test_native_lifecycle_api.py` and `tests/test_native_configuration_api.py`;
- `tests/test_native_metadata_api.py` and `tests/test_native_policy_api.py`;
- `tests/test_power_configuration_api.py` and `tests/test_axi_transport_progress.py`.

The compiler profiles and source-bound native lifecycle proofs described in
[`docs/CONTROLLER_COVERAGE.md`](docs/CONTROLLER_COVERAGE.md#native-lifecycle-guard-proof)
retain executable-line and raw-branch counts separately from Python coverage. They do not
establish complete C++ runtime coverage. Actual UIO/IIO identity and unavailable-device refusals
are exercised without invented sysfs nodes. Successful MMIO, IRQ handling, PAC1934 reads and
power worker lifecycle need physical resources and remain unverified. Host builds do not qualify
a U54 target binary, Linux image, bus timing or the board instrument.

The [Linux build targets](docs/HOST_ANALYSIS.md#linux-native-and-rv64-builds) also accept
explicit target compilers, sysroot flags and a separate output directory. A local RV64 Linux
check used Ubuntu GCC 13.3.0 and genuine riscv64 OpenSSL `3.0.13-0ubuntu3.15` headers and
libraries. Both UIO executables and their controller object compiled with the strict warnings
and were checked as RISC-V ELF64 with double-float ABI. The run executable links target
`libcrypto.so.3`. QEMU 8.2.2 user-mode checks exercised both usage refusals and actual missing
UIO sysfs refusal, including configuration hashing before device access; no measurement
outputs were created. These are target build and emulated refusal checks. Successful MMIO,
interrupts, IIO acquisition and compatibility with a particular board image remain unverified.

## Host load capture validation

`tests/test_linux_load_config.py` checks supported profiles, actual inherited CPU affinity
and resource bounds through the public configuration API.
`tests/test_linux_load_channels.py` exercises actual pipe transfers, prompt EOF, early
child-end release, kernel broken-pipe failure cleanup, descriptor-number reuse and real
descriptor exhaustion during second-pipe allocation, with first-pipe cleanup verified.
`tests/test_linux_load_readiness.py` reads actual producer frames through real pipes and
checks complete-line deadlines, incremental chunks, exact field types, EOF and the inclusive
frame-size bound, strict UTF-8 encoding and repeated-member refusal.
`tests/test_linux_load_readiness_launch.py` exercises actual worker pipes
with incomplete, oversized, unterminated, duplicate or mistyped messages and checks that no
native output or completed load receipt is created. Tracing delays actual worker policy
readback to provide a controlled startup window; syscall results are not replaced.
`tests/test_linux_load_worker.py` exercises actual control-pipe EOF, odd-size and maximum UDP
chunks, parent scheduling preservation and exclusive workspace/storage/receipt failures,
plus real UDP peer corruption and concurrent working-file modification.
`tests/test_linux_load_api.py` checks the public launch API against actual invalid paths,
lifetime bounds, executable-format failure, missing worker source and journal write failure.
`tests/test_linux_load.py` exercises all five real host profiles with each production RTL plant,
actual workload counters and readback, parent scheduling preservation and completed process
ownership, bounded native timeout, actual SIGTERM loss, SIGSTOP/kill escalation and
readiness timeout or identity corruption on the actual owned control pipe.
`tests/test_linux_load_trace.py` changes an actual worker to `SCHED_BATCH` before its kernel
scheduler readback and checks refusal without a receipt. It also retains original production
worker receipts, deliberately alters PID, either interval bound or top-level/nested JSON member
names while actual exit is delayed, and checks that the launcher refuses each altered artifact after successful native execution.
The tracer retains owned descendant identities with pidfds and checks live parent relationships
before registering children. Cleanup signals only those retained identities.
`tests/test_host_load_capture.py` exercises frozen producer-to-manifest-to-report
capture and reproducible public analyzer output, retaining source digests and refusing a
contradictory native exit receipt. `tests/test_host_load_receipt.py` validates actual receipts
and rejects altered policy, operation counts, scopes and time brackets. These host workload
checks do not establish board timing or power, NIC traffic, uncached storage access or native
hardware branch coverage.
