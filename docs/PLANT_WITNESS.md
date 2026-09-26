<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — plant monitor and injector RTL
-->

# Plant, monitor and fault injector

`rtl/control_plant_witness.sv` is the vendor-neutral fabric entry point. Both sampled plants,
reference generator, strict deadline monitor, fault injector and simultaneous-event capture
feed the real dual-clock record FIFO. Tests drain binary records into the public host analyzer.
This is simulation evidence; no physical board is available. C/Rust/RTL controllers and the
closed fabric feedback path are specified in [`CONTROLLERS.md`](CONTROLLERS.md). Native CLI
commands replay through simulated actuator transactions; bus adapters, board processor service, vendor timing constraints,
power readings and physical safe-state acceptance remain planned.

## Ports and configuration

All inputs except `drain_request` are synchronous to `capture_clock`; drain inputs and outputs
belong to `drain_clock`. `run_reset_n` asynchronously asserts the common run reset; each domain
releases it after two local edges. A reset flushes events, plant state, monitor and injection.
`capture_active` marks local reset release. `control_cycle.sv` owns the sample period,
actuator register, command classification and event strobes. Hold configuration stable for the run.

| Inputs | Contract |
|---|---|
| `enable`, `stop_after_cycle` | Start at cycle zero; hold enable high through the last cycle's deadline. Stop includes that deadline, with no extra sample. Reset before restarting. |
| `sample_read` | First sample read per cycle produces `SAMPLE_READ`. |
| `actuator_write`, `command_cycle`, `command_value` | Synchronous actuator command, signed Q8.24. Matching current-cycle writes strictly before its deadline satisfy it. Only the first such write produces `ACT_WRITE`; later timely writes may replace the actuator. |
| `fault_arm`, `fault_kind`, `fault_cycle`, `fault_periods` | Arm one injection before its target sample. Kinds 0/1/2/3 are drop/delay/freeze/overload request. Positive duration required, target cannot be past or beyond the final cycle. |
| `reference_mode`, `reference_amplitude`, `reference_offset`, `ramp_increment`, `phase_increment` | Step/ramp/sine selection 0/1/2; signed Q8.24 values, modulo-16 phase increment. Mode 3 uses zero amplitude plus offset. |
| `drain_request` | Request next record; inspect data only with `drain_valid`. |

| Outputs | Contract |
|---|---|
| `sample_valid`, `cycle_number`, `sample_value`, `velocity`, `reference_value` | New registered sample/target on the update edge. Thermal velocity is zero. |
| `actuator_value` | Latest accepted command; defined safe value wins on monitor trip and remains until reset. |
| `sample_interrupt`, `delayed_interrupt`, `delayed_cycle` | Edge strobes; delayed origin survives coincident normal IRQ delivery. |
| `safe_interrupt` | Latched trip indication, not a one-clock pulse. |
| `fault_ready`, `freeze_actuator`, `overload_request` | Injection availability and synchronous action levels. Readiness falls after trip or run completion; invalid schedule data is refused. |
| `total_misses`, `consecutive_misses`, `late_commands` | Saturating 32-bit capture-domain counters; not coherent processor snapshots. |
| `plant_clipped`, `reference_clipped` | Saturation at the last sample; retain/sample these with `sample_valid`. These are flags, not cumulative clipping counters. |
| `counter_ticks`, `overflow_count`, `buffer_full` | Capture timebase, saturating combined lost-event count and downstream FIFO full status. Group queue exhaustion can lose events even when FIFO full is low. |
| `drain_valid`, `drain_empty`, `drain_record` | Existing 16-byte stream in the drain domain. |

Parameters: `PERIOD_TICKS` defaults to 100,000 at the planned 100 MHz (1 kHz);
`MISS_LIMIT` defaults to three, must be positive; `SAFE_VALUE` defaults to zero.
`THERMAL` selects the plant. `ADDRESS_BITS` is the existing FIFO width (1–14), and
`GROUP_ADDRESS_BITS` is the simultaneous-event queue width (1–8, default six).
Plant coefficients are compile-time signed Q8.24 parameters. Changing period requires
recomputing them for that physical sample interval. Clock and period parameters do not qualify
a physical oscillator or board rate.

## Fixed-point plant

Signed Q8.24 means raw integer divided by 2^24, range [-128, 128−2^-24]. A product is signed
64-bit; three products accumulate in signed 66-bit precision. Arithmetic right shift by 24
rounds toward negative infinity. Saturation occurs once at the state/output boundary. Both
mechanical states update from their old values together; intermediate states are not rounded.

