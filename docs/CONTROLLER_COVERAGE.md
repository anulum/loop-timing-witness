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

[`controller_coverage.json`](../benchmarks/controller_coverage.json) binds source hashes
to GCC and LLVM coverage reports. Both controller kernels and their streaming CLIs have
100% executable line and branch coverage in the recorded snapshot. The retained reports
include the earlier Rust 1.98.1 build; they are historical evidence and do not certify a new
compiler. These counts exclude benchmark harnesses and SystemVerilog. They establish
host execution coverage, not board qualification.

Production Rust builds use 1.99.0. Stable LLVM coverage additionally reports complete line,
region and function coverage for the library and CLI, but does not instrument branches.
The separate branch analysis uses `nightly-2026-08-21`, with `llvm-tools-preview`, without
changing the production compiler or disabling any branch. GCC 13.3.0 uses `--coverage`.
Build outputs and raw reports remain under ignored `build/` and the crate's `target/`.

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
with Rust 1.99.0 source coverage, then runs the real C API and PID/LQR stream clients.
It also runs the safe core's public Rust API tests and links a test-owned no-std panic
producer to the adapter's unchanged panic handler. The host-only panic sink flushes the
actual profile before exiting. The test merges those profiles with the matching toolchain's
`llvm-profdata` and requires positive, fully covered line, region, function and branch
counts for both original Rust source files. `RUSTC_BOOTSTRAP=1` is scoped to the profile
builds solely to enable Rust 1.99.0's unstable branch instrumentation option; production
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
[`GCOV_PREFIX`](https://gcc.gnu.org/onlinedocs/gcc-13.3.0/gcc/Cross-profiling.html).
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

The Linux scheduling API corpus builds a separate native executable with strict warnings and
gcov, uses actual unprivileged `SCHED_BATCH` in its own children, and checks unchanged real
policy after invalid public requests. It also exercises preserving inherited policy and applying
explicit normal policy/affinity. No syscall substitution or parent-thread scheduling change is used:

```bash
WITNESS_POLICY_BUILD_ROOT="$PWD/build/native-policy-coverage" \
.venv/bin/python -m pytest tests/test_native_policy_api.py
```

Export its actual `policy_api_test.gcno` with gcov and retain this scope separately from RTL
controller profiles. Positive privileged FIFO application still requires a permitted host policy.
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
