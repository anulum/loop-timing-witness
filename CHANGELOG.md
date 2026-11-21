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

- `control_cost` computes the stationary quadratic cost of a benchmark loop whose command is applied
  after a random delay inside the period, as Jitterbug does: unit-intensity noise at the plant
  input, exact integration between events by Van Loan's block exponentials, and the second-moment
  equation solved after a proof of mean-square stability. `cost_increase` gives the increase over
  immediate application and `empirical_delays` the distribution of measured latencies. A delay of
  almost one period raises the default loops' output variance by at most 0.35 %.

- ADR 0002 (proposed) records the boundary of the source-bound neural analysis: the host
  analysis owns a verifier that depends on no single consumer, a consumer enters only as data in
  a reviewed registry entry, and no consumer source, model, compiled artefact or adapter is
  committed.

### Changed

- The pulse-per-second fit takes each edge's second from the counter: the first edge anchors the
  reference, a later edge counts only at a whole, positive number of seconds after the previous
  accepted one (within one part in a thousand), and `rejected_edges` counts the others, such as a
  ringing second edge. A pulse the reference skipped now spans two seconds instead of shifting
  every later second, and the new `seconds` shows it against the sequence span. The slope's
  standard uncertainty never falls below the counter's quantization (1/12 tick squared per
  edge), so two edges, or edges on whole ticks, no longer report zero. Python and Rust, with the
  shared corpus extended by a ringing edge, a skipped pulse and an edge off a whole second.
- `make fifo-invariants` proves the dual-clock event buffer's rules by temporal induction instead of
  a bounded check of 30 steps: no write when full, no read when empty, and a freely chosen record
  read back unchanged and in order hold in every reachable state at 2, 4, 8 and 16 records. The
  strengthening invariants relate the pointers, their Gray registers and both synchroniser stages
  of each domain; a buffer copy whose write port ignores the full flag is refused with a trace.
- The roadmap's vendor-tool item and the validation record cite the Libero runs of the release
  derivation on MPFS250T and MPFS250T_ES instead of the earlier MPFS250T run.
- The roadmap's bare-metal item states why an emulator cannot replace the board's boot artefacts:
  QEMU's Icicle Kit machine no longer runs the HSS and models no fabric.
- The kernel trace stop's description states that time in machine-mode firmware (OpenSBI or the
  HSS) is not in the supervisor-mode trace.
- The threat model covers the source-checker workers of the neural analysis: the files that decide
  which checker code runs, the source owner as an actor, and the controls against unreviewed
  code, a substituted interpreter or environment, and resource or network abuse, with the residual
  risk that admitted checker code is trusted code. Its UIO residual risk now describes register
  map version 2, whose fault registers have their own page and device.
- The README's related work places the instrument against the tool classes it complements:
  processor-side latency tools (`cyclictest`, the timerlat tracer and `rtla timerlat`), embedded
  logic analysers (SmartDebug live probes, LiteScope), processor trace, time references
  (IEEE 1588, White Rabbit) and control-timing analysis (Jitterbug and TrueTime).
- Source release signatures cover 0.4.0: the registry, the workflow's release choice, the byte-exact
  provenance fixture and the exact public digest lines the secret scanner recognises in it.

## [0.4.0] - 2026-11-21

### Added

- Pulse-per-second reference input: `control_plant_witness` timestamps each rising edge of an
  asynchronous `pps_in` on the 64-bit counter after two synchroniser stages and records it as
  event code 18 (`PPS`, a new `reference_events` member of the CONTROL profile in the measurement
  domain) with its own sequence number in the cycle field. The record waits for a write slot that
  no capture record claims, so the reference never displaces or delays a control event (a plant
  simulation with the pulse gives the same control records as without it); an edge that arrives
  while the previous one waits is not recorded and leaves a gap in the sequence. The synchroniser
  resets high, so a pulse already high at the release is not an edge, and the run is quiescent only
  when no reference record waits. The fabric wrapper, `axi_control_witness` and `icicle_witness`
  pass the input through; the Icicle derivation places `WITNESS_PPS` on ball C14 (J13, `PF_C14`),
  LVCMOS33 with a weak pull-down. J12 and J13 carry the device's live probe pins (C15 and C14),
  which the reference reserves for SmartDebug: the first Libero run of the derivation refused both
  as user-reserved, so the connection script releases them (`RESTRICTPROBEPINS:0`) and the derived
  design offers no live probe.
  - The Python and Rust decoders check reference records on their own (zero reserved bits,
    increasing sequence number and counter value) and keep them out of the cycle checks; both
    domain validators count reference events among the coded names and in the buffer-sizing rule.
  - The native and AMP completion checks count every record of the event file, reference records
    too, as the native drain and the AMP logger do, so a board run with a connected reference keeps
    its completion receipt valid; both analyses refuse a receipt that leaves a PPS record out.
  - The report's new `reference_timebase` member gives the edge count, the skipped edges and an
    ordinary least-squares fit of the counter against the sequence numbers: ticks per second, the
    scale error against the declared clock in ppm with its standard error, and the residuals, with
    the same bits in both languages (shared corpus `control-reference-cases.json`).
  - `docs/MEASUREMENT_PROTOCOL.md` uses the fit in the uncertainty budget in place of the
    oscillator bound, with the reference's own declared uncertainty added.
