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
commands replay through simulated actuator transactions. Capture I/O registers and AXI transport
are exercised against the actual plant in simulation; board processor service, vendor timing constraints,
power readings and physical safe-state acceptance remain planned.

## Ports and configuration

All inputs except `drain_request` and the asynchronous `pps_in` are synchronous to `capture_clock`; drain inputs and outputs
belong to `drain_clock`. `run_reset_n` asynchronously asserts the common run reset; each domain
releases it after two local edges. A reset flushes events, plant state, monitor and injection.
`capture_active` marks local reset release. `control_cycle.sv` owns the sample period,
actuator register, command classification and event strobes. Hold configuration stable for the run,
and do not change `reference_mode` or `reference_amplitude` in the cycle that raises `enable`.

| Inputs | Contract |
|---|---|
| `enable`, `stop_after_cycle` | Start at cycle zero; hold enable high through the last cycle's deadline. Stop includes that deadline, with no extra sample. Reset before restarting. |
| `sample_read` | First sample read per cycle produces `SAMPLE_READ`. |
| `actuator_write`, `command_cycle`, `command_value` | Synchronous actuator command, signed Q8.24. Matching current-cycle writes strictly before its deadline satisfy it. Only the first such write produces `ACT_WRITE`; later timely writes may replace the actuator. |
| `fault_arm`, `fault_kind`, `fault_cycle`, `fault_periods` | Arm one injection before its target sample. Kinds 0/1/2/3 are drop/delay/freeze/overload request. Positive duration required, target cannot be past or beyond the final cycle. |
| `reference_mode`, `reference_amplitude`, `reference_offset`, `ramp_increment`, `phase_increment` | Step/ramp/sine selection 0/1/2; signed Q8.24 values, modulo-16 phase increment. Mode 3 uses zero amplitude plus offset. Mode and amplitude are read one capture edge before each sample. |
| `drain_request` | Request next record; inspect data only with `drain_valid`. |

