<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — fixed-point controller contract
-->

# Fixed-point controllers

The controller surface has three independently compiled implementations:
`controllers/c/witness_controller.c`, `controllers/rust/src/lib.rs` and
`rtl/fixed_point_controller.sv`. The fabric entry point is
`rtl/fabric_control_witness.sv`; the existing `control_plant_witness.sv` accepts
externally supplied commands. Both connect to the same deadline monitor, safe actuator,
plant, event capture and dual-clock drain. This surface is exercised in simulation.
There is no physical board available; board timing, processor interrupts, bus adapters,
energy and physical safe-state qualification remain unavailable.

## Common arithmetic and reset

All values and gains are signed raw Q8.24 integers. Products and sums retain wide signed
precision before division by 2^24, which floors negative fractions. C uses GNU `__int128`
without relying on signed right shifts; Rust uses `i128::div_euclid`; RTL uses signed
96-bit arithmetic shifts. These intermediates cover the complete signed input range,
including 33-bit errors and measurement differences. C requires a compiler/target with
128-bit integer support; the planned RV64 toolchain still needs its separate build gate.
No floating-point arithmetic executes in any controller kernel.

Reset clears the PID integral, derivative and previous-measurement initialization.
The first accepted sample has zero derivative. Configuration, mode and sample period
remain stable until reset. Bounds must be ordered and contain zero. PID gains `kp`,
`ki_period`, `derivative_gain` are nonnegative; `derivative_decay` is in [0, 2^24].
LQR state and reference gains may be signed. Invalid coefficients produce no command and
leave state unchanged. C callers supply non-null pointers and state obtained from reset
or a preceding successful step; Rust memory is initialized by `PidState::default()`.

## PID with conditional integration

Let `S=2^24`, `e=r-y`, `dy=y-y_previous`. Each sample computes:

```text
D = first_sample ? 0 : clamp_i32(floor((decay*D_previous - gain*dy)/S))
I_proposed = clamp_integral(floor((I_previous*S + ki_period*e)/S))
u_previous = floor((kp*e + (I_previous+D)*S)/S)
hold = (u_previous >= output_max and e > 0)
       or (u_previous <= output_min and e < 0)
I = hold ? I_previous : I_proposed
u_raw = floor((kp*e + (I+D)*S)/S)
u = clamp_output(u_raw)
```

The saturation decision uses the prior integral. Testing only the proposed integral would
prevent a pure integral controller from ever responding when one increment crosses a rail.
Conditional integration permits the crossing step and prevents continued windup; an error
that helps recover permits integration. The integral has explicit independent bounds.
`integral_held` reports the integration decision; `clipped` reports final actuator clipping,
not derivative or integral saturation. Integral and derivative outputs expose those states.