- Register map version 2: the fault schedule (kind, target cycle, duration, arm) moves to its own
  4 KiB fault page at `0x1000`–`0x100c`; the run page refuses its old offsets `0x58`–`0x64`, every
  other address of the 8 KiB aperture returns SLVERR, the injector status stays at `0x68` and
  `0x7c` reads 2. `axi_control_witness` takes 13-bit addresses and maps the fault page onto the
  unchanged internal decoders; the Icicle FIC0 slot ends at `0x60021fff`. Register addresses are
  16 bits in the native runtime and the AXI process protocol (up to `0x1fff`). `run_uio` maps the
  fault page as its own UIO device (`--fault-uio`, required exactly for a fault run) and unmaps it
  before it writes START; `run_amp_uio` takes it as an optional fourth map of its resource
  configuration; both refuse a map that reaches past its 4 KiB register page. The firmware, the
  Spike plugin and every reader of the version follow it. The threat model, architecture, plant
  witness, AMP and Icicle documents describe the pages.
  The native simulation steps its reset period without sampling the bus: under random initial
  values a local reset that starts low has no falling edge, so a response flag could hold an
  initial value until the domain's first clock edge and meet a sampled bus edge, depending on how
  the values fell. The runtime gate reviews the two response handshakes that only that state could
  reach, with that reason, and the reviewed outcomes move with the shifted lines.
- `docs/AMP_LINUX.md` describes the board placement of the dedicated-hart controller from the MSS
  Technical Reference Manual: firmware in L2-LIM ways that stay disabled as cache, L2 way
  partitioning with the per-master `WayMaskX` registers (hart 4's caches as masters 13 and 14,
  identical front-port masks), and the stress protocol for isolation results (the five host load
  profiles on harts 1–3, three memory arrangements, tail intervals and weakly-hard metrics per
  profile, and the overlap rule for an isolation claim). The runs need a programmed board.
- Kernel trace stop: `run_uio` and `run_simulation` accept `--trace-stop miss|safe --tracefs
  DIRECTORY` (with `--metadata`). They require active tracing, record the selected trace clock,
  and at the first interrupt that sees a missed deadline or the latched safe state write a cause
  marker and switch tracing off, as `cyclictest -b` does, so the ring buffer ends at the cause.
  The native metadata records `trace_stop` (schema, receipt corpus), the run manifest may bind
  the extracted trace as `files.kernel_trace`, and `runtime/linux/trace_stop.h` joins the judged
  sources of `make runtime-coverage`. `run_amp_uio` refuses a trace stop.
- Tail statistics: `python -m loop_timing_witness.tail_intervals REPORT_DIRECTORY` bounds a published
  report's p95, p99 and p99.9 with 95 % moving-block-bootstrap intervals (1,000 resamples of
  blocks of `ceil(n^(1/4))` consecutive samples from a fixed-seed SplitMix64 sequence), checks the
  report's `cycle_intervals.csv` against its own distributions and names both files by digest; a
  quantile is reportable only with ten expected samples beyond it (200, 1,000 and 10,000 samples).
  The native crate exposes the same computation (`witness_analysis::control_tail`), and the shared
  corpus `control-tail-cases.json` holds Python's results, which Rust reproduces bit for bit.
  Every report's `events.control.weakly_hard` gives the `(m, K)` metrics: the largest number of
  misses in any 2 to 1,000 consecutive deadlines and the longest miss run, in both analyses.
- `hardware/icicle/README.md` records a Libero SoC 2026.1.0.17 run for MPFS250T_ES beside the
  MPFS250T run, on the same derived input: timing met in the three corners (smallest setup slack
  +2.152 ns on the FIC1 clock, +2.206 ns on the witness capture clock), the same resource counts
  and a byte-identical CDC report, with the report digests. It is static timing of one placement,
  not board evidence.
- Event mirror outputs for an external time tagger: `control_plant_witness`, the fabric controller
  wrapper, `axi_control_witness` and `icicle_witness` expose `sample_ready_mirror` and
  `actuator_write_mirror`, capture-clock registers that toggle on the edge recording each
  `SAMPLE_READY` and `ACT_WRITE`, and `safe_state_mirror`, which rises with `SAFE_STATE` and holds
  the latched safe state. The Icicle derivation places them on three bank 1 pins that no baseline
  constraint uses (J26 pins 7 and 31 of the Raspberry Pi connector, and J12), from the new
  `hardware/icicle/LOOP_TIMING_WITNESS.pdc`, whose digest the derivation manifest binds; the
  connection script adds the top-level ports and the pins to the place-and-route constraints. The
  plant simulation requires every mirror edge at the counter value of its record, and the
  measurement protocol's acceptance gains the external cross-check: intervals between pin edges on
  the tagger's own timebase must equal the witness intervals within the timebase, edge and pin-skew
  bound. The provenance check covers `.pdc` files.
- `make fifo-invariants` checks the dual-clock event buffer with free write and read clocks over
  every interleaving of 30 steps from reset (four writes and four reads, one wrap of both
  pointers): no write when full, no read when empty, and a freely chosen record read back
  unchanged and in order; the never-full negation yields a counterexample.
- `witness::SimulationOptions` selects the model's initial values (Verilator rand-reset mode and
  seed). The lifecycle corpus, built with `--x-assign unique --x-initial unique`, runs one
  configuration from zeros and from four random seeds and requires byte-identical events, trace
  and result.
- `loop_timing_witness.energy_sweep` separates each rail's static power from the marginal energy
  per cycle: from run reports of one placement at three or more cycle rates and one temperature,
  a least-squares line `P = P0 + E_dyn·f` with standard errors and `r²`, refusing mixed placements,
  invalid reports, too few rates and temperatures beyond a declared tolerance. The measurement
  protocol gains an Energy section (the four PAC1934 rails, the recorded sample rate, the window
  mean and the sweep method).
