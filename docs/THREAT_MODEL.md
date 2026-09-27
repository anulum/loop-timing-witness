<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — threat model
-->

# Threat model

The model separates implemented software and simulated RTL from physical instrument
qualification. Current surfaces include validation and host analysis, C/Rust/RTL controllers,
native Linux run control, UIO/IIO adapters, workload processes, contracts and workflow
definitions. Hardware access code exists; successful board operation remains unverified.
The second part covers the controls needed for a qualified physical instrument.

## Part 1 — current repository

### Assets

| Asset | Why it matters |
|---|---|
| `measurement-domain.json` and its schema | define what a future measurement means; a silent change would change every later result |
| `run-manifest.schema.json` and the host analysis tool | bind run files to provenance and calculations; accepting an invented source or silently dropped event would falsify a result |
| `capability-inventory.json` | the public statement that no board capability is qualified or measured |
| Non-claims in the manifest and README | prevent the repository from being cited for results that do not exist |
| `requirements-dev.txt` and `development-dependency-licences.json` | hash-bound Python development dependencies; native prerequisites are recorded in `VALIDATION.md` |
| Workflow definitions | execute only with declared per-job hosted permissions after separately authorised publication |
| Native configuration, source snapshots and receipts | identify actual controller inputs, executable and completed observations |
| Workload processes and pipes | affect host resources and admit a native run only after bounded, owned-worker readiness |
| UIO/IIO adapters and raw power journal | contain physical access paths whose successful operation is unqualified |
| Licensing and provenance metadata | legal integrity of the repository |

### Trust boundaries and actors

- **Repository editor** (owner or reviewed contributor): trusted after review; every change passes
  the gates in `VALIDATION.md`.
- **Downstream consumer** (for example an accelerator library adapter that reads the manifest
  format): trusts the manifest only as far as its schema identifier and validator verdict.
- **Package index and upstream projects**: untrusted; every development dependency is pinned by
  version and hash, and every licence is recorded after review.
- **Operator-selected executable and local kernel**: the operator selects the native executable,
  CPU and workload bounds. The launcher owns its children and descriptors; it does not sandbox
  arbitrary executable code. Actual kernel policy and device identity are checked at their
  interfaces. A process with the same user privileges can interfere with owned artefacts.
- **Hosted CI** (after separately authorised publication): untrusted execution environment;
  workflows carry empty top-level permissions, per-job least privilege, commit-pinned actions,
  no persisted checkout credentials and bounded timeouts.

### Misuse paths and mitigations

| Misuse path | Mitigation |
|---|---|
| Adding a capability, claim or hardware verification without evidence | validator refuses non-empty capabilities or claims and `verified_on_hardware: true` at `architecture_only`; the inventory is generated and drift-checked |
| Editing the inventory by hand to imply capability | the inventory embeds the manifest SHA-256 and must equal a fresh generation byte for byte |
| Shadowing a manifest field with a repeated key | every JSON reader rejects repeated member names; workflow YAML is parsed with repeated-key rejection |
| Changing the event record or buffer so that data is silently lost | validator checks record contiguity and size, unique numeric event codes, cycle count and counter width, and buffer fill time against the slowest drain |
| Supplying malformed or substituted run data | the host rejects duplicate-key JSON, invalid schema versions, escaping paths, missing or mismatched source/artefact/input hashes, malformed binary records and inconsistent CSV series |
| Presenting RTL simulation as board measurement | run manifests label source kind; reports preserve `simulation_only` independently of internal series validity; board input requires declared acceptance state and complete artefacts |
| Shadowing worker readiness or receipt fields | strict UTF-8 object parsing rejects repeated members, including nested counters; readiness checks exact Boolean/PID types and the owned PID |
| Holding a partial readiness frame open | one deadline covers all chunks and the inclusive 4096-byte frame limit; native execution is refused until the complete frame validates |
| Worker policy drift or premature exit | actual CPU/scheduler readback and owned-process exit status are verified; incomplete collection does not produce a completed load receipt |
| Claiming more load than was observed | actual operation counters and worker/native time brackets remain bound to the capture; loopback UDP is not NIC traffic and fsync is not proof of uncached storage |
| Closing a reused descriptor or signalling an unrelated process | owned pipe endpoints close once; production cleanup retains process-group leader identity until reaping; tracing tests retain owned pidfds and verify live parent relationships |
| Accepting a foreign device or writing over evidence | adapters check actual kernel device identity, ownership and ABI before use; native output files are created exclusively |
| Substituting a development dependency | `pip install --require-hashes` refuses any file whose hash is not in the lock; the licence guard refuses a package or version without a reviewed record |
| Tampering with a workflow towards write authority | top-level permissions must be empty, the only allowed write scope is code-scanning upload, write-authority workflows are refused, actions must be commit-pinned, privileged triggers are refused |
| Leaking a secret through a commit | secret scan of the publishable file set locally and of the whole history in CI; private-key detection hook |
| Publishing private notes | `docs/internal/` is ignored; the documentation guard refuses links into ignored paths |