This is conditional integration, one of the anti-windup methods discussed by
[Åström and Rundqwist, Integrator Windup and How to Avoid It](https://doi.org/10.23919/ACC.1989.4790464).
It uses derivative on measurement with a first-order filter, so changing the reference alone
introduces no derivative kick. For physical coefficients, `ki_period = Ki*T`,
`decay = Tf/(Tf+T)`, `gain = Kd/(Tf+T)`, each quantized to Q8.24. The default normalized
emulator gains are `Kp=2`, `Ki=1`, `Tf=T=0.001`, `Kd=0.0005`. Raw defaults are
33554432, 16777, 8388608 and 4194304. Output bounds are ±4 (raw ±67108864);
integral bounds are ±2 (raw ±33554432). These are reproducible emulator settings,
not tuning for a physical machine. Arbitrary gains require their own closed-loop assessment.

## Discrete LQR

The kernel evaluates `u=clamp_output(floor((nr*r-kx*y-kv*v)/S))`. The mechanical
model supplies both emulator states; thermal uses `kv=0`. No observer is implied.
The standard infinite-horizon objective and state-feedback sign are documented by
[the Python Control authors](https://python-control.readthedocs.io/en/latest/generated/control.dlqr.html).
The default design uses the quantized plant matrices in
[`PLANT_WITNESS.md`](PLANT_WITNESS.md), mechanical `Q=diag(10,1)`, thermal `Q=1`,
and `R=1`, with no cross cost. Iterate the discrete Riccati equation from `P=Q`:

```text
P_next = Q + A' P A - A' P B (R+B' P B)^-1 B' P A
K = (R+B' P B)^-1 B' P A
F = A-BK
nr = 1 / ([1,0] (I-F)^-1 B)           # mechanical
nr = (1-A+B*K)/B                     # thermal
```

Round coefficients to nearest raw integer, ties to even. Mechanical defaults are
`kx=38822697`, `kv=26419076`, `nr=55599913`; thermal defaults are
`kx=6944437`, `kv=0`, `nr=23721653`. Stability must be checked again after
quantization using the strict Jury inequalities for `F`; scalar thermal requires `abs(F)<1`.
Saturation makes the closed loop nonlinear, so linear poles alone do not qualify every
reference/state range. Design residual, stability and longer trajectories are separate gates
from arithmetic parity.

## Fabric integration

The controller accepts one valid sample per clock edge and registers its command plus
unchanged cycle tag. `fabric_control_witness` consumes a new plant sample on the following
edge, capturing `SAMPLE_READ`; the actuator register accepts the resulting command one edge
later, capturing `ACT_WRITE`. The simulation invariant is scheduling one tick, compute one
tick and loop two ticks. This is not a 100 MHz place-and-route verdict.

The fabric wrapper blocks controller steps during actuator freeze or a latched safe state.
The independent monitor retains final priority. Drop/delay IRQ and overload-request actions
operate on the processor service path; a fabric controller does not depend on that IRQ.
Invalid configuration yields no write and therefore allows the independent deadline monitor
to trip. Actual processor service and register adapters are later roadmap work.

## Native interfaces

C declarations and contracts are in `controllers/c/witness_controller.h`; the kernel has
no allocation, operating-system calls or global mutable state. Rust exposes `Coefficients`,
`PidState::step`, `PidState::reset` and `lqr_step`, with no third-party dependencies or unsafe
code. The Rust library is `no_std`: its arithmetic requires neither allocation nor an operating
system. Its host streaming and benchmark binaries still use the standard library for I/O and
timing. Native API docs are generated by `cargo doc --no-deps`; C uses the header contract.
The [AMP Rust adapter](../runtime/bare_metal/rust_kernel/README.md) exposes the original
C ABI through this safe arithmetic library. Public firmware preparation selects it with
`--rust-compiler rustc`, sharing the existing C/assembly startup, interrupt service and telemetry.
Its image and capture receipts retain the original Rust source, compiler, target libraries and
actual archive bytes.
Cross-compiling the library for a target without an OS checks that boundary; it does not establish
a Rust bare-metal entry point, interrupt service, linker layout or board acceptance. For an
installed `wasm32-unknown-unknown` or `riscv64imac-unknown-none-elf` target, the library-only
checks are:

```sh
cargo build --offline --locked --lib --target wasm32-unknown-unknown \
  --manifest-path controllers/rust/Cargo.toml
cargo build --offline --locked --lib --target riscv64imac-unknown-none-elf \
  --manifest-path controllers/rust/Cargo.toml
```

`controller_cli pid|lqr` and `witness-controller pid|lqr` read the same streaming protocol:

1. Eleven comma-separated raw integers: `kp,ki_period,decay,gain,kx,kv,nr,output_min,
   output_max,integral_min,integral_max`.
2. Sample rows `cycle,reference,position,velocity`, with cycle an unsigned 32-bit integer
   and state values signed 32-bit integers. A `reset` row clears PID memory.
3. One output per sample: `cycle,command,integral,derivative,clipped,integral_held`.

Each command is flushed for interactive co-simulation. The host CLI is a functional adapter,
not a Linux UIO or bare-metal implementation. Parsing failure exits nonzero; already emitted
commands remain emitted and the caller must treat the stream as incomplete. Both programs
accept LF and CRLF, reject surplus fields and out-of-range values, and preserve cycle tags.

## Reproduce

```bash
mkdir -p build
gcc -std=gnu11 -O3 -flto -Wall -Wextra -Werror -Wconversion -Wshadow \
  -Wstrict-prototypes -Wmissing-prototypes controllers/c/witness_controller.c \
  controllers/c/controller_cli.c -o build/controller_cli
cargo build --release --offline --locked --manifest-path controllers/rust/Cargo.toml
cargo fmt --check --manifest-path controllers/rust/Cargo.toml
cargo clippy --offline --all-targets --manifest-path controllers/rust/Cargo.toml -- -D warnings
cargo test --offline --locked --manifest-path controllers/rust/Cargo.toml
.venv/bin/pytest -q tests/test_controller_*.py tests/test_fabric_controller*.py
verilator --lint-only --Wall --top-module fixed_point_controller rtl/fixed_point_controller.sv
verilator --lint-only --Wall --top-module fabric_control_witness rtl/*.sv
```

`benchmarks/controller_benchmark.c` and the Rust `controller_benchmark` binary execute the
same million samples per controller and report mode, iteration count, total nanoseconds and
command checksum. Run them with identical optimization and CPU context. Non-isolated timing
is local regression evidence only; record affinity, host load, governor, toolchain, OS and
CPU model. Never infer processor-to-fabric speedup from host wall time and simulated ticks.


The current local comparison is in
[`controller_comparison.local.json`](../benchmarks/controller_comparison.local.json).
Build and record a new artifact with:

```bash
make controller-benchmarks CONTROLLER_BENCHMARK_CPU=0 \
  CONTROLLER_BENCHMARK_OUTPUT=build/new-controller-comparison.local.json
```

Choose a CPU in the process's inherited allowed set. The recorder runs three warmup batches
and twenty measured batches per native backend, interleaving C and Rust. Each batch executes
both controllers on one million deterministic samples. Warmup batches are retained but excluded
from statistics. P50/P95/P99, mean, min, max and throughput summarize batch-average step times;
these percentiles do not describe individual-step latency tails. Source and executable hashes
are checked before and after measurement; all command checksums must agree. Existing output
paths are refused. `tools/benchmark_controllers.py` also accepts `--warmup`, `--repeats` and
`--source-root` for measuring an actual separately built source snapshot.

CPU pinning applies only to the native child processes and does not reserve the core. The
artifact records actual toolchains, host load, frequency context and affinity. It explicitly
declares nonisolated regression evidence, no production performance claim and no host-to-RTL
timing comparison. Its `ci_evidence: not_attested` field requires separate hosted-run verification.
The prior five-repeat record remains in
[`controller_regression.json`](../benchmarks/controller_regression.json) as historical evidence;
it has no discarded warmup or percentile summary and is not the current comparison. Native
coverage scope, separate branch-analysis compiler and reproduction are in
[`CONTROLLER_COVERAGE.md`](CONTROLLER_COVERAGE.md). The four default closed-loop
trajectories run for 64,000 samples at a model period of 1 ms. Every C/Rust command
and PID state matches RTL; each final 1,000-sample error is below 4,000 raw units
(about 0.000239). This checks those emulator settings, not arbitrary gains or a
physical plant. Freeze and invalid configuration trip the independent actuator
monitor; IRQ drop/delay and overload requests leave the fabric service timely.

The `Controller comparison` workflow defines weekly and manual measurement on `ubuntu-24.04`.
It builds both kernels, runs the same recorder, and retains the CI JSON plus a runner receipt
for 30 days. The receipt binds the JSON SHA-256 to the hosted commit, repository, run ID and
attempt. Verify the actual hosted run and artifact digest before using it as CI evidence;
no hosted result is included with the current local artifact. CPU pinning on that shared runner
also provides no core reservation. A published CI/local comparison requires both real artifacts.