- `docs/MEASUREMENT_PROTOCOL.md` has a GUM uncertainty budget: the timebase scale from the Icicle
  Kit's 50 MHz reference oscillator (±10 ppm with temperature and supply, ±5 ppm first-year aging,
  from its data sheet), the event phase behind the two-stage request synchroniser (`T/√12` per
  processor end), the calibrated bus offset and oscillator jitter, combined for each interval kind.
- `make safe-state-invariants` proves the deadline monitor's safe-state rules by temporal induction
  for miss limits 1, 3 and 255: the latch sets only on a missed deadline completing `MISS_LIMIT`
  consecutive misses, a latched monitor has counted at least that many misses, the consecutive count
  never exceeds the total, and the latch holds until reset; the never-latches negation yields a
  counterexample. `tests/test_safe_state_proof.py` runs it.
- `container/Dockerfile`, a development and test container: Ubuntu 26.04 pinned by digest, the
  exact apt packages the workflows pin, Python 3.15.2, Rust 1.100.0 and Go 1.27.4, every download
  checked against its SHA-256 and run as an unprivileged user. `tests/test_container_definition.py`
  keeps its pins equal to the workflows', and `VALIDATION.md` shows how to build and use it.
- Differential mutation fuzzing of the run input readers (`tests/test_run_input_fuzz.py`): each case
  mutates one bound input of a real Icarus capture with seeded byte and text changes, re-declares its
  digest and requires the same outcome from the Python and Rust analyses. A fixed-seed batch runs in
  the test suite; the fuzzing workflow gains a job with 200 cases per profile on push and 5,000 on
  schedule, keeping the inputs of any differing case. 6,000 cases passed after the fix below.
- `loop_timing_witness.control_reference` computes the default benchmark loops in float64 from the
  unquantized design values, and finds the exact steady period of a recorded fixed-point loop. The
  long RTL trajectory test now compares each default loop with it: the largest output and command
  differences are below 1500 raw units, and every loop settles on a fixed point (no limit cycle),
  each slightly below the reference; `docs/CONTROLLERS.md` gives the measured values per loop.
- `loop_timing_witness.control_timing` computes a loop's crossover, phase margin, constant delay
  margin and jitter margin (Theorem 1 of Cervin, Lincoln, Eker, Årzén and Buttazzo, 2004: stability
  under any time-varying delay in `[0, N*h]`), and compares measured input-output latencies with the
  jitter margin. Direct simulation of whole-period delays brackets the computed delay margin of the
  default mechanical PID loop. `docs/CONTROLLERS.md` gives the default loops' margins: delay margins
  of 335 to 993 periods and jitter margins of 313 to 2415 periods, so these loops cannot separate
  controller placements by control quality.
- Native run metadata records `host_kernel`, the Linux real-time context of the run: kernel release
  and build string, the PREEMPT_RT flag, isolated and full dynamic tick CPUs, the isolation, tick,
  RCU, interrupt, preemption, idle, watchdog, clock source and mitigation boot parameters, the
  process's locked memory and the current CPU latency PM QoS target. `runtime/linux/kernel_context.h`
  reads it once before the run acquires its device or outputs, in the simulation, UIO and AMP UIO
  programs, and refuses a missing, unreadable or malformed kernel source. The member is optional
  in the native run schema, so earlier metadata stays valid; the shared receipt schema corpus and
  the native coverage gate cover it, and `docs/HOST_ANALYSIS.md` lists every field and source. The
  runtime's reviewed outcomes move with the shifted lines, and one is added: the buffered write of
  the kernel context, whose failure happens at the checked `fclose`.
- The reviewed lists of unreachable C and C++ branch outcomes have a public count table in
  `docs/CONTROLLER_COVERAGE.md`, per list and source (77 runtime and 17 plugin outcomes at this
  release). A test reads
  both lists with the coverage gate's own loader and requires the table and its totals to match, so an
  added entry changes the public table in the same commit and a malformed list fails in the Python
  tests as well as in the native gate.
- A measurement-only counted variant of the Spike plugin:
  `make amp-spike-plugin AMP_PLUGIN_INSTRUMENTATION=coverage` adds GCC counters to the plugin's
  device object (the Spike adapter, its RAM transport and the AMP logger), and only to it.
  - The plugin build receipt records the flags in an optional `instrumentation` member, in the
    schema, the receipt writer and the Python and native validators.
  - Capture, the capture snapshot check and offline analysis refuse a receipt with the member. Only
    an explicit coverage-run selection (`admit_plugin(..., instrumented=True)`) admits one, and that
    selection refuses a production receipt.
  - The writer and admission refuse a library whose counters (`__gcov_init`) disagree with its
    receipt.

### Changed

- `hardware/icicle/README.md` records Libero SoC 2026.1.0.17 runs of this release's derivation
  (`4fca029`) for MPFS250T and MPFS250T_ES: timing met in the three corners with 99.96 % constraint
  coverage, capture clock worst setup slack +2.531 ns and +2.655 ns, no bus-to-capture path among
  the 1000 worst setup paths, the same 12 witness crossings and a byte-identical CDC report.
- The local control-run analysis timing in `docs/HOST_ANALYSIS.md` is measured again at the
  analysis code of this release (`30db584`, with the weakly-hard metrics and the reference
  timebase in every report) on ML350, pinned to CPU 16 under a load average of 13 to 16: run P50
  24.02 s in Python and 1.82 s native, campaign P50 61.85 s and 5.48 s. The deterministic events
  and tracking inputs are unchanged; the manifests differ by the new measurement-domain digest.
- The report's `energy` block names its method, `window_mean`, in the Python and Rust analyses and
  the shared series corpus.
- The README shows the OpenSSF Best Practices badge: the project's record (15127) reached the passing
  level on 2026-11-20 with every passing criterion answered from the repository.
