<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — native controller coverage reproduction
-->

# Native controller coverage

Every line and branch of the C controller kernel and its streaming CLI, and of every source
of the Rust controller crate, is required on every hosted test run; see
[C controller gate](#c-controller-gate) and [Rust controller gate](#rust-controller-gate).
The host C++ runtime sources are gated the same way, apart from reviewed unreachable outcomes;
see [Host C++ runtime gate](#host-c-runtime-gate).
[`controller_coverage.json`](../benchmarks/controller_coverage.json) binds source hashes
to the GCC and LLVM reports of an earlier recorded snapshot, with 100% executable line
and branch coverage of both controller kernels and their streaming CLIs. Its C source
hashes no longer match the current files, so for C it is historical; the gate is the
current evidence. Its Rust controller hashes still match. The retained reports include
the earlier Rust 1.98.1 build; they are historical evidence and do not certify a new
compiler. These counts exclude benchmark harnesses and SystemVerilog. They establish
host execution coverage, not board qualification.

Production Rust builds use 1.100.0. Stable LLVM coverage additionally reports complete line,
region and function coverage for the library and CLI, but does not instrument branches.
The separate branch analysis uses `nightly-2026-08-21`, with `llvm-tools-preview`, without
changing the production compiler or disabling any branch. GCC 15.2.0 (the hosted Ubuntu
26.04 compiler) uses `--coverage`.
Build outputs and raw reports remain under ignored `build/` and the crate's `target/`.

## Python coverage report in CI

The CI test job requires 100% Python statement and branch coverage for
`src/loop_timing_witness`, `tools` and `controller_test_support.py`. It also writes
`build/coverage/coverage.xml` through [`export_python_coverage.py`](../tools/export_python_coverage.py).
The export preserves repository-relative paths, including equal basenames in different
source directories, without changing the collected source set or coverage threshold. A successful test job retains that report, its SHA-256
and the tested commit as the `python-coverage-<commit>` artifact for seven days.

A separate job runs only on `main`, after the test job succeeds. It downloads the
artifact from the same workflow run and verifies its digest and commit against the
exact checkout before uploading only that XML report to Codecov with the `python`
flag. OIDC authentication belongs to the `codecov` environment; test execution has
only repository read permission. An upload error fails the CI category and its
required gate. Pull requests retain the test report without publishing it.

This report describes the configured Python source set. It does not measure C, C++,
Rust, SystemVerilog or physical hardware. Those surfaces need their separate
instrumented evidence below.

## C controller gate

`make controller-tests` ends with `make controller-coverage`, and the hosted test shard
that runs the controller tests runs it at every push. The target:

1. compiles the kernel with `tests/native/controller_api_test.c` using GCC `--coverage
   -fprofile-abs-path -O0` and runs that test;
2. runs `tests/test_controller_inputs.py` and `tests/test_controller_parity.py` with
   `WITNESS_C_COVERAGE_DIRECTORY` set, so the shared fixture builds the CLI with counters in
   that directory and every real stream, refusal and operating-system boundary case runs
   against it;
3. exports each program with `gcov --json-format --branch-probabilities`;
4. runs [`c_coverage_gate.py`](../tools/c_coverage_gate.py), which adds the counts of all
   programs line by line and branch by branch. Every executable line and every branch
   outcome of every `.c` file in `controllers/c` must have run. A new file there fails until
   it is measured, and a line whose branch structure differs between programs is refused.

The coverage builds omit the undefined-behaviour sanitizer. Its boolean-load check adds a
branch that only undefined behaviour can take, so complete branch coverage would be
unreachable with it. The sanitized API test above and the sanitized CLI used by every other
test keep it. The target's outputs stay in ignored `build/c-controller-coverage`.

## Rust controller gate

`make controller-tests` then runs `make controller-rust-coverage`. It uses the
instrumentation of the native analysis gate, the production Rust 1.100.0 compiler with
`RUSTC_BOOTSTRAP=1` and `-C instrument-coverage -Z coverage-options=branch`. The target:

1. runs the crate's own tests (`cargo test`) instrumented in its own target directory and
   selects every executable from Cargo's JSON messages;
2. runs the `controller_benchmark` program once;
3. runs `tests/test_controller_inputs.py` and `tests/test_controller_parity.py` with
   `WITNESS_RUST_COVERAGE_DIRECTORY` set, so the shared fixture builds the instrumented
   streaming program in that directory and every stream and refusal case runs against it;
4. merges every profile with `llvm-profdata` and exports the summary of
   `controllers/rust/src` with `llvm-cov`;
5. runs [`rust_coverage_gate.py`](../tools/rust_coverage_gate.py) with `--crate
   controllers/rust`. Every line and branch of `lib.rs`, `main.rs` and
   `bin/controller_benchmark.rs` must have run, and an unmeasured new source fails.

The outputs stay in ignored `build/rust-controller-coverage`. Without the streaming-program
runs the gate fails: `main.rs` has 0 of 84 lines and `lib.rs` 33 of 36 branches. The
benchmark's step uses `expect` for its constant, valid coefficients, as the streaming program
does after validation, so no unreachable error path remains in the crate.

The manual procedure below reproduces the recorded snapshot of both languages.

## Host C++ runtime gate

`make runtime-coverage`, run in the hosted shard that runs the controller tests, judges the
host C++ runtime over every native test corpus at once: the run command line, the lifecycle,
configuration and metadata API corpora, the AXI process, the power configuration corpus and the
scheduling corpus described under
[native run controller instrumentation](#native-run-controller-instrumentation). Each builds
with GCC counters on the files under `runtime/` only; `MAKEFLAGS=OPT_FAST=-O0` reaches
Verilator's sub-make, which compiles the runtime sources unoptimised (the generated makefile
puts `OPT_FAST` after `CFLAGS` for them) while the model keeps the `-O2` of `CFLAGS`. The
target exports every report and runs [`c_coverage_gate.py`](../tools/c_coverage_gate.py) on
the judged sources:
`runtime/exclusive_output.h`, `runtime/run_configuration.cpp`, `runtime/run_options.h`,
`runtime/run_output.h`, `runtime/run_control.h`, `runtime/run_metadata.h`,
`runtime/rtl/run_simulation.cpp`, `runtime/rtl/simulation.h`, `runtime/linux/file_digest.cpp`,
`runtime/linux/run_policy.h`, `runtime/process_protocol.h`, `runtime/rtl/axi_simulator.cpp` and
`runtime/linux/power_configuration.cpp`.
More runtime sources join the list as their scenarios land.
Every executable line and every branch outcome must have run, with two exceptions:

- [`runtime/coverage-review.json`](../runtime/coverage-review.json) lists the outcomes no real
  surface reaches, each with its condition and reason, and the lines only they reach: for
  example a negative `sched_getcpu` (glibc answers it from the rseq area or the vDSO, without a
  system call), a failed `CPU_ALLOC`, the bounds checks inside the glibc mask macros, a FIFO
  priority below the Linux minimum (validation refuses it first), buffered `fprintf` and `fputs`
  calls whose writes and failures happen at the following flush or close, states the code
  never creates, and the cleanup flags GCC 15 sets to 0 on the normal path before it tests
  them. A listed outcome or line that runs fails the gate, so the list cannot go stale.
- GCC adds an exception edge at every C++ call that may throw; the gate reports how many ran
  and does not require them.

The reviewed outcome numbers, here and in the plugin list below, are those of GCC 15.2, the
hosted Ubuntu 26.04 compiler. GCC 13 numbers some cleanup outcomes differently, so it fails
both gates on otherwise complete coverage.

The policy priority readback scenario runs a FIFO priority 1 thread, so the target refuses to
start without `RLIMIT_RTPRIO` of at least 1; the hosted step raises it with `sudo prlimit`.
Without that permission the scenario verifies the kernel's refusal of FIFO instead, and the two
outcomes it would cover stay untaken.

## Spike plugin device gate

`make plugin-coverage`, run in hosted shard 4, judges the Spike plugin's device object:

- `runtime/isa/spike_axi_device.cpp`;
- `runtime/isa/spike_amp_transport.h`;
- `runtime/amp_logger.h`, in its Spike instance. The Linux UIO instance needs the board.

**What the target does.**

1. It builds the
   [measurement-only counted variant](AMP_SIMULATION.md#measurement-only-counted-variant) of both plant plugins.
2. It runs the direct Spike corpus with them in place of the production plugins. This corpus covers:
   - argument, topology and completion refusals;
   - the logger's public API;
   - architectural, startup, consumer, cycle, kernel and interrupt faults;
   - the public device interface probe.
3. It exports every report.
4. It runs [`c_coverage_gate.py`](../tools/c_coverage_gate.py) on the three sources.

Diagnostic variants built on the counted plugins add the same counters. Their own copied sources lie outside
`runtime/` and get none, while the production headers they include are counted.

**Why the capture tests are not in the corpus.** The capture refuses the counted variant. A corpus run with the
capture tests counted exactly the same lines and outcomes as one without them, so the capture tests keep the
production plugins in the normal shards.

**Three facts behind the reviewed list.**

- Spike catches no exception. A refusal ends through `std::terminate`, and Spike's own abort handler then exits
  through `exit`, so the counters of a refused run are written. GCC's unwinder, finding no handler, runs no
  cleanup on the way. The cleanup landing pads on throw paths therefore never run.
- Spike's bus passes a device only an access that lies whole inside it. It passes a misaligned word only under
  `--misaligned`.
- On the normal path GCC 15 sets a cleanup flag to 0 once the object it guards is complete, and only then tests
  it, so the guarded destruction or deallocation under that test never runs.

[`tests/test_amp_device_probe.py`](../tests/test_amp_device_probe.py) includes the production device source verbatim.
It calls the public `load` and `store` interface with the requests Spike's bus never forms, and asks Spike's registry
for the device-tree text that Spike requests only for built-in devices.
[`runtime/isa/plugin-coverage-review.json`](../runtime/isa/plugin-coverage-review.json) lists the remaining
outcomes, each with its reason.

## Compile instrumented public interfaces

Run from the repository root with its development environment installed. Use a fresh
output directory so profiles from a different source revision cannot be merged.

```bash
mkdir -p build/controller-coverage
gcc -std=gnu11 -O0 --coverage -Icontrollers/c -c \
  controllers/c/witness_controller.c -o build/controller-coverage/kernel.o
gcc -std=gnu11 -O0 --coverage -Icontrollers/c build/controller-coverage/kernel.o \
  controllers/c/controller_cli.c -o build/controller-coverage/controller_cli
gcc -std=gnu11 -O0 --coverage -Icontrollers/c build/controller-coverage/kernel.o \
  tests/native/controller_api_test.c -o build/controller-coverage/controller_api_test
build/controller-coverage/controller_api_test
rustup component add --toolchain nightly-2026-08-21 llvm-tools-preview
export RUSTUP_TOOLCHAIN=nightly-2026-08-21
export RUSTFLAGS='-C instrument-coverage -Z coverage-options=branch -C opt-level=0'
export LLVM_PROFILE_FILE="$PWD/build/controller-coverage/rust-%p-%m.profraw"
export CARGO_TARGET_DIR="$PWD/controllers/rust/target/controller-coverage"
cargo test --offline --locked --manifest-path controllers/rust/Cargo.toml
cargo build --offline --locked --bins --manifest-path controllers/rust/Cargo.toml
```

## Execute the existing behavioral corpus

This calls the same parameterized tests against the instrumented executables. The RTL
runner still invokes Icarus; the read, write, pipe and device tests still use real OS
interfaces. It does not replace a controller, plant or simulator with a mock.

```python
import importlib
import inspect
import itertools
import os
from pathlib import Path
import sys

root = Path.cwd()
sys.path.insert(0, str(root / "tests"))
import conftest

work = root / "build/controller-coverage"
programs = (
    work / "controller_cli",
    Path(os.environ["CARGO_TARGET_DIR"]) / "debug/witness-controller",
)
fixtures = {
    "native_controllers": programs,
    "tmp_path": work,
    "run_rtl": conftest.run_rtl.__wrapped__(work),
}
for module_name in ("test_controller_inputs", "test_controller_parity"):
    module = importlib.import_module(module_name)
    for name, function in inspect.getmembers(module, inspect.isfunction):
        if not name.startswith("test_"):
            continue
        marks = [m for m in getattr(function, "pytestmark", []) if m.name == "parametrize"]
        for values in itertools.product(*(m.args[1] for m in marks)):
            parameters = dict(zip((m.args[0] for m in marks), values, strict=True))
            parameters.update(
                {
                    key: fixtures[key]
                    for key in inspect.signature(function).parameters
                    if key in fixtures
                }
            )
            function(**parameters)
```

Save or execute the Python block with `.venv/bin/python` from the repository root.
The corpus includes full-range default/maximal coefficients, deterministic random states,
negative fractions, reset, integrator rail recovery, malformed input, LF/CRLF, streaming
before EOF, `/dev/full`, invalid encoding and an actual nonblocking-pipe read failure.

## Export and inspect every outcome

Run `gcov -b -c -j build/controller-coverage/kernel.gcno` and
`gcov -b -c -j build/controller-coverage/controller_cli-controller_cli.gcno`.
For each production C file, every executable line and every branch must have a positive
execution count in the resulting JSON report. A percentage rounded to 100 is insufficient.

Resolve the pinned toolchain's `llvm-profdata` and `llvm-cov` below
`rustc --print sysroot`, in `lib/rustlib/x86_64-unknown-linux-gnu/bin/`.
Merge all `build/controller-coverage/*.profraw` with `llvm-profdata merge -sparse`.
Use `llvm-cov export --instr-profile=<merged.profdata>` with the CLI ELF and `-object`
for every actual `controller_api-*` ELF below the coverage target directory; exclude
dependency metadata files. Inspect the `lib.rs` and `main.rs` file summaries: line,
region, function and branch covered counts must equal their totals. Preserve source hashes,
compiler versions, flags and report hashes with the result. Reset the coverage environment
variables before ordinary production builds or benchmarks.

## Freestanding AMP C optimized trace coverage

The production RV64 firmware is built at `-O2` without instrumentation. A separate debug-map
link recompiles only `runtime/bare_metal/amp_controller.c` with the exact production compiler
and flags plus `-g`, then links the other original objects unchanged. Coverage is admissible only
when the production and debug-map `.text` sections have equal sizes and SHA-256 digests.

Real Spike `-l` logs from the production lifecycle and the dedicated refusal tests are mapped to
that byte-identical optimized image. `tests/test_amp_startup_admission_fault.py` supplies the
remaining real MMIO, mailbox, overload, submission and post-entry hart observations on both
production plants. Exact-function or exact-branch traces from wrapper images are included only
after their linked instruction bytes and addresses match production. The retained profile covers
all 112 executable source lines and all 100 conditional machine-code edges. It executes 520 of
522 controller-attributed instructions; the remaining second `wfi` and loop-back occur after the
real logger has already terminated on the first published refusal.

These optimized instruction and edge counts are functional ISA evidence. They are not GCC
source-branch counters and do not qualify physical U54 timing, cache policy, PMP isolation,
HSS/Linux ownership or board acceptance.

## Freestanding Rust C ABI coverage

`tests/test_amp_rust_branch_coverage.py` builds the original safe core and C ABI adapter
with Rust 1.100.0 source coverage, then runs the real C API and PID/LQR stream clients.
It also runs the safe core's public Rust API tests and links a test-owned no-std panic
producer to the adapter's unchanged panic handler. The host-only panic sink flushes the
actual profile before exiting. The test merges those profiles with the matching toolchain's
`llvm-profdata` and requires positive, fully covered line, region, function and branch
counts for both original Rust source files. `RUSTC_BOOTSTRAP=1` is scoped to the profile
builds solely to enable Rust 1.100.0's unstable branch instrumentation option; production
builds and their warning gates retain their normal compiler settings. This is host source
coverage. The separately compiled RV64 fault in `tests/test_amp_rust_panic.py` exercises
the public target refusal path, but does not export target coverage counters or qualify
board timing.

## Native run controller instrumentation

Kernel coverage above does not cover the Linux run lifecycle, artifact hashing, scheduling
or transport. Measure those C++ paths through the actual native/RTL entry points in a new
build allocation:

```bash
WITNESS_NATIVE_BUILD_ROOT="$PWD/build/native-run-coverage" \
RUN_SIMULATION_CFLAGS='-std=c++17 -Wall -Wextra -Werror --coverage -O2' \
RUN_SIMULATION_LDFLAGS='--coverage' \
.venv/bin/python -m pytest tests/test_native_run.py tests/test_native_run_output.py \
  tests/test_native_run_metadata.py tests/test_native_configuration.py \
  tests/test_native_configuration_mutation.py tests/test_native_hash_mutation.py \
  tests/test_native_file_digest.py tests/test_native_scheduling.py tests/test_power_journal.py \
  tests/test_native_final_drain.py
```

`WITNESS_NATIVE_BUILD_ROOT` selects separate mechanical and thermal build directories.
The Makefile creates nested output directories before invoking Verilator. Compiler and linker
instrumentation flags are explicit; their defaults retain ordinary builds. Record optimization flags with coverage; optimized reports may omit eliminated paths. Choose a new
allocation for each measurement to avoid merging old execution counts. After all native
processes exit, use `gcov -b -c -j` on `run_simulation.gcno`, `run_configuration.gcno` and
`file_digest.gcno` in each plant directory. Included runtime headers appear under their actual
source paths in the resulting JSON; filter by those paths, not generated Verilator or system
library totals. Inspect uncovered lines and branch counts before making any coverage claim.
CLI file-size-limit tests relocate their child counters with
[`GCOV_PREFIX`](https://gcc.gnu.org/onlinedocs/gcc-15.2.0/gcc/Cross-profiling.html).
The limit also affects profiling files, so those child counter files may be truncated and must
not be merged into the baseline. Their exit status and retained data prove behavior; they do
not supply valid compiler coverage counts. Never use a corrupted gcov export as coverage evidence.

C++ exception paths and positive UIO/PAC1934 acquisition need separate real evidence. Native
simulation execution does not qualify hardware, and generated model C++ coverage does not
prove SystemVerilog branch or CDC coverage. Retain each scope and compiler's evidence separately.

The native lifecycle API corpus builds both production plants with strict warnings and
`--coverage -O2` in a separate allocation:

```bash
WITNESS_LIFECYCLE_BUILD_ROOT="$PWD/build/native-lifecycle-coverage" \
.venv/bin/python -m pytest tests/test_native_lifecycle_api.py tests/test_native_configuration_api.py
```

Its C++ entry point calls the public `Simulation` and run lifecycle APIs against the actual
AXI decoder, clocks, CDC and FIFO. It verifies register refusals, active-run reset refusal,
unread-record reset refusal, drain followed by successful bank reset, and start/check/finish
callback ordering during a real run. Completed-output cases use actual saved event/sample data
to verify repeated completion and writes after close are refused. Additional sample cases verify repeated/out-of-range
observations and invalid public API coefficient inputs for both controller selections, using
actual RTL samples. These callbacks observe the simulation lifecycle; they
do not provide physical PAC1934 evidence. Export `run_lifecycle_test.gcno` with gcov after all
cases exit and retain source/report hashes. This corpus supplements the production run CLI
coverage; keep its scope and counters separate rather than reporting a combined percentage.
The period-mismatch case supplies a valid configuration with a period different from the
compiled RTL register and requires refusal before START. The unstarted-sample case calls
the public sample operation before START and requires the actual AXI decoder to refuse
the sample read before the native controller or command commit can run. Both cases complete a
healthy run on the same device; the refused unstarted sample retains an empty event file
and a header-only trace separately from the recovery capture.
The read case also refuses the upper timebase word before the lower-word latch, then reads
the latched pair through the real AXI path.

The C++ lifecycle corpus additionally applies reversible soft `RLIMIT_FSIZE` caps with
`SIGXFSZ` ignored in its own process. Real header, event, sample and final-flush failures occur
while the cap is active; output cleanup finishes before the original limit and signal disposition
are restored. GCC writes profiling data only after that restoration. Those API counters can
therefore provide compiler evidence without truncating `.gcda` files. The CLI tests retain their
original hard limits and isolated profiling directories. Do not merge their damaged counters
with the API reports or substitute the API corpus for production CLI behavior tests.

For direct RTL source-flow coverage, set `WITNESS_RTL_COVERAGE=1` for the same lifecycle and
configuration API corpus, choose a fresh `WITNESS_LIFECYCLE_BUILD_ROOT`, and set pytest's
`--basetemp` to a separate retained directory. The fixture builds the actual production RTL
with Verilator `--coverage-line`; each successful lifecycle executable writes a nonempty
`events.bin.coverage.dat` next to its real test outputs. Merge those files with
`verilator_coverage --write merged.dat <files...>` and retain the raw files, source hashes,
merged report and compiler version. Verilator's `v_branch` counters describe instrumented RTL
source-flow branches; they are separate from C++ gcov and do not prove CDC timing, synthesis
timing or physical board acceptance. Keep zero-count branches open for real stimulus or a
documented unreachable-invariant review.

The existing production AXI process corpus adds register, controller feedback and full-aperture
transport paths. Set `WITNESS_RTL_COVERAGE=1`, choose a fresh
`WITNESS_AXI_COVERAGE_BUILD_ROOT`, and run `tests/test_axi_simulator.py` with
`tests/test_axi_transport_progress.py`. The Make target builds the same RTL with
`--coverage-line`; each process that finishes through the public `Q` request writes a
`axi_simulator.<pid>.coverage.dat` beside its executable. Invalid-request cases exit through
their real error path and do not export a profile. Merge these raw files with the separately
retained lifecycle profiles only when source hashes and Verilator versions match. The AXI
build's FIFO parameter differs from the lifecycle build, so report the union of instrumented
points and its actual denominator rather than adding percentages.
The AXI process corpus also commits a command for cycle one while the actual RTL remains on
cycle zero. It requires one retained `ACT_LATE` FIFO record and unchanged miss and safe-state
registers, exercising accepted-but-untimely command handling through the real register path.
The same process corpus configures ramp, sine and clipped step references through AXI writes,
then reads successive reference snapshots and acknowledges each retained sample interrupt.
The module-specific arithmetic simulation checks both saturated reference values and their
clip flags. The register contract refuses reference mode 3, so that generator default case
is not a reachable AXI runtime path.

`ExclusiveOutput` supplies the same exclusive FILE ownership to controller outputs and the
power journal. The actual lifecycle corpus copies a captured FIFO record through that public
stream API, closes it, refuses a second close and borrow, and refuses recreating the same path.
Existing real output failures exercise constructor unwinding and partial-file cleanup. These
cases verify shared file ownership through simulation and real host files. They do not exercise
physical power acquisition or the logger's hardware-dependent worker start/stop sequence.

Public configuration API cases first complete an actual run, snapshot its finished/configuration
registers and nonzero retained IRQ generation, then submit an invalid C++ configuration. The
refusal must leave every observed register unchanged; a second actual healthy run must succeed.
This supplements file-parser refusal tests and exercises the shared semantic validator before
reset rather than relying on a transport refusal after configuration has already changed.

Final-backlog cases model a five-millisecond CPU delay during an actual eight-cycle run.
The real 32-record FIFO retains 20 events without overflow; two regular drain batches cannot
empty it, so final producer-quiescence drain must retrieve the remainder. Native PID/LQR cases
replay the observed command through both public kernels, and frozen captures from both plants
reach the importer/report path with eight observed deadlines and one partial tracking sample.
This exercises final-drain execution; it does not fabricate a timeout or qualify host-wall latency.

The Linux scheduling API corpus builds a separate native executable with strict warnings,
uses actual unprivileged `SCHED_BATCH` in its own children, and checks unchanged real policy
after invalid public requests. It also exercises preserving inherited policy and applying
explicit normal policy and affinity. The parent test thread's policy never changes. To reach
the kernel's failures, a scenario installs a seccomp filter in its own child: the kernel then
answers one system call with an errno (`*_denied`), or skips it and reports success
(`*_ignored`), which reaches the read refusals and the readback checks of
[`run_policy.h`](../runtime/linux/run_policy.h). No libc function is replaced.

`tests/test_native_scheduling.py` asks the kernel, through an independent
child, whether SCHED_FIFO at priority 1 is permitted, and then requires the native run to apply
it or to refuse with EPERM and no outputs. The hosted test shards raise their real-time limit to
1 with `sudo prlimit`, so the positive FIFO path runs there; hosts without that limit or
privilege require the refusal. Higher priorities and real-time latency are not qualified.
The same test module launches the production simulation CLI through `chrt --batch 0` for
both plants. Complete healthy runs must retain the inherited batch scheduler and affinity
in native metadata, with actual event counts and sample traces matching the receipt.

`tests/test_axi_transport_progress.py` exercises the production AXI process across idle,
held-bank-reset and completed-run states for both plants. Each case reads all 256 byte offsets
and submits every partial strobe mask at every offset, requiring actual SLVERR responses for
partial writes and unchanged configuration/staging readback. Request and response files retain
the actual model time for each access. The fixed 7 ns bus and 5 ns capture half-periods must
complete each serial access within 280 modeled nanoseconds; this is a simulation regression
bound, not a host or board latency guarantee.

Bank reset does not reset the AXI mailbox: `axi_control_witness` supplies the external reset to
the transport and the separate bank reset to the register banks. Remote decode still returns
SLVERR while the bank is held, so a held bank cannot by itself exercise the simulation's
100,000 ns AXI timeout. The test verifies response progress through those real states; it does
not exercise stopped clocks, an external-reset race or either timeout exception. Those guards
remain in the compiler report without a coverage exclusion. Physical UIO reads/writes cannot
return destination AXI response signals and require separate board acceptance.

`tests/test_native_metadata_api.py` uses the lifecycle executable after an actual healthy run.
It submits invalid public metadata configurations, requires refusal before file creation, then
writes the original run's receipt to the same path. Schema validation and independently computed
hashes bind that receipt to the actual completed configuration, event and tracking files. Both
plants exercise the shared validator before the metadata writer's fault-name array lookup.

`tests/test_power_configuration_api.py` builds the actual PAC1934 constructor and submits typed
configurations that bypass file parsing. Malformed identity, polling, CPU, sample-rate and rail
fields must refuse before IIO selection with the same semantic contract as the parser. These
compiler profiles cover configuration validation and early constructor refusal, not physical
sensor reads or journal worker execution. The journal's validation-before-output ordering is
source-inspected and compiled; invoking that constructor requires actual IIO and UIO resources.

## RTL source-flow closure

The completed Verilator 5.020 measurement retains every source and elaboration
identity, omitting only instance hierarchy when taking the union. It covers all
25 production RTL files: 22 contain measured procedural source-flow points;
`fabric_control_witness.sv` and `icicle_witness.sv` contain continuous
assignments and module wiring, and `event_codes_pkg.sv` contains constants.
Those three files have no procedural counter in this scope.

The completed union has **826 of 832 points executed**, with **6 remaining
raw zero counters accepted as source invariants**. No point is excluded and no
unexplained zero remains. The six proofs do not count as runtime hits. The
union combines actual public-port testbench, native lifecycle and AXI process
profiles; it does not assert independent completeness for each plant.

The union was measured with 826 of 834 points before `control_event_capture.sv`
replaced its eight-step record scan with a comparison tree. The file appears in
two elaborations, the default and `GROUP_ADDRESS_BITS=4`. Each lost the scan's
two branch points and exchanged the scan's block point for the tree function's.
Every output of the module is unchanged in every cycle, so every remaining point
executes under the same stimulus. A re-measurement of the lifecycle,
configuration and AXI corpora with the previous and the current file gives
identical counts for every shared statement.

The union was then 822 of 830 with eight invariants, before the plant and the
reference registered their products one edge ahead (`split_multiplier.sv`). Every
output of `control_plant_witness` is unchanged in every cycle, so the same resets,
samples and clamps occur under the same stimulus. `sampled_plant.sv` keeps its five
elaborations and replaces each one's four points (block, sample branch, reset
if/else) by five (block, reset if/else, sample if/else). The sample's else arm runs in
every non-reset cycle without a sample, which each elaboration's previous counts show
(its reset-else count exceeds its sample count). `fixed_point_math.sv` lost its
coefficient parameters, so its five elaborations of four points become one, which
every plant step shares; the clamping instances keep the clamp branches executed, and
the two invariants of the thermal velocity binding no longer apply. The new
`split_multiplier.sv` has one elaboration of three points. The union therefore
becomes 816 of 822 with six invariants. A re-measurement of the lifecycle,
configuration and AXI corpora with the previous and the current tree (76 and 56 tests
passed for each) gives identical point sequences and counts for
`reference_generator.sv` and `control_cycle.sv`; for the one `sampled_plant.sv`
elaboration that these corpora reach, the same block and sample counts and all five
new points executed; and all three `split_multiplier.sv` points executed. The
`fixed_point_math.sv` evaluation counts differ, as expected for a combinational block
with other inputs; its clamp branches are not reached by these corpora in either tree.
The register copy of the capture queue head in `control_event_capture.sv` adds no
source-flow point: the same corpora on the final tree give the elaboration they reach
(`GROUP_ADDRESS_BITS=4`) identical point sequences and counts, the other elaboration has
the same statements, and the union stays 816 of 822.

`clock_request_bridge.sv` then gained a capture-clock register for the held request,
loaded while `capture_valid` is low. The union holds two elaborations of it, the
production binding (request 45 bits, response 34 bits) and the testbench default (65 and
256 bits, from `clock_request_bridge_tb`); the retained source inventory lists 28 points,
14 each. Each keeps its twelve branch points and two block points and gains the if/else
pair of that load. Both pairs executed: the production one in the lifecycle,
configuration and AXI corpora, the default one in a `clock_request_bridge_tb` run. Every
port behaves as before while `capture_valid` is high, and those corpora on the previous
and the current tree give every shared point of every other file the same executed
status. The union therefore becomes 820 of 826 with the same six invariants. (An earlier
revision of this paragraph counted only the production elaboration and gave 818 of 824.)

`control_plant_witness.sv` and `axi_control_witness.sv` then registered capture
quiescence and the reset permission before their bus synchronisers. The permission joins
the existing capture-domain block of `axi_control_witness.sv`, whose points stay three per
elaboration. `control_plant_witness.sv` gains its first procedural block: a block point
and a reset if/else. Elaborating every testbench case of the union records with Verilator
names two elaborations of it, `control_plant_witness__pi1` (from `axi_lite_clock_bridge_tb`
and `clock_request_bridge_tb`) and `control_plant_witness__pi2` (from the other testbenches
and the native corpora). All six points executed: `__pi2` in the lifecycle, configuration
and AXI corpora, `__pi1` in a `clock_request_bridge_tb` run. The same corpora on the
previous and the current tree give every shared point of every other file the same executed
status. The union therefore becomes 826 of 832 with the same six invariants.

`tests/test_retained_interrupt.py` reads the real `0xa8` IRQ status register
across three bus/capture clock ratios. It checks an older snapshot acknowledgement
while a newer generation is pending, coalesced safe/finish events, invalid
acknowledgements and common reset. This exercises `retained_interrupt.sv:50`;
the unknown-address default is at line 51 and was already executed.

Run the full original 32-bit counter programme separately from the ordinary suite:

```bash
make rtl-counter-saturation RTL_SATURATION_DIRECTORY=build/rtl-counter-full
make rtl-invariants RTL_INVARIANT_DIRECTORY=build/rtl-invariants-full
```

The first command drives public clocks and inputs for `2^32 + 8` ticks after
warmup. Six `control_cycle` period bindings (64, 256, 512, 16384, 32768 and
100000), three `deadline_monitor` miss limits (1, 2 and 3), and an actual full
FIFO reach `UINT32_MAX`, remain saturated and clear on common reset. The sources
and their 32-bit widths stay unchanged. The ordinary pytest regression runs
only one million ticks and checks progression/reset; it does not claim saturation.
A full run takes 50 minutes on the recorded shared host. Verilator retains
the original constant unsigned-threshold warning for miss limit 1, so this
programme does not certify strict RTL lint. Its C++ build uses strict warnings.

Coverage snapshots are cumulative observations. Verilator's unsigned 32-bit
coverage counters can wrap during this long run; preserve the intermediate
profiles and use positive observations to determine execution. Do not add these
snapshots as independent cases or treat their sum as an execution frequency.
Keep raw elaboration pages distinct: `event_witness__A3` and
`event_witness__A3_O20` are separate measured identities. Both original 32-bit
bindings were executed, including an exact explicit-parameter FIFO run.

| Raw zero source points | Accepted invariant and reproduction |
| --- | --- |
| `run_configuration_registers.sv:111` | A successful public write can only select a listed sequential address; the default cannot follow an accepted write. The configuration proof runs six periods and both plant selectors. |
| `control_io_registers.sv:83,127` | The nested read case has the same six addresses as its outer case; successful writes select the three sequential addresses. The public decoder assertions support this exact source inspection. |
| `axi_lite_clock_bridge.sv:147,148` (three points) | The original `ENABLE_LOCAL=0` binding makes `local_valid=0`; the local response branches cannot execute. Enabled-local elaborations remain separate runtime points. |

`make rtl-invariants` runs 16 positive checks with Yosys: four default wrappers
and 12 configuration variants. The `fixed_point_math` wrapper now checks the plant
step binding (split multipliers feeding the sum) with zero coefficients; it no longer
backs a coverage invariant. The recorded proof review also checked four
intentionally false assertions and retained their concrete counterexamples.
The accepted argument uses two-state, one-step SAT and exact source/parameter
binding with unconstrained initial states. It makes no reset-reachability,
four-state, signal-toggle, MC/DC, CDC-timing, synthesis or physical-board claim.
Native C++ compiler edges and hardware acquisition remain separate scopes.

## Native lifecycle guard proof

The lifecycle corpus retains the original production RTL, the production GCC
optimisation level and nanosecond timers. `commit_boundary` delays a real one-cycle run through
`Simulation::advance`; the live-status read still sees an active run, while the
subsequent full-word command commit receives the actual finished-run SLVERR.
The trace retains one observed sample with `submitted=0`, and all three real
FIFO records are drained. This exercises the second status check in `control_sample`;
it does not replace the transport or inject a response.

`final_drain_no_hooks` exercises the real backlog without callbacks. `run_timeout`
and `final_drain_timeout` use acquisition callbacks to advance both production
clocks past the original timer limits. They require the exact timeout exception,
no completion callback, and the retained actual event/trace bytes. These tests
advance more than one billion simulated nanoseconds and therefore take longer
than ordinary lifecycle cases. They establish timer supervision in the simulation
time domain, rather than host-wall or board timing.

```bash
WITNESS_LIFECYCLE_BUILD_ROOT="$PWD/build/native-lifecycle-proof" \
.venv/bin/python -m pytest tests/test_native_lifecycle_api.py \
  tests/test_native_configuration_api.py tests/test_native_metadata_api.py
make native-runtime-invariants
```

The Yosys wrappers elaborate the unchanged production `control_io_registers`,
`run_configuration_registers`, `control_cycle`, `deadline_monitor` and
`clock_reset_release` modules.
Four-step proofs check full-word cycle/value staging followed by commit, and
preservation of enabled, finished and safe state across non-reset transitions,
constant ABI/Q-format readback, and reset release after two running local edges.
Each intentionally false variant must produce a counterexample; parser errors
and solver timeouts cannot satisfy the negative control. JSON netlists and
counterexample waveforms are retained in `build/native-invariants`.

For the serial `Simulation` lifecycle, sample-read success establishes enabled
state; both staged writes succeed or the public API throws before commit.
There is no reset or competing bus writer inside `control_sample`. Under these
premises, the production decoder can refuse the commit only when finished or
safe is asserted, and those flags persist until reset. The subsequent status read
therefore handles that refusal. The defensive exception for refusal without
either flag remains in the source and raw coverage report. This compositional
proof applies to the declared serial simulation path; it does not assert that an
unqualified physical device, external reset or competing writer obeys the premises.

GCC JSON reports mark exception arcs with `throw=true`. Keep those arcs and their
counts, and inspect the accompanying `-fdump-tree-cfg-lineno` files rather than
renaming them as source decisions. An unexecuted allocation/unwind edge is not an
executed error path. Constant ABI/Q-format mismatches, deterministic reset release,
and the defensive commit guard require their own source evidence; the successful
period-mismatch test covers the independent variable period check. Report raw
executable lines, compiler arcs, proved source invariants and actual resource
limitations separately. Do not publish an unconditional 100% C++ compiler-edge claim.
