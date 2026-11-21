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
native Linux run control, UIO/IIO adapters, workload processes, the source-checker workers of the
neural analysis, contracts and workflow definitions. Hardware access code exists; successful
board operation remains unverified.
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
| Native configuration, source snapshots and receipts | identify actual controller inputs, executable, loaded parent project context and completed observations |
| Workload processes and pipes | affect host resources and admit a native run only after bounded, owned-worker readiness |
| UIO/IIO adapters and raw power journal | contain physical access paths whose successful operation is unqualified |
| Neural source registry, checker policies, runtime descriptors, the consumer installation descriptor, the executor image binding and the three worker sources | decide which source-owned checker code the [neural analysis](HOST_ANALYSIS.md#source-bound-neural-analysis) runs on the analysis host, under which interpreter, and which verdict it accepts |
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
- **Source owner of a neural cohort**: its checker code runs on the analysis host during neural
  analysis. It is trusted only for the exact bytes a reviewed registry entry pins, never for code
  or paths that a run bundle names; the operator chooses the installation or executor image.
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
| Supplying malformed or substituted run data | the host rejects duplicate-key or nonfinite JSON numbers, invalid schema versions, escaping paths, missing or mismatched source/artefact/input hashes, malformed binary records and inconsistent CSV series |
| Creating a report destination during staging | the Linux writer checks native publication capability before staging and uses `renameat2(RENAME_NOREPLACE)` to preserve a competing directory, file or symlink; a dangling symlink is also refused before staging |
| Presenting RTL simulation as board measurement | run manifests label source kind; reports preserve `simulation_only` independently of internal series validity; board input requires declared acceptance state and complete artefacts |
| Shadowing worker readiness or receipt fields | strict UTF-8 object parsing rejects repeated members, including nested counters; readiness checks exact Boolean/PID types and the owned PID |
| Holding a partial readiness frame open | one deadline covers all chunks and the inclusive 4096-byte frame limit; native execution is refused until the complete frame validates |
| Worker policy drift or premature exit | actual CPU/scheduler readback and owned-process exit status are verified; incomplete collection does not produce a completed load receipt |
| Claiming more load than was observed | actual operation counters and worker/native time brackets remain bound to the capture; loopback UDP is not NIC traffic and fsync is not proof of uncached storage |
| Closing a reused descriptor or signalling an unrelated process | owned pipe endpoints close once; production cleanup retains process-group leader identity until reaping; tracing tests retain owned pidfds and verify live parent relationships |
| Arming or changing a fault during a run from a process that holds the controller's registers | register map version 2 puts the fault schedule (kind, target cycle, duration, arm) on its own 4 KiB page at offset `0x1000`, and the run page refuses those registers, so a process given only the run page cannot reach them; the UIO run programs map the fault page, a separate UIO device, only to arm the fault before the start, and unmap it before the controlling loop; [`run_configuration_registers.sv`](../rtl/run_configuration_registers.sv) accepts schedule writes only while the run is not started and no fault is armed, and one arm per common reset; the Linux UIO adapters hold an exclusive non-blocking `flock` on each device while they map it |
| Running unreviewed code through a neural run bundle | only a source contract named by a registry entry (schema digest, cohort, source-contract digest) runs; the registry comes from the package or from the caller's own reviewed entries, and a carrier, a copied policy or an acquisition cannot add one; acquired paths and historical argv never select an executable; every source body must match its digest, and the worker sources and runtime files are checked against theirs before and after each checker operation |
| Substituting the interpreter, import roots or environment of a checker | the interpreter, tracer and import roots come from the installation descriptor or executor image binding that the operator selects by absolute path and whose digest the package pins; the worker runs as `python -I -B -S` with a private empty bytecode cache, a cleared environment holding only the fixed variables, and null standard input, under the selected tracer, which records every opened file for comparison with the admitted set (in an executor image, a read-only root, the worker's loaded-file observation replaces the trace) |
| Exhausting the host or reaching the network from a checker | each operation runs in its own process group with a deadline that stops the whole group; the worker sets address-space, CPU-time and file-size limits, disables core files, sets `no_new_privs` and installs a seccomp filter that refuses network system calls on Linux x86-64; reports are bounded to 8 MiB and published without replacing a path |
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
- Commits and run manifests are not signed. Release tags and the published source assets are
  ([source release signatures](SOURCE_RELEASE_SIGNATURES.md)). Elsewhere hashes establish byte
  identity, not authentication against an actor who can edit the artefact and its declaration.
- The UIO lock is advisory. A process that opens a device without taking it, or root through
  `/dev/mem`, can still write its registers: through the run device it can change the run
  configuration before the start and issue controller accesses during a run, and through the
  fault device it can arm a fault before the start. Register map version 2 keeps the fault
  registers on their own page, so withholding the fault device from a process keeps faults out of
  its reach; a bitstream with map version 1 has no such page and the run programs refuse it.
- A neural checker runs with the analysis user's privileges. The limits, the network filter and
  the opened-file comparison bound and expose what it does, but they are not a sandbox: code that
  a reviewed registry entry and a reviewed installation admit is trusted code. The worker refuses
  to start on any platform other than Linux x86-64, where the filter exists.
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


## Dedicated-hart ISA capture

The public ISA capture boundary admits original topology, reserved firmware/telemetry ranges,
PLIC contexts, strict linked firmware and tool identities before execution. Exclusive capture
output preserves failures. It snapshots the verified original inputs and rejects byte drift
in either captured artifacts or executed tools. Analysis refuses contradictions between the
capture receipt, executed tool identities, complete native/model compiler dependency and link
roles, captured original source/header bytes, verified image, configuration, observed tracking
and full fabric event history. Completion requires actual stream drain and logger acknowledgement.
Plugin generation inputs and actual tools are frozen before Verilator runs. Actual compiler
preprocessing freezes native/model source and system-header dependencies before compilation;
post-build reconciliation refuses source, generated build-file, dependency-record or tool drift.
Final receipts must agree with their original preparation, which is retained in capture sources.
The plugin's compile flags are fixed against Make command-line assignments. A counted coverage
variant records its instrumentation in its receipt. Capture and analysis refuse that variant, and
admission refuses a library whose GCC counters disagree with its receipt. A measurement build
therefore cannot pass as an admitted capture.

The functional clock map and parked companion harts do not establish physical U54 latency,
Linux coexistence, HSS configuration or PMP isolation. A malicious compiler, simulator, plugin
or host can forge self-consistent data; artifact hashes do not authenticate those components.
The capture remains simulation evidence under [its public contract](AMP_SIMULATION.md).