- The RTL, native runtime and plant timing proofs (`make rtl-invariants`,
  `make native-runtime-invariants`, `make plant-timing-invariants`) now prove their assertions by
  temporal induction (`sat -tempinduct`) instead of bounded SAT to a depth of one or four steps.
  Every one of the 25 positive checks closes within two steps, so its assertions hold in every
  reachable state; each negative control still yields a counterexample.
- The threat model covers the fault-injection registers in the controller's register window: the
  hardware accepts their writes only before start and before an arm, and refuses them afterwards;
  the UIO lock that keeps other processes out is advisory, now a stated residual risk. Its residual
  on signatures now says that release tags and source assets are signed and commits and run
  manifests are not.
- `docs/FABRIC_WITNESS.md` states what the witness adds to the measured path: no processor access
  and no back-pressure, with `SAMPLE_READ` and `ACT_WRITE` taken from the controller's own register
  accesses; the bus-to-capture clock crossing that those accesses pay is the instrument floor of
  the bus-offset calibration.
- Every hosted workflow runs on `ubuntu-26.04` (25 jobs, before `ubuntu-24.04`), with the Ubuntu
  26.04 toolchain pinned:
  - GCC 15.2 for native code and `riscv64-linux-gnu-gcc-15` 15.2 for the RV64 firmware;
  - Verilator 5.032, which contains both upstream fixes of the thread-pool abort (issue 4931);
  - Yosys 0.52, Icarus Verilog 12.0-3, OpenSSL 3.5.5, strace 6.19, dtc 1.7.2 and Boost 1.90
    (Boost.System is header-only, so its package is gone);
  - clang 21.1.8 for the fuzzing build, linking GCC 15's C++ library (`FUZZ_GCC_INSTALL`).
    It named GCC 13's, which the hosted image still ships and the 26.04 packages do not.

  The neural source contracts keep the Verilator 5.020 and g++ 13.3 identities of the
  acquisitions they describe, which the runner does not produce. The Verilator build job limit
  of 8, set for 5.020's thread-pool abort, was reviewed under 5.032-1 on 22 processors: 0 of 262
  builds aborted at 22 jobs and 22 jobs built no faster than 8, so it stays for every host.
  VALIDATION, the Makefile and `host_profile` no longer call 5.020 the CI pin. Recorded
  measurements keep the runner and toolchain they name.
  `.github/actionlint.yaml` declares the `ubuntu-26.04` label: the pinned actionlint v1.7.12, its
  newest release, knows the hosted labels only up to `ubuntu-24.04`.
- clang-format 21.1.8 comes from the development lock as the hash-pinned `clang-format` wheel,
  the same binary on every host and runner, instead of the `clang-format-18` apt package.
  `tools/check_native_format.py` requires 21.1.8 and uses the environment's wheel by default.
  - Six files take its brace-initialiser layout.
  - `runtime/coverage-review.json` follows the one line `runtime/linux/file_digest.cpp` lost.
- `tools/c_coverage_gate.py` reads gcov JSON format 2 (GCC 14 and later) as well as format 1. The
  fields it reads are the same in both.
- The reviewed outcomes of both native coverage gates follow GCC 15.2. Each new entry was checked
  in the compiler's control-flow graph of the exact coverage build.
  - On the normal path GCC 15 tests cleanup flags it has already set to 0, so the guarded
    destructions cannot run: `run_simulation.cpp` line 27 (outcome 6), `power_configuration.cpp`
    line 69 (outcomes 0, 4 and 6), and `spike_axi_device.cpp` line 67 (outcomes 4 and 7) and
    line 174 (outcome 6).
  - The landing-pad outcomes moved: `run_simulation.cpp` line 27 to outcomes 8, 10 and 11,
    `spike_axi_device.cpp` line 67 to outcomes 8 to 11 and line 174 to outcomes 8 and 9.
  - The vector assignment's cleanup of the `artifacts` initialiser is on `run_simulation.cpp`
    line 40 (outcomes 2 and 3), no longer on line 38.
  - Outcome 12 of the plugin's `REGISTER_DEVICE` line is named for what it completes, the
    `runtime_error` construction.
- `make plugin-coverage`, run in hosted shard 4, requires every line and branch outcome of the
  Spike plugin's device object to run: `runtime/isa/spike_axi_device.cpp`,
  `runtime/isa/spike_amp_transport.h` and `runtime/amp_logger.h`.
  - It builds the counted variant of both plant plugins and runs the direct Spike corpus with them,
    the diagnostic variants passing the counters on.
  - The capture refuses the variant. A run with the capture tests counted the same outcomes as one
    without them.
  - `runtime/isa/plugin-coverage-review.json` lists the outcomes no real surface reaches, each with
    its reason. Examples are cleanup landing pads, which never run because Spike catches no exception,
    and requests Spike's bus never passes to a device.
  - New scenarios: `tests/test_amp_device_probe.py` calls the unchanged device's public `load` and
    `store` refusals and its registry device-tree callback, then completes the run. A device tree
    whose PLIC is `sifive,plic-1.0.0` is refused by the device. Loading both plant plugins into one
    Spike is refused (`Plugin "witness_axi" already registered`).
  - `tools/c_coverage_gate.py` accepts a line that gcov lists for several functions, some without
    branches. Spike's `REGISTER_DEVICE` places such functions on one line; a branchless record adds
    only its line count.