The mechanical model is `m*x'' + c*x' + k*x = u`, with state `[x, v]` and continuous matrix
`Ac = [[0, 1], [-k/m, -c/m]]`, input vector `Bc = [0, 1/m]`. Zero-order hold gives
`Ad = exp(Ac*T)` and `Bd = integral(exp(Ac*t)*Bc, t=0..T)`.
The [systemID author's mechanical example](https://damiengueho.github.io/SystemID/examples/spring_mass_damper_system/spring_mass_damper_system_lti_notebook.html)
describes this discretisation; our default uses its unit-mass normalization. For the default
`m=c=k=1`, `T=0.001`, set `alpha=0.5`, `beta=sqrt(0.75)`,
`C=exp(-alpha*T)*cos(beta*T)`, `S=exp(-alpha*T)*sin(beta*T)/beta`. Then:

```text
Ad = [[C + alpha*S, S], [-S, C - alpha*S]]
Bd = [1 - C - alpha*S, S]
x_next = A00*x + A01*v + B0*u
v_next = A10*x + A11*v + B1*u
```

The thermal model is `theta' = (-theta + gain*u)/tau` relative to ambient. With
`tau=gain=1`, `T=0.001`, its coefficients are `A=exp(-T)`, `B=1-exp(-T)`.
These are normalized emulator parameters, not fitted physical plant measurements.
Coefficients round to nearest raw integer (ties to even):

| Parameter | Raw Q8.24 default |
|---|---:|
| `A00` | 16777208 |
| `A01` | 16769 |
| `A10` | -16769 |
| `A11` | 16760439 |
| `B0` | 8 |
| `B1` | 16769 |
| `THERMAL_A` | 16760447 |
| `THERMAL_B` | 16769 |

The default quantized models are stable; arbitrary supplied coefficients are the run owner's
responsibility and must be documented and checked for representability and stability. For a
2×2 real discrete matrix, check the strict Jury inequalities `1−det>0`,
`1−trace+det>0`, `1+trace+det>0`; thermal requires `abs(A)<1`.
Saturation makes the emulator nonlinear and must be reported with sample clipping flags.

The plant uses the actuator present strictly before the sample edge. A command on that edge
updates the actuator for the following sample. Mismatched-cycle or exact-deadline commands
increment `late_commands`; the first such accepted command in an observed cycle produces
`ACT_LATE` (code 13). It cannot fulfil that cycle's deadline. Event cycles identify the observation
cycle, including the new cycle on a boundary edge; the command's original tag remains on the
command port. Frozen or safe-state writes are ignored. Multiple commands may update the same
register, so the latest accepted value is used; this is not a command queue.

Step produces offset plus amplitude. Ramp uses an initially zero, saturating Q8.24 accumulator,
incremented after each sample, then multiplied by amplitude and offset. Sine uses sixteen
uniform phase samples of `sin(2*pi*phase/16)`, independently rounded to Q8.24. It advances once
per sample; no interpolation or analog waveform fidelity is claimed. Reference multiply and
add use wide signed arithmetic and saturate only after scaling.

## Deadline, safe state and injected faults

A missing timely write at a deadline increments total and consecutive misses; a fulfilled
deadline clears the consecutive counter. Reaching `MISS_LIMIT` applies `SAFE_VALUE` on that
edge, latches `safe_interrupt` and captures `SAFE_STATE`. Safe application wins over command
writes, freeze and the simultaneous plant update. Only the common run reset clears the latch.
`FAULT_DETECTED` is captured at this trip when an injection is pending. Ordinary misses do not
invent an injected-fault detection. `SAFE_STATE` and `FAULT_DETECTED` share the trip timestamp.

One schedule can be armed per run. Arms while busy/used, zero-duration arms, past targets and
targets beyond the last sample are refused. Arming must precede the sample edge; the data is
latched, so subsequent input changes cannot replace the schedule. A trip suppresses subsequent ordinary sample IRQs and prevents further
injections; an already pending delayed IRQ can still release. Reset is the rearm boundary.

- Drop suppresses the target sample IRQ, with subsequent sample IRQs unaffected.
- Delay with `k` periods suppresses that IRQ and releases its saved origin exactly
  `k * PERIOD_TICKS` edges later. Subsequent ordinary IRQs continue. Coincident IRQ pulses
  coalesce on the physical IRQ output, while `delayed_interrupt` identifies the release.
- Freeze ignores actuator writes over `[injection, injection + k periods)`. Safe application
  still wins. The stored actuator continues driving the plant until the monitor trips.
- Overload asserts a request over the same interval. Actual processor overload software is
  a future task; simulation checks the request and a declared service response, not processor
  execution time.

The delay-service test waits for the saved delayed IRQ and does not service intervening normal
IRQs. This stimulus yields two missed periods and a monitor trip at the release. With period
100,000 and threshold two, injection-to-detection is exactly 200,000 ticks, and first-missed-
deadline-to-safe-state is 100,000 ticks. These are simulation invariants, not board statistics.

## Simultaneous capture and losses

`control_event_capture.sv` snapshots all eight supported control strobes, each cycle tag and a
single free-running 64-bit counter value before serialization. Accepted groups retain that
value through the stream. Within a group, old-cycle events precede new-cycle events; equal
cycles sort by code. Groups retain capture order. `ACT_LATE` is optional in the domain snapshot;
archived snapshots and record format v1 remain unchanged.

The default queue holds 64 groups. Each head emits one record per capture edge. Queue-full
rejects the newest complete group and counts its set bits; a full downstream FIFO drops and
counts each serialized record. Both contribute once to a saturating 32-bit `overflow_count`.
Any loss invalidates the host run. No source is stalled and no dropped event is recreated.
The FIFO uses the existing common-reset CDC contract. Neither group serialization nor RAM
inference establishes a 100 MHz board timing result.

## Reproduce

```bash
.venv/bin/pytest -q tests/test_control_plant_witness.py tests/test_control_faults.py
yosys -s rtl/check_control_equivalence.ys
verilator --lint-only --Wall --top-module control_plant_witness rtl/*.sv
```

Tests exercise both plants against exact integer transitions and an independent analytic step
response, signed actuator changes, references, saturation, healthy and four injected scenarios,
exact-deadline and repeated stale commands, simultaneous timestamps, queue wrap, counted losses
and reset. The host command verifies the hash-bound RTL sources, executable and tracking series.
Power is explicitly absent, so those reports cannot qualify complete board evidence.

The equivalence script compares each prepared component with `opt -full` (word-level
arithmetic), including both plant modes, cycle registers and a two-group capture queue.
It checks optimization semantics component by component. The integrated wrapper is exercised
through public-port RTL-to-host tests; a monolithic technology-mapped system proof has not been
completed. This does not qualify a vendor netlist, physical CDC, RAM mapping or place-and-route.