| Outputs | Contract |
|---|---|
| `sample_valid`, `cycle_number`, `sample_value`, `velocity`, `reference_value` | New registered sample/target on the update edge. Thermal velocity is zero. |
| `actuator_value` | Latest accepted command; defined safe value wins on monitor trip and remains until reset. |
| `sample_interrupt`, `delayed_interrupt`, `delayed_cycle` | Edge strobes; delayed origin survives coincident normal IRQ delivery. |
| `safe_interrupt` | Latched trip indication, not a one-clock pulse. |
| `run_finished`, `capture_quiescent` | Capture-domain final-deadline completion and completion with no remaining event group or event strobe. The latter is a register one capture edge behind its terms, so a bus-domain synchroniser never samples a combinational hazard of them; it does not imply the downstream FIFO or its receiver has drained. Both are also exposed by the fabric controller wrapper. |
| `fault_ready`, `freeze_actuator`, `overload_request` | Injection availability and synchronous action levels. Readiness falls after trip or run completion; invalid schedule data is refused. |
| `total_misses`, `consecutive_misses`, `late_commands` | Saturating 32-bit capture-domain counters; not coherent processor snapshots. |
| `plant_clipped`, `reference_clipped` | Saturation at the last sample; retain/sample these with `sample_valid`. These are flags, not cumulative clipping counters. |
| `counter_ticks`, `overflow_count`, `buffer_full` | Capture timebase, saturating combined lost-event count and downstream FIFO full status. Group queue exhaustion can lose events even when FIFO full is low. |
| `drain_valid`, `drain_empty`, `drain_record` | Existing 16-byte stream in the drain domain. |
| `sample_ready_mirror`, `actuator_write_mirror`, `safe_state_mirror` | Capture-domain registers for an [external time tagger](MEASUREMENT_PROTOCOL.md#external-cross-check). The first two toggle on the edge that records each `SAMPLE_READY` and `ACT_WRITE`, so each edge carries the counter value of its record; the third rises with `SAFE_STATE` and follows `safe_interrupt`. Reset clears all three. The fabric controller wrapper, `axi_control_witness` and `icicle_witness` expose them. |

Parameters: `PERIOD_TICKS` defaults to 100,000 at the planned 100 MHz (1 kHz);
`MISS_LIMIT` defaults to three, must be positive; `SAFE_VALUE` defaults to zero.
`THERMAL` selects the plant. `ADDRESS_BITS` is the existing FIFO width (1–14), and
`GROUP_ADDRESS_BITS` is the simultaneous-event queue width (1–8, default six).
Plant coefficients are compile-time signed Q8.24 parameters. Changing period requires
recomputing them for that physical sample interval. Clock and period parameters do not qualify
a physical oscillator or board rate.

## Capture I/O registers

[`axi_control_witness.sv`](../rtl/axi_control_witness.sv) is the combined AXI peripheral:
it connects the capture I/O and configuration registers to the actual plant and exposes its
FIFO through the bus-domain record window. Its 13-bit AXI addresses are offsets within an
externally decoded 8 KiB aperture of two [register pages](#register-pages). Plant coefficients and capture parameters retain the raw plant
module's compile-time interface. Capture diagnostics and IRQ strobes belong to `capture_clock`;
the record window, `run_drained` and retained `interrupt_line` belong to `bus_clock`.
[`icicle_witness.sv`](../rtl/icicle_witness.sv) is the board-facing AXI4-Lite boundary: it
accepts the interconnect's 38-bit address and forwards the selected low thirteen bits to this
peripheral. Its physical decode and retained interrupt route still require Libero validation.
A low `capture_clock_locked`, the lock of the capture clock's PLL, acts as `run_reset_n`: the
witness stays in reset until that PLL locks, and losing the lock resets both clock domains.
The processor/kernel interrupt mapping remains unqualified. External `run_reset_n` aborts AXI transactions
as well as the run; quiesce the master before asserting it. The software run-bank reset below
retains the AXI transport and its accepted responses.

[`control_io_registers.sv`](../rtl/control_io_registers.sv) decodes capture-domain requests
from [`axi_lite_clock_bridge.sv`](../rtl/axi_lite_clock_bridge.sv). Addresses are byte offsets
within the peripheral. Only aligned 32-bit accesses are accepted. All writes require four
byte strobes; unsupported accesses return AXI `SLVERR` without changing state.

| Offset | Access | Contract |
|---|---|---|
| `0x00` | Read | Return the current sample and snapshot its cycle, velocity, reference, time and miss count at the same capture edge. Refused while disabled or finished. |
| `0x04` | Read | Bits 0–4: snapshot valid, run enabled, run finished, safe latched, capture quiescent. |
| `0x08`, `0x0c` | Read | Read low timebase word at `0x08`, then its latched upper word at `0x0c`. Upper-word reads before an observation are refused. |
| `0x10`, `0x14`, `0x18` | Read | Snapshot cycle, velocity and reference. |
| `0x1c`, `0x20`, `0x24` | Read | Snapshot low time word, upper time word and total misses. |
| `0x28`, `0x2c` | Read/write | Stage the command cycle and signed Q8.24 command value. Readback retains the last staged values. |
| `0x30` | Read/write | Read the current capture/FIFO overflow count. Write 1 to commit both command stages; successful commit consumes both staging credits and emits one actuator-write strobe. |
| `0x34` | Read | Current total deadline misses, including deadlines after the last sample read. |

Snapshot fields are unavailable before the first successful sample read. Once captured, they
remain unchanged across subsequent plant steps and run completion until another sample read
or common reset. Timebase observation is independent of the sample snapshot. The `SAMPLE_READ`
event retains the snapshot's capture-edge timestamp; AXI response arrival is a later event.

Commit is refused if either stage is missing, the run is disabled or finished, or safe state is
latched. A successful bus response acknowledges the submitted transaction; the independent
deadline monitor still determines timely acceptance and safe override. A mismatched command
cycle remains subject to the plant's late-command contract. Reset invalidates snapshots,
time observations and staging credits.

## Run configuration registers

[`run_configuration_registers.sv`](../rtl/run_configuration_registers.sv) holds the capture-domain
run configuration. Writes require aligned full words. Configuration is immutable after a
successful fault arm or start. Start is one-shot until common reset; writing zero cannot disable
an active run or erase its deadlines. The sample period is read-only because the compiled plant
coefficients declare that interval.

| Offset | Access | Contract |
|---|---|---|
| `0x38` | Read/write | Read enabled state; write 1 to start once. |
| `0x3c`, `0x40` | Read/write, read | Final cycle number and compiled period in capture ticks. |
| `0x44` | Read/write | Reference mode: step 0, ramp 1 or sine 2. Other values are refused. |
| `0x48`, `0x4c`, `0x50` | Read/write | Signed Q8.24 reference amplitude, offset and ramp increment. |
| `0x54` | Read/write | Modulo-16 phase increment, restricted to 0–15. |
| `0x1000`, `0x1004`, `0x1008` | Read/write | Fault page: fault kind 0–3, target cycle and duration in periods. |
| `0x100c` | Read/write | Fault page: read armed configuration state; write 1 before start to arm one fault. Duration must be positive and target no later than the final cycle. |
| `0x68` | Read | Bits 0–2: injector ready, actuator freeze and software overload request. |
| `0x6c`, `0x70`, `0x74` | Read | Compiled thermal-model flag, miss limit and signed safe actuator value. |
| `0x78`, `0x7c` | Read | Fixed-point fractional bits (24) and register ABI version (2). |

Arming copies the declared schedule into the actual injector on the accepted capture edge and
locks configuration readback to that schedule. Start remains available after arming. Common
reset clears enabled/armed state and restores the step reference with amplitude one, zero
offset/ramp, phase increment one and final cycle zero. Runtime overload execution is separate
from the hardware overload-request level.

## Register pages

Register map version 2 divides the aperture into two 4 KiB pages. The run page, offsets
`0x000`–`0x0ff`, holds every register above except the fault schedule; the fault page holds the
fault kind, target cycle, duration and arm registers at `0x1000`, `0x1004`, `0x1008` and
`0x100c`. The run page refuses `0x58`–`0x64`, the schedule's offsets in version 1, and every
other address of the aperture returns SLVERR. The injector status at `0x68` stays on the run
page, because a controller under test must see the overload request. A system can therefore give
a controller a mapping of the run page alone: on Linux the two pages are separate UIO devices,
and the run programs map the fault page only to arm a fault before the start
([UIO transport](#linux-uio-transport)). The schedule's write rules are unchanged: writes only
before the start and no arm, and one arm per common reset.

## FIFO record window and completion

[`event_record_window.sv`](../rtl/event_record_window.sv) prefetches one actual FIFO record
and holds it for bus reads. Read `0x80`, `0x84`, `0x88` and `0x8c` for its four words in
increasing significance; arbitrary read order is allowed. Write 1 with all byte strobes to
`0x94` to consume the held record. Invalid accesses and POP without a held record return
`SLVERR`. Prefetch consumes a FIFO entry into receiver storage; that receiver record remains
part of the undrained stream until POP.

Status at `0x90` reports held record, fetch pending, FIFO empty and run drained in bits 0–3.
`run_drained` requires all three storage conditions to be empty and capture quiescence to
have crossed four bus synchroniser stages. This delays completion past the FIFO's pointer
synchronisers and registered empty calculation. Neither capture completion nor FIFO empty
alone proves the stream has drained. Reset clears receiver and completion state.

Simulation tests read and POP actual records through the combined AXI top, bind the binary
drain to source/simulator hashes and send it through the public host analyzer. Resulting
reports remain `simulation_only`, with no processor timing, power or physical CDC claim.

## Software run reset

Bus-local `0x98` controls the run banks. Write 0 with all byte strobes to assert reset, then
write 1 to release it. Assertion is permitted only while the run is disabled or finished;
an active run's deadlines cannot be erased by software reset. Invalid data, partial writes
and repeated release while already enabled return `SLVERR` without changing state.

Read bits 0–3 for bank enabled, capture ready, bus ready and reset assertion permitted.
The permission is a capture-clock register, one capture edge behind the run flags, before
its bus synchroniser.
Poll bits 0–2 until all three are set before configuring a fresh run. Capture readiness is
registered after local reset release and then synchronised into the bus domain; a stopped
capture clock cannot report ready. Holding bank reset makes run-register accesses invalid,
while the local reset register remains accessible.

Bank reset flushes plant, monitor, injection, configuration, sample/time snapshots, FIFO and
receiver state in both domains. It preserves AXI channel state and the request mailbox, so an
already accepted read response or reset write response remains valid under backpressure.
Consume responses from the previous run before using a new run's data. Resetting an unconsumed
receiver record discards that run's remaining stream; drain and save it first when retaining
the run's evidence.

## Retained processor interrupt

[`retained_interrupt.sv`](../rtl/retained_interrupt.sv) turns capture IRQ events into a retained
bus-domain level. Its 64-bit generation counter increments once per capture edge containing
sample interrupt, the first safe indication or the first run-finished indication. Simultaneous
sources coalesce. Persistent safe/finished levels do not repeatedly increment it. The counter
outlasts a run with a 32-bit final cycle number; it resets with the common run banks.

| Offset | Access | Contract |
|---|---|---|
| `0x9c` | Read | Return current generation's low word and snapshot both words. |
| `0xa0` | Read | Return the snapshot's upper word; refused before a low-word observation. |
| `0xa4` | Write | Write 1 with all strobes to acknowledge the observed generation and consume its snapshot credit. Missing credit, partial writes or other data are refused. |
| `0xa8` | Read | Bits 0–1: interrupt pending and snapshot valid. |

`interrupt_line` stays asserted until the observed generation is acknowledged. A newer event
remains pending when software acknowledges an older snapshot. An event still in the synchroniser
pipeline reasserts the level when it reaches the bus domain. Acknowledging the IRQ does not clear
the independent safe latch. Read the existing capture status to inspect safe/finished state.
The Gray counter uses two bus synchroniser stages; physical skew and maximum-delay constraints
must be qualified before board use. These simulations do not verify kernel IRQ handling.

## Fixed-point plant

Signed Q8.24 means raw integer divided by 2^24, range [-128, 128−2^-24]. A product is signed
64-bit; three products accumulate in signed 66-bit precision. Arithmetic right shift by 24
rounds toward negative infinity. Saturation occurs once at the state/output boundary. Both
mechanical states update from their old values together; intermediate states are not rounded.

Each 32 × 32 product is formed one capture edge before it is used. `split_multiplier.sv` splits
both operands into a signed high and an unsigned low 16-bit half and registers the four half
products (17 × 17 bits, one math block each); their shifted sum is exact. The plant multiplies
its state and its held actuator every edge; `control_cycle.sv` reports an accepted command with
`actuator_accept`, and the plant loads it in that cycle, so a command accepted in the cycle
before a sample reaches that sample. A trip or the safe latch applies `C * SAFE_VALUE` in the
sampling cycle itself. The reference multiplies its waveform by the amplitude every edge, also
in reset; the shift, offset, saturation and clip flag stay in the sampling cycle. The sum,
floor and saturation remain in `fixed_point_math.sv`. Every output is the same in every cycle as
with same-cycle products, because consecutive samples are at least two capture cycles apart
(`PERIOD_TICKS ≥ 2`), the state, phase and ramp change only at samples, the configuration
registers accept mode and amplitude only while the run is disabled, and the safe latch holds
until reset. `make plant-timing-invariants` proves these three invariants and the product
identity at reduced width by temporal induction, for every reachable state, each with a
counterexample to its negation. Module ports carry the
same rule: `sampled_plant` and `reference_generator` must never sample in consecutive cycles,
and `reference_generator` must see mode and amplitude unchanged over the edge before a sample.

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

`make safe-state-invariants` proves the monitor's safe-state rules by temporal induction, from any
state reached through a reset with every input free, for miss limits 1, 3 and 255: the
consecutive miss count never exceeds the total, the latch sets only on a missed deadline that
completes `MISS_LIMIT` consecutive misses, a latched monitor has counted at least `MISS_LIMIT`
misses, and the latch holds until the next reset. Its negation, that the latch never sets, yields
a counterexample (`tests/test_safe_state_proof.py`).

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

The default queue holds 64 groups. Each head emits one record per capture edge: a three-level
comparison tree picks the earliest pending cycle tag, lower code first on equal tags, and the
group leaves the queue with its last pending event, which the remaining-event mask shows without
waiting for that choice. The head group's timestamps sit in a register copy of the head slot,
loaded from the next slot when a group leaves and written through when the pushed group becomes
the head in the same edge, so the choice starts from a register rather than a queue read.
`record` carries data only while `record_valid` is high. Queue-full rejects the newest complete group and counts its set bits; a
full downstream FIFO drops and counts each serialized record. Both contribute once to a saturating 32-bit `overflow_count`.
Any loss invalidates the host run. No source is stalled and no dropped event is recreated.
The FIFO uses the existing common-reset CDC contract. Neither group serialization nor RAM
inference establishes a 100 MHz board timing result.

## Pulse-per-second reference

`pps_in` takes an external pulse-per-second reference, such as a GNSS receiver's timing output,
so that the host analysis can measure the counter's rate against it. Two capture-clock synchroniser
stages and an edge register follow the pin; they reset high, so a pulse that is already high when
the run reset releases is not an edge. From that release until the run finishes, each rising edge
increments a 32-bit sequence number and its counter value is held as one record: code 18 (`PPS`,
the `CONTROL` profile's reference event in the measurement domain), the edge's sequence number in
the cycle field and the counter value of the cycle in which the edge register sees the rise, two
capture periods after the second stage takes the new level. The record enters the event FIFO on an
edge where no capture record is valid, so a control event is never displaced or delayed by it; a
reference record may therefore follow capture records with later counter values. An edge that
arrives while the previous record still waits is counted in the sequence but not recorded, so the
host sees the gap, and no reference loss enters `overflow_count`. The run is quiescent only when no
reference record waits. In simulation and the native programs the input stays low.
[`tests/rtl/pps_reference_tb.sv`](../tests/rtl/pps_reference_tb.sv) holds the drain until an edge
waits and the next is lost, and the plant testbench's `+PPS_PERIOD` run gives the same control
records as the run without the pulse. The host decoding and fit are in
[`HOST_ANALYSIS.md`](HOST_ANALYSIS.md#pulse-per-second-reference-timebase).

## Reproduce

### Native AXI simulation process

`make axi-simulator SIMULATION_THERMAL=0` builds the mechanical production top;
select `1` for the thermal plant. The executable is
`build/axi_simulator_0/axi_simulator` or `build/axi_simulator_1/axi_simulator`.
These models use a 32768-tick period, a 256-record FIFO, a 16-group capture
queue, 5 ns capture half-period and 7 ns bus half-period. No vendor IP is used.

The process accepts decimal request lines on stdin and flushes one
`response,value,simulation_nanoseconds` reply on stdout:

| Request | Effect |
| --- | --- |
| `R address` | Actual AXI register read; reply retains its RRESP and data |
| `W address data strobes` | Actual AW/W/B transaction; reply retains BRESP |
| `T nanoseconds` | Advance both simulated clocks |
| `I nanoseconds` | Advance until retained IRQ or the bounded wait expires; value is IRQ level |
| `Q` | Finalize and exit without a reply |

Address, data and strobe bounds are 255, 4294967295 and 15. Advance/wait requests
are bounded to 10000000 ns, each AXI transaction to 100000 ns. Invalid process
requests fail before access; aligned register permissions and SLVERR come from
the production RTL decoder. EOF also finalizes the process. Reset starts both
clock domains; software must poll register `0x98` after a later bank release.

Clocks advance only during requests. Host calculation and pipe waiting consume
no simulated time; callers must explicitly advance time to model delay. This
transport exercises actual CDC, plant, monitor and FIFO state. It does not
establish Linux scheduling latency, UIO/kernel IRQ behavior, physical CDC or power.

`tests/test_axi_simulator.py` streams live sample snapshots to each public C/Rust
PID/LQR executable and submits the returned commands through AXI. Both plant
modes retain matching command/plant histories, original read-edge timestamps and
32768-tick sample/deadline cadence through the event receiver.

```bash
.venv/bin/pytest -q tests/test_axi_simulator.py
```

### Linux UIO transport

`make uio-transport` builds `build/uio_transport`. It accepts explicit arguments
`uioN name version map physical_address_decimal` followed by the same stdin
R/W/T/I/Q protocol. Name, version, sysfs map identity and `/dev/uioN` major/minor
must match before access. Only the `uio_pdrv_genirq` platform driver is accepted;
the tool does not bind devices, load drivers or choose an aperture automatically.

The selected map uses `map * page_size` as its mmap offset, then adds the sysfs
`offset` to the returned pointer. For this driver, the declared physical register
address must equal the page-aligned sysfs `addr` plus `offset`. The page-rounded
map size must contain the entire 256-byte run-page window and must not reach past its 4 KiB
register page, so the map never covers the fault page. The tool verifies map
metadata again after mmap, requires ready run banks and reads register ABI version
2 before serving requests. It serves the run page only. These rules follow the
[Linux UIO HOWTO](https://docs.kernel.org/driver-api/uio-howto.html) and the
[generic platform driver](https://github.com/torvalds/linux/blob/master/drivers/uio/uio_pdrv_genirq.c).

Accesses are single volatile little-endian 32-bit loads/stores with RV64
`fence iorw,iorw` or x86_64 full barriers. Partial strobes and unaligned offsets
are refused before access. UIO does not return AXI response signals: response
zero means the CPU access completed, and response two is a local refusal.
Callers must respect the documented register permissions and state; an invalid
remote access may produce a CPU bus fault rather than a recoverable SLVERR reply.

`I` re-enables the generic driver with a native-endian signed 32-bit value 1,
waits with `ppoll` and reads exactly four bytes of cumulative UIO interrupt
count. The in-process API retains that count independently of the RTL IRQ
generation. A false result means timeout. The caller must ACK the observed
RTL generation before its next wait; ACK never resets the kernel counter.
`T` sleeps while hardware keeps running. Reply time is absolute monotonic host
nanoseconds, separately identified from both fabric ticks and simulator time.

`UioDevice` is also available to an in-process native controller. Ownership uses
a nonblocking advisory file lock, so all cooperating users must take that lock.
Close unmaps the aperture and closes the descriptor; it disables IRQ only after
this instance has successfully managed IRQ. It never resets an active run.
No board is available: builds and genuine public-entry refusal tests currently
cover this adapter. Successful hardware mmap, MMIO, kernel IRQ delivery, RV64
cross-compilation and board acceptance are still unverified.

```bash
.venv/bin/pytest -q tests/test_uio_transport.py tests/test_axi_simulator.py
```

### Native run controller

`make run-simulation SIMULATION_THERMAL=0` or `1` builds
`build/run_simulation_0/run_simulation` or its thermal counterpart. Invoke it
with `configuration events.bin tracking_raw.csv`. It links the actual C PID/LQR
kernel directly into the production RTL model. `make run-uio` builds
`build/run_uio`, which accepts the same first three arguments followed by
`uioN name version map physical_address_decimal` and uses the same run lifecycle
with direct in-process MMIO. A run with a scheduled fault also needs
`--fault-uio "uioN name version map physical_address_decimal"`, the fault page's own UIO
device at the run page's address plus `0x1000`, and refuses it for a run without one. The
program maps the fault page with the same identity checks, writes the schedule and unmaps it
before it writes START, so the controlling loop never holds a fault mapping.
Successful UIO operation is not yet board-qualified.
`make run-amp-uio` builds the separate [Linux AMP logger](AMP_LINUX.md), which drains
firmware telemetry and fabric events after the dedicated controller arms. Its resource
configuration names both IRQ-free maps explicitly; Linux does not write controller commands
or acknowledge the dedicated hart interrupt.

The simulation transport advances its context one nanosecond at a time. It evaluates changed
inputs before sampling the next bus edge, toggles the 7 ns/5 ns half-period clocks, and evaluates
again when a clock changes. This production RTL has no delayed processes or time-dependent HDL
expressions, so a step whose clocks and inputs did not change needs no evaluation: the model keeps
the state of its last one. Input-before-clock ordering follows the
[Verilator evaluation guidance](https://verilator.org/guide/latest/connecting.html).
Reference comparisons preserve byte-identical events, raw tracking and summaries for both plants,
PID/LQR, different references and injected freeze/overload cases. This is simulation parity,
not physical timing or processor performance evidence.

Configuration is whitespace-separated, with every field required in this order:

```text
pid 32 32768
33554432 16777 8388608 4194304 33554432 16777216 50331648 -67108864 67108864 -33554432 33554432
0 16777216 0 16777 1
none 0 0
0 0
```

The rows supply controller (`pid`/`lqr`), cycle count and expected compiled
period; eleven coefficients in the native controller API order; reference mode,
amplitude, offset, ramp and phase; fault kind (`none`, `drop`, `delay`, `freeze`,
`overload`), target cycle and duration; overload work iterations and modeled
overload nanoseconds. Raw reference and controller fields use signed Q8.24.
None requires zero target and duration. Overload work is an actual volatile
sum of squared indices, recorded in the raw trace. Modeled delay advances RTL
time and is rejected by `run_uio`; host calculation alone advances no simulated
time. The physical path can execute work iterations with modeled delay zero.

The controller refuses reset of active runs or unread previous records, then
polls bank readiness, checks ABI/Q format/compiled period and configures before
START. Each retained IRQ observation snapshots its generation, reads actual
sample metadata, computes a native command, stages/commits it and ACKs only the
observed generation. Safe/finished status vetoes command submission independently
of kernel output. Raw tracing preserves submitted status; a register commit is
not proof that the monitor accepted the actuator value during a freeze. A single modeled
500000 ns overload crosses one 32768-tick period: the actual AXI submission can succeed while
the independent witness records `ACT_LATE` and one miss without entering safe state. Tests
exercise this distinction on both plants with PID and LQR and replay commands through C and Rust.

The run waits for configured final-cycle completion, producer quiescence and
receiver drain. Safe latch does not end the configured run: misses can continue
after the third miss first trips safe. Final live counters come from `0x30` and
`0x34`, not stale sample metadata. Overflow makes the executable fail.
Event output is the original 16-byte little-endian FIFO record. Tracking stores
only observed samples, raw kernel state, original capture ticks and IRQ generation;
dropped IRQs do not create invented tracking rows. Outputs are created exclusively;
failed runs retain partial files and existing files are never overwritten.
The public output API refuses event/sample writes after completion and repeated completion calls,
retaining the already closed files. The tracking header is flushed and checked before software run-bank reset/configuration and
START. A header write failure leaves the new event file empty. This checks initial write
readiness, not durable storage or future free space. Later event, tracking, close or summary
write failures still fail the run and retain partial evidence. The native tests use real
child-only file-size limits and `/dev/full`; they do not replace the output streams.
Active drain batches contain at most eight records before returning to IRQ service;
final drain repeats batches until the actual receiver reports completion.
Completion timeout covers the full configured cycle count and compiled period
at the target 10 ns tick, plus one second of margin. Configurations that overflow
this unsigned nanosecond timer are refused before starting. Safe IRQ silence does
not shorten a run; a physical clock still requires the board acceptance check.

The simulation tests cover both plants, both kernels, all references and all
fault kinds. Every recorded controller transition is replayed through the actual
C and Rust streaming CLIs. The native entry accepts optional `--metadata file`
for exclusive configuration and completion metadata. The
[host capture command](HOST_ANALYSIS.md#native-simulation-capture) compiles a frozen
source snapshot, binds its executable and original outputs, and regenerates the
host reports with explicit observed tracking coverage. PAC1934 logging and physical
UIO qualification remain outstanding.

```bash
.venv/bin/pytest -q tests/test_native_run.py
```

### Fabric and host report integration

```bash
.venv/bin/pytest -q tests/test_control_plant_witness.py tests/test_control_faults.py \
  tests/test_plant_timing.py
make plant-timing-invariants
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

### Native Linux scheduling

`run_simulation`, `run_uio` and `run_amp_uio` accept `--cpu N`, `--scheduler normal|fifo` and
`--priority N`, in any order after the positional arguments. The simulation capture
command forwards the same options. Without them, the run inherits its calling
thread's scheduler and allowed CPU set. `normal` means Linux `SCHED_OTHER`, priority
zero. `fifo` requires an explicit allowed CPU and priority within the kernel's FIFO
range. Requested CPU selection narrows the inherited set; it cannot widen a cpuset.

The runtime applies and reads back the policy before acquiring the device or opening
raw outputs. A rejected request fails the run; it never falls back silently. Only
the calling run thread is changed. Parent processes, kernel IRQ threads and other
services retain their own policies. Affinity does not reserve or isolate a CPU.

Native metadata contains `host_policy`: requested CPU/scheduler/priority (minus one
means inherited), actual kernel scheduler and priority, the complete allowed CPU
list, observed CPU and nice value read immediately after applying the request.
These are startup facts, not a measurement of scheduling latency or proof of a real time
kernel. Later external policy/CPU changes are outside this startup snapshot.

```bash
build/run_simulation_0/run_simulation configuration.txt events.bin tracking_raw.csv \
  --metadata native_metadata.json --cpu 0 --scheduler normal
```

CPU zero is an example; select an actual CPU from the process's inherited allowed
set. FIFO permission depends on the kernel's capabilities and resource limits.
See the Linux [`sched_setaffinity`](https://man7.org/linux/man-pages/man2/sched_setaffinity.2.html)
and [`sched_setscheduler`](https://man7.org/linux/man-pages/man2/sched_setscheduler.2.html)
interfaces. Hardware processor timing and physical acceptance remain unqualified.

### Kernel trace stop

`run_uio` and `run_simulation` accept `--trace-stop miss|safe --tracefs DIRECTORY`, together and
only with `--metadata`. Before the run they require that kernel tracing is on in the tracefs
directory (`tracing_on` reads `1`), record the trace clock that `trace_clock` selects and open
`trace_marker` and `tracing_on` for writing. After each sample interrupt the run reads the
fabric's miss counter (`0x34`) and safe-state flag; at the first observation with a missed
deadline (`miss`) or with the safe state latched (`safe`) it writes the marker
`loop-timing-witness trace stop: <condition> misses=<n> safe=<0|1>` and then `0` to `tracing_on`,
as `cyclictest -b` does at its latency threshold, so the ring buffer ends at the cause instead of
being overwritten after it. The observer adds one register read per interrupt. The stop follows
the missed deadline by up to one sample period and the interrupt service, so the trace covers the
cycle that missed it. The trace is the supervisor-mode kernel's: time a hart spends in
machine-mode firmware (OpenSBI or the HSS), for an SBI call or a machine-mode interrupt, is not
traced and shows only as time passing between traced events.

The native metadata records `trace_stop`: the condition, tracefs directory, trace clock, whether
the condition occurred, the miss count and safe flag at the stop and its `CLOCK_MONOTONIC` time.
Read the trace afterwards, for example with `trace-cmd extract` or by copying `trace`, select
`mono` as the trace clock beforehand to compare its timestamps with the recorded stop, and declare
the file as the run manifest's `files.kernel_trace` with its SHA-256
([host analysis](HOST_ANALYSIS.md#inputs)). `run_amp_uio` refuses a trace stop: its controller runs
on another hart, outside the Linux trace. A tracefs write that fails during the run refuses the
run. The simulation program accepts the options so that the path is tested; there the trace
records the host, not fabric timing.

### Native FIFO loss qualification in simulation

`make run-simulation SIMULATION_FIFO_ADDRESS_BITS=1` compiles a two-record FIFO.
`RUN_SIMULATION_DIRECTORY` selects a distinct build directory when preserving other simulator
variants. Default native builds retain 256 records. The
[public capture producer](HOST_ANALYSIS.md#native-completion-and-fifo-loss) binds the compile
parameters, retains actual native completion counters and reports declared FIFO loss as invalid.
Live monitor misses are distinct from misses inferred from an incomplete event stream;
a dropped actuator record cannot establish a real missed deadline.