- `make runtime-coverage`, run in the hosted controller shard, requires every line and branch
  outcome of the judged host C++ runtime sources to run: `exclusive_output.h`,
  `run_configuration.cpp`, `run_options.h`, `run_output.h`, `run_control.h`, `run_metadata.h`,
  `rtl/run_simulation.cpp`, `rtl/simulation.h`, `linux/file_digest.cpp`, `linux/run_policy.h`,
  `process_protocol.h`, `rtl/axi_simulator.cpp` and `linux/power_configuration.cpp`. It builds every
  native test corpus with counters on the runtime sources only (`OPT_FAST=-O0` through `MAKEFLAGS`,
  `-fprofile-filter-files`; the Verilator model keeps `-O2`). `runtime/coverage-review.json` lists,
  each with its reason, the outcomes no real surface reaches. `tools/c_coverage_gate.py` now also
  judges named C++ files, reports C++ exception edges without requiring them and refuses a reviewed
  entry whose outcome or line runs; its messages start with "GCC coverage".
- New scenarios for that gate: eight scheduling scenarios have the kernel answer one system call
  through seccomp in the test's own child, reaching the policy read refusals and readback checks;
  refusal cases cover duplicate `--metadata`, `--power-config`, `--power-journal`, `--scheduler` and
  `--priority` options and a non-numeric number; a lifecycle scenario fails the event file's final
  flush; a metadata API scenario fails the receipt's final write under a file-size limit; an LQR
  run's receipt passes the importer; a run built with a four-record event FIFO overflows and exits
  with status 1; four more hashing mutations change the modification time by a second or a
  nanosecond, the change time alone, or replace the configuration's directory; the AXI process
  refuses a command argument, an unreadable request stream and a full output, and ends cleanly when
  its input closes; ten malformed power configuration files reach every refusal of the file reader.
  The AXI simulator target takes `AXI_SIMULATOR_LDFLAGS`; the scheduling and power configuration
  corpora build with counters only under `WITNESS_POLICY_COVERAGE_DIRECTORY` and
  `WITNESS_POWER_COVERAGE_DIRECTORY`.
- Verilator builds use at most 8 jobs, a reviewed policy limit kept apart from the host-derived
  limits: `VERILATOR_JOBS` defaults to the host's processors up to `VERILATOR_JOB_LIMIT`, and the
  tests use `host_profile.verilator_jobs()`. Verilator 5.020 can abort after a complete link
  ("attempted to destroy locked Thread Pool", upstream issue 4931): on a 24-processor host, 4 of
  220 interleaved builds aborted at 24 jobs and 0 of 220 at 8 jobs, at equal build time. The
  control-run benchmark workflow no longer overrides the default.
- The hosted test shards raise their real-time limit to priority 1 (`sudo prlimit --rtprio=1:1`),
  and `test_fifo_permissions` asks the kernel through an independent child whether SCHED_FIFO at
  priority 1 is permitted, then requires the native run to apply it or to refuse with EPERM. It
  accepted either outcome before, and every host had run only the refusal.
- `witness-controller` 0.3.0 is on crates.io, published on 2026-11-16 by `publish-rust.yml` from
  `7ed2ce5` (crate checksum `9c9e0edc3fd35ff6db27ada3a95adda0c58e59b2abbb2a6a04230f473cc7b2bd`, equal
  to the verified crate the workflow retained). Its sources equal those of the 0.3.0 tag, and its
  library is unchanged since 0.1.0.
- The Rust crate publishing workflow packages the verified crate after its dry-run publish. Under
  Cargo 1.100 a dry-run publish leaves the crate only under `target/package/tmp-crate`, so the
  workflow's digest and retained artifact found no file and nothing was published; the added
  `cargo package --locked --no-verify` writes the same bytes to the retained path.