### Fail-closed behaviour

Every tool exits non-zero on any finding and treats a missing file, unreadable or repeated-key
JSON, an unknown schema identifier or an unparsable workflow as a failure. The preflight runner
fails a gate whose tool is missing, cannot run or is not the pinned version.

### Residual risks

- The registry cross-check runs only where the canonical project registry is present; a standalone
  checkout validates manifest-internal consistency only.
- The Go-built tools are verified by module version and checksum recorded in the binary; the Go
  toolchain that reads that record is itself trusted.
- The licence record is a reviewed statement, not an automatic legal analysis.
- No cryptographic signing of commits or of the manifest exists yet. Hashes establish byte
  identity, not authentication against an actor who can edit the artefact and its declaration.
- Workload and executable bounds do not reserve a CPU or exclude other host jobs. Processes with
  the same privileges can alter scheduling or files; actual refusal tests establish specific
  guards, not isolation from a compromised local user.
- Positive MMIO/IRQ, PAC1934 acquisition, power-worker lifecycle, rail calibration and window
  alignment require physical evidence. Builds and emulated missing-device refusals do not
  qualify those paths or the board Linux image.

## Part 2 — planned instrument

### Assets

| Asset | Why it matters |
|---|---|
| Bitstream and job files | define the witness; a modified witness produces plausible but wrong timestamps |
| Firmware, operating-system images and controller binaries | define the system under measurement |
| Event, power and manifest files | the evidence; tampering changes conclusions |
| Safe-state behaviour | an actuator path that fails unsafe would matter as soon as a physical plant replaces the emulator |
| Host link | carries run control and data |

### Misuse paths and planned mitigations

| Misuse path | Planned mitigation |
|---|---|
| A run recorded with a different bitstream or image than reported | manifest records SHA-256 of bitstream, firmware, images and controller binary; host analysis refuses a run whose hashes are missing or inconsistent |
| Event or power files edited after the run | SHA-256 of every file in the manifest; analysis verifies before decoding |
| Silent event loss | buffer overflow counter in fabric; any overflow marks the run invalid |
| Witness defect producing systematic error | known-period, injected-delay and bus-offset tests on the same bitstream before any result |
| Host-link spoofing or interception on a shared network | direct cable or isolated network for runs; the run manifest and file hashes are verified on the host, not trusted from transfer |
| Safe-state failure | hardware deadline monitor independent of the processors; safe-state tests with injected faults; the emulated plant is never replaced by a physical machine inside this project |
| Redistribution of licensed vendor IP | Libero projects generated by scripts; licensed and encrypted IP is never committed |

### Residual risks

- Energy results inherit the rail layout of the board; the core rail is shared by processors and
  fabric.
- A compromised build host could produce a bitstream whose hash is recorded faithfully but whose
  content is wrong; reproducible builds and independent rebuilds are the planned control.