- Every hosted workflow step that installs the pinned Rust 1.100.0 toolchain uninstalls it first, so a
  partial toolchain already on the runner cannot conflict with the component install. One PR run
  failed so ("failed to install component: 'clippy-preview-x86_64-unknown-linux-gnu', detected
  conflict: 'bin/cargo-clippy'"), while another runner logged "recovering from a partially installed
  toolchain".
- `capture_quiescent` (in `control_plant_witness`) and the run-bank reset permission (in
  `axi_control_witness`) are capture-clock registers, one capture edge behind their terms, before
  their bus-clock synchronisers. At a run's end the event strobes clear on the edge a record
  appears; the combinational quiescence could pulse high there and let `run_drained` report a
  drained run before its last records. `rtl/check_synchroniser_inputs.ys` requires register
  outputs at those synchroniser inputs.
- `clock_request_bridge` registers the held request in the capture domain: `capture_data` follows
  the bus-held payload while `capture_valid` is low and holds it while high, so it loads on the
  edge that completes the request toggle's synchronisation. Every port keeps its cycle-by-cycle
  behaviour while `capture_valid` is high. Destination decode now starts from a capture-clock
  register instead of crossing the bounded clock-domain path; the Libero run of the tree with the
  capture lock reset had missed that path's 8 ns bound by 0.051 ns.
- `icicle_witness` takes `capture_clock_locked`, the lock of the capture clock's PLL, and holds
  both witness clock domains in reset while it is low, as a low `run_reset_n` does; losing the
  lock resets the run. The Icicle witness script routes `WITNESS_CCC`'s `PLL_LOCK_0` there
  instead of leaving it unused, so the capture domain no longer leaves reset on an unlocked
  clock.
- The recorded Libero SoC 2026.1 run of the derived design for MPFS250T (STD), on the tree of
  `0fea6ea`, meets every clock: the 100 MHz witness capture clock with setup +2.152 ns and hold
  +0.069 ns, the reference clocks with +2.508 ns or more; every witness crossing is constrained,
  and the synthesis CDC check lists 12 witness crossings instead of 55, none fed through logic.
  The Icicle README records the slack table, the CDC summary, the resources and six report
  digests.
- `control_event_capture` keeps a register copy of the head group's timestamps, loaded from the
  next queue slot when a group leaves and written through when the pushed group becomes the head,
  so record selection starts from a register instead of a queue read. Every output is the same in
  every cycle, `record` while `record_valid` is high; `record` is defined only then.
- The Icicle derivation constrains the witness clock-domain crossings. It edits the reference
  `fic_clocks.sdc` as a third pinned vendor file: the FIC0 clock group also holds the witness
  capture clock, so the paths between the two are analysed instead of cut as asynchronous;
  `set_max_delay 8` bounds every such path in each direction, and `set_min_delay -8` releases the
  hold check derived from the two clocks' phases. Both clocks stay asynchronous to every other
  clock. The refusal for a changed derived file now reads "derived vendor file changed".
- The plant and the reference form each 32 × 32 product one capture edge before it is used.
  `rtl/split_multiplier.sv` registers four 17 × 17 half products, whose shifted sum is exact;
  the sampling cycle keeps the sum, floor, offset and saturation. Every output of
  `control_plant_witness` is the same in every cycle. `sampled_plant` takes `actuator_load`,
  `actuator_command` and `actuator_safe` in place of `actuator`, `control_cycle` reports
  `actuator_accept` in place of `plant_actuator`, and `fixed_point_math` sums three exact
  products. Module contract: no samples in consecutive cycles; the reference's mode and
  amplitude unchanged over the edge before a sample. `make plant-timing-invariants` proves the
  invariants behind this, with a counterexample to each negation. The RTL source-flow union
  becomes 816 of 822 points with six invariants: `fixed_point_math` has one elaboration that
  every plant step shares, so its two thermal-binding invariants no longer apply.
- `tools/release_provenance.py collect` keeps the complete earlier registry artifacts a
  specification lists and reads PyPI only when none of them is a PyPI file, so a source release
  without a registry upload can be collected. It refuses, in its own words, while a hosted run of
  the commit is unfinished; it raised a `TypeError` before.
- Source release signatures cover 0.3.0: the registry, the workflow's release choice, the byte-exact
  provenance fixture and the exact public digest lines the secret scanner recognises in it.

### Fixed

- The RTL simulation wrapper starts every model input idle before the first evaluation. It set
  only the reset input, so with random initial values the bus handshake inputs, which an AXI
  master must hold low during reset, started random and a spurious transaction was refused; the
  random-initial-value test found it.
- The Rust analysis matches schema patterns without recursion. The former matcher took a few stack
  frames per repeated character and aborted the native analysis with a stack overflow on a manifest
  string of about 5,000 characters, which Python refused or accepted normally; the differential
  fuzzer found it. Patterns now compile to a small instruction program run breadth-first over the
  text, so time and stack no longer grow with nesting. Repetitions that may match empty now count
  towards a minimum as in Python (`^(a?){2}$` matches the empty text); no committed schema pattern
  has such a repetition.
- Series values keep only their significant digits, with trailing zeros moved into the exponent as
  the Rust reader stores them. A value with more than 4300 trailing zeros (`1` followed by 4400
  zeros and `e-4400`) used to keep them, and under a CPython without the C decimal module its first
  arithmetic stopped at the interpreter's 4300-digit integer-string limit; the C module and the
  Rust reader computed it. The shared series corpus gains two such values and one operation, kept
  out of the random operand pool so every other case stays as committed.
- The AMP build toolchain and simulator identities admit the loader's record of the listed
  program itself. On the hosted `ubuntu-26.04` runner, glibc 2.43's `ld.so --list` begins with a
  nameless record at the listed program's load address, which was refused as an unresolved
  library. `tools/amp_tool_runtime.py` skips that record only as the first record, and only at
  the program's fixed load page (position-dependent tools such as the GCC driver, `cc1` and
  `collect2`) or at a page address (position-independent tools and the plugin library). The
  program's bytes are hashed separately, and any other nameless record is still refused. A
  refusal quotes the complete loader listing.
- `tools/closed_loop_run.py` prepares every repeat (sources, declarations and harness copy)
  before any harness runs, then runs the repeats in parallel.
  - Before, each thread copied its harness while other threads forked their runs. A child forked
    in that window kept the copy's write descriptor until it executed, and running that copy
    failed with `Text file busy` (ETXTBSY).
  - One five-repeat campaign on a loaded Ubuntu 26.04 host lost its last repeat this way.
- The Spike plugin's compile flags are fixed (`override`). An assignment on Make's command line,
  such as `make amp-spike-plugin AMP_PLUGIN_CXXFLAGS=-O0`, used to build a plugin with other flags.
  Its receipt, which binds the makefiles but no flag, looked like a production one. Production
  admission also accepted a plugin carrying GCC counters; it now refuses one whose receipt does not
  record them.
- The AXI simulator and UIO transport processes refuse a request stream that fails to read
  ("cannot read AXI request", status 1). `std::cin` reads through stdio, which reports a read
  error as end of file, so a failed stream, such as a directory given as input, ended with
  status 0 as if complete; `std::ferror(stdin)` now tells the two apart.

## [0.3.0] - 2026-11-16

### Added

- Closed-loop benchmark data: `make closed-loop-harness` builds a Verilator harness over the
  production `control_plant_witness` at the minimum declared period with the production FIFO
  depth. `tools/closed_loop_run.py` writes hash-bound repeat runs and their campaign. A seeded
  service stimulus reads and writes at declared offsets with the production C PID kernel,
  withholds one write in 97 cycles and injects one tripping delay fault. Python and native
  analyses publish byte-equal reports for these runs.
- Control-run analysis timing: `tools/benchmark_control_runs.py` times the Python and native run
  and campaign commands on a closed-loop campaign of five 2·10⁵-cycle repeats, pinned to one CPU.
  It uses one warm-up and five measured passes, requires byte-identical reports in every pass, and
  records percentiles, peak memory and provenance. The dispatched `control-run-benchmark.yml`
  workflow regenerates the data on the fixed runner, holds them to the committed digests and
  uploads its measurement. The hosted result is `benchmarks/control_run_analysis.json` and the
  local result `benchmarks/control_run_analysis.local.json`.
- Release asset builder: `tools/release_provenance.py collect` reads a version's PyPI
  distributions, the listed crate publications and the commit's hosted workflow runs into a
  release specification; `build` writes the source ZIP and `release-provenance.json` from the
  tagged commit offline, computing the archive size, digests and per-file SHA-256 from the
  commit's tree. The tests rebuild both published records and ZIPs; the 0.1.0 record is rebuilt
  byte for byte. See
  [building the release assets](docs/SOURCE_RELEASE_SIGNATURES.md#building-the-release-assets).

### Changed

- The Rust controller crate is under the hosted 100 % native coverage gate.
  `make controller-tests` runs `make controller-rust-coverage`: crate tests, one benchmark pass
  and the shared stream and refusal tests against an LLVM branch-instrumented build, gated by
  `tools/rust_coverage_gate.py --crate controllers/rust` (208 lines, 52 branches). The
  benchmark program's unreachable coefficient error path is now an `expect`, as in the
  streaming program.
- Source release signatures cover every registered release. `source-release-signatures.yml` takes
  a required `release` choice; `tools/source_release.py` holds a frozen registry of each release's
  source commit and published asset digests, refuses a tag that names another commit and records
  the chosen tag in the predicate. The workflow auditor requires the choice options to equal the
  registry. Release 0.2.0 is registered with its byte-exact provenance record and the exact
  public digest lines the secret scanner recognises in it.
- The native run command writes `cycle_intervals.csv` and `cycle_jitter.csv` row by row as the
  rows are formed, instead of building both tables in memory first. On a 2·10⁵-cycle benchmark
  repeat its peak memory falls from about 2.1 times Python's to about 0.31 times, with
  byte-identical reports. The local control-run timing is re-measured on ML350.
- The native RTL simulation transport evaluates the model only after an input or clock change.
  It still steps one nanosecond at a time, but a step with unchanged inputs and no clock edge no
  longer evaluates. The native run simulator writes byte-identical outputs for both plants, PID
  and LQR, every reference and every injected fault; a 60-cycle PID run at the compiled period
  takes 2.11 s instead of 3.61 s (median of six alternating runs on ML350).
- The derived Icicle project generates in Libero SoC 2026.1 for MPFS250T. The first Libero run
  refused the derived design, so the witness script now adds the witness HDL core as an AXI4
  target on FIC0 slot 2, MSS interrupt bit 11 and a separate 100 MHz CCC after the base design
  has generated. The derivation edits only the reference script and FIC0's interconnect and
  keeps the reference's design-rule settings. The reference CCC has no free output, and a
  SmartDesign input left for later is refused when the base design generates.
- The capture group queue picks each record with a three-level comparison tree and pops a group
  from its remaining-event mask. Before, an eight-step scan chose the record, and its result also
  gated the pop, the queue-full rejection, the loss sum and the saturation of `overflow_count` in
  the same capture cycle, the longest path of the capture clock domain in Libero's timing analysis.
  Every output is unchanged in every cycle: a SAT proof of the selection and pop logic over all
  inputs, and co-simulation of both versions. The RTL source-flow union now has 822 of 830 points
  executed: each of the file's two elaborations lost the scan's two branch points.
- A recorded Libero SoC 2026.1 run of the derived design for MPFS250T (STD) is documented with its
  report digests: every reference clock meets timing; the 100 MHz witness capture clock misses
  setup by 2.419 ns in the plant model and reference generator; hold is met; CDC constraints for
  the witness are still to be written.

## [0.2.0] - 2026-11-14

### Added

- Native AMP repeat campaigns: the native campaign command no longer refuses a campaign whose
  repeats bind AMP captures. Each repeat's report attaches the capture as a single run does; a
  refused capture refuses the repeat and an artifact that cannot be read refuses the campaign, as
  Python's `OSError` does. A parity test on campaigns of real Spike captures holds both commands to
  the same output.
- Native AMP run analysis: the native report completes a run that binds an AMP capture as the
  Python report does, admitting the capture and every artifact it binds and holding the run
  declaration and the logger's counters to them, with Python's refusal texts and read errors. A
  parity test on real Spike captures, C and Rust kernels, and 39 changed copies holds both analyses
  to the same report or refusal.
- Native AMP tracking CSV and fault schedule in the Rust analysis crate: the public
  `amp_observations` module writes a capture's observed tracking as Python's `csv.writer` and
  `Decimal` write it, byte for byte, and reads the configured fault schedule. A corpus of raw values,
  tracking tables and run configurations holds both implementations to the same outcomes.
- Native AMP completion and capture stream checks in the Rust analysis crate: the public
  `amp_completion` and `amp_tracking` modules read the logger completion, decode the raw controller
  tracking and hold the completion to the captured events and tracking with the Python readers'
  refusal texts. A corpus of the real ISA capture, changed per rule, holds both implementations to
  the same outcomes.
- Native AMP image receipt checks in the Rust analysis crate: the public `amp_image_receipt`
  module checks a captured image's declarations, recorded verification request, platform, run,
  firmware contract and exit channel with the Python check's refusal texts and read errors. A
  corpus of a real image folder, changed per rule, holds both implementations to the same outcomes.
- Native AMP image contract and exit channel admission in the Rust analysis crate: the public
  `amp_image_contract` and `amp_exit_channel` modules admit a firmware image's constants, entry
  points, stack geometry and ISA completion channel with the Python checks' refusal texts. A corpus
  of the committed whole firmware, changed per rule, holds both implementations to the same
  outcomes.
- Native AMP run configuration reading in the Rust analysis crate: the public `amp_run_input`
  module reads an image's native run configuration with the Python reader's separators, field
  rules and refusal texts. A corpus of the ISA image's configuration, changed per rule, holds both
  implementations to the same outcomes.
- Native AMP platform binding in the Rust analysis crate: the public `amp_platform` module admits
  the firmware and telemetry reservations, the Witness device with its PLIC source and aperture,
  and the PLIC aperture from a decoded device tree, with the Python binding's refusal texts. A
  corpus compiled by the real `dtc` from the repository's Spike platform holds both
  implementations to the same outcomes.
- Native AMP Rust kernel checks in the Rust analysis crate: the public `amp_rust_receipt` module
  checks an image's captured Rust preparation, snapshots, dependency records and compiled outputs
  against the image's receipts, with Python's refusal texts and read errors. A corpus laid out as
  a real Rust kernel image holds both implementations to the same outcomes.
- Native AMP plugin receipt checks in the Rust analysis crate: the public `amp_plugin_receipt`
  module decodes a plugin build receipt and checks it against its preparation, and
  `amp_plugin_snapshot` checks a capture's plugin receipt and source copies, with Python's
  refusal texts and read errors. A corpus built from a reduced real receipt holds both
  implementations to the same outcomes.
- Native AMP snapshot checks in the Rust analysis crate: the public `amp_runtime_snapshot` and
  `amp_image_dependencies` modules check an image's or capture's runtime library and firmware
  preprocessing source copies against their index and the recorded identities, and read the
  preprocessing record count of a kernel backend, with Python's refusal texts and read errors.
  A corpus of trees built by Python's own snapshot writers holds both implementations to the
  same outcomes.
- Native Rust dependency record reading in the Rust analysis crate: the public
  `amp_rust_dependencies` module hashes the sources that rustc's dependency records of an AMP
  image name, with the Python reader's digests, refusal texts and read errors;
  `amp_failure::AmpFailure` tells a read error from a refusal. Its port of CPython's POSIX
  `shlex.split` and the reader are held to a corpus built from Python's own lexer and reader.
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

- Hosted workflows use Go 1.27.4 and cargo-audit 0.23.0; `make security` requires the same auditor.
- The native crates build with Rust 1.100.0, also their minimum supported version; every hosted
  workflow, the toolchain files, the source enrolment pin and the guides move with them.
- The analysis crate's lock moves const-oid to 0.10.3 and errno to 0.3.15; the licence record and the
  third-party notices carry their archives, whose MIT texts are unchanged.
- Development tools move to their newest releases: Ruff 0.17.5, coverage 7.17.3, typos 1.52.2,
  markdown-it-py 4.3.0, the PyYAML typing stubs and jsonpointer 3.12. All three locks share one upload
  cut-off, 2026-11-14T14:00Z; the runtime and build locks resolve unchanged.
- `VALIDATION.md` names the policy limits apart from the host-derived ones: the hosted jobs'
  `timeout-minutes`, the neural checker's sandbox limits, the commands' 3600-second maximum
  `--timeout`, the fuzz target's per-input memory limit and the PyPI request's network timeout.
- Build parallelism follows the executing host instead of two jobs: the Makefile's Verilator builds
  use `VERILATOR_JOBS` (by default `nproc`), the tests build generated image Makefiles with every usable
  processor, and the hosted workflow builds Spike and the image with `make -j"$(nproc)"`. The
  Makefile's Yosys proofs' bound and the fuzz target's per-input bound are now the overridable
  `SAT_TIMEOUT` and `FUZZ_INPUT_TIMEOUT`, which the tests pass scaled for the host.
- The native crate's integration tests bound their child processes with `timeout(1)` durations
  scaled by the same declaration. A corpus of declarations shared with the Python tests holds both
  readers to the same scale, whole-second rounding and refusal.
- Tool hang guards follow the executing host as the tests' do: toolchain probes, benchmark and
  capture commands, the native analysis SBOM check, the load worker's loopback receive and the load
  launcher's readiness wait, cleanup waits and default `--timeout` are multiplied by the declared
  timeout scale. The load launcher refuses an invalid declaration before it creates its journal or
  workspace.
- Test hang guards follow the executing host: each is written for the reference profile and is
  multiplied by the timeout scale a host declares in `WITNESS_HOST_TIMEOUT_SCALE`, which the new
  `loop_timing_witness.host_profile` module reads and validates. Without a declared scale every
  guard keeps its value.
- Raw tracking cells accept leading zeros at any length and refuse a magnitude longer than any
  column's bound as outside its ABI bounds, instead of failing with the interpreter's integer
  string conversion limit text past 4300 digits.
- A captured measurement domain is held to the measurement-domain schema, its semantic rules and
  the 16-byte event wire layout, as a run's domain is, before its contracts decode the captured
  events. A capture whose domain lacked its contracts failed with the interpreter's `KeyError` or
  `TypeError` text instead of a refusal.
- The AMP run configuration reader separates fields only at the C locale's whitespace, as the
  native reader does; the ASCII information separators no longer separate fields. Whole numbers
  with more than 4300 digits (leading zeros included) are read as the native reader reads them,
  instead of being refused with the interpreter's integer string conversion limit text.
- An AMP plugin build receipt whose preparation path names no file (the root folder) is refused
  as `AMP plugin receipt omits or contradicts original preparation identities` instead of with
  pathlib's `PosixPath('/') has an empty name`.
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
