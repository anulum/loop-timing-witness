<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — architecture
-->

# Architecture

## Evidence state

The full board instrument remains planned and no measured result exists. Synthesizable
timestamp capture, a dual-clock record buffer, numeric event codes, a run-manifest schema and
host analysis exist. Both sampled plants, references, deadline/safe-state monitor, fault injector
and simultaneous-event capture feed the drain stream and host CLI in simulation. C, Rust and
RTL PID/LQR kernels have bit-exact parity, with an integrated fabric feedback loop and native
command replay through simulated actuator transactions. Native AXI simulation and Linux UIO run
software are implemented; physical I/O, power acquisition and processor timing remain unqualified.
No physical board is available. The
machine-readable design contract is `measurement-domain.json`, validated by
`tools/validate_measurement_domain.py`; changes to that contract also update its schema, this
document and the measurement protocol.

## Target platform

PolarFire SoC Icicle Kit, device MPFS250T-FCVG484E, as described in the board user guide
(Microchip DS60001679E). Facts used by the design:

| Item | Use in the design |
|---|---|
| SiFive E51 monitor core and four U54 application cores | E51 boots the system; U54 cores run Linux or a bare-metal controller |
| On-board 50 MHz oscillator | reference for the fabric clock conditioning circuit |
| PAC1934 power monitor on the processor subsystem I²C bus, four rails (VDD, VDD25, VDDA25, VDDA) | energy windows |
| Two Gigabit Ethernet ports | run control and data transfer to the host |
| Raspberry Pi 4 compatible header | optional mirror of the event strobes for an external logic analyser |

Not yet checked on hardware, and therefore not relied on: the asymmetric-multiprocessing
reference release for the current board support package, the PAC1934 sampling configuration of
the reference Linux image, and the fabric RAM budget used to freeze the event buffer size.

The board-facing `rtl/icicle_witness.sv` presents a 38-bit AXI4-Lite address port to a fabric
interconnect that selects the planned 256-byte register range at `0x60020000` through
`0x600200ff`. It passes the low eight address bits to `axi_control_witness` and exposes its
retained interrupt level. This boundary is exercised in simulation; the Libero interconnect,
capture clock, interrupt route and physical timing are not yet qualified.
The pinned Icicle reference source configures the FIC0 bus clock at 125 MHz from CCC GL0_0
and the witness capture clock at 100 MHz from CCC GL0_1. Those source settings do not
establish implemented clock rates or CDC timing closure.

## Block structure

```text
                 ┌──────────────────────── PolarFire SoC MPFS250T ────────────────────────┐
                 │  FABRIC                                                MSS              │
 50 MHz osc ───► │  CCC/PLL ─► 64-bit timebase (100 MHz, 10 ns)           E51: boot        │
                 │    │                                                   U54: Linux       │
                 │    ▼                                                   U54: bare-metal  │
                 │  Event witness ◄── strobes ── controller I/O register ◄── controller    │
                 │    │   (capture, buffer)          ▲    │                                │
                 │    │                              │    ▼                                │
                 │  Plant emulator (fixed point) ── sample-ready interrupt ──► MSS         │
                 │  Fabric controller (fixed-point PID / LQR) ◄─ placement select         │
                 │  Deadline and safe-state monitor ──► safe actuator value, fault flag   │
                 │  Fault injector (drop, delay, freeze, overload request)                │
                 │  Event buffer ─► AXI4 (fabric interface controller) ─► Linux UIO       │
                 │  GPIO mirror of the strobes ─► header (optional external witness)      │
                 └─────────────────────────────────────────────────────────────────────────┘
                        MSS I²C ─► PAC1934 (four rails) ─► Linux energy logger
                        Gigabit Ethernet ─► host: run control, transfer, analysis, report
```

## Fabric

### Timebase

A clock conditioning circuit derives 100 MHz from the 50 MHz oscillator. A free-running 64-bit
counter gives 10 ns resolution and cannot wrap in any planned run; the validator checks that the
counter width outlasts one repeat at the lowest sample rate. Multi-phase capture for finer
resolution is a later option and is accepted only if the known-period test shows the improvement.

### Plant emulator

A discrete-time second-order plant (mass, spring, damper) and a first-order thermal plant, in
signed fixed point with a documented Q format per plant. The plant updates once per sample period
(100 Hz to 20 kHz, 1 kHz by default) with the most recent actuator value that arrived before the
update; a late command is applied one period later and counted. A reference generator (step,
ramp, sine) provides the tracking target. Implemented Q8.24 equations, coefficients and ports
are specified in [`PLANT_WITNESS.md`](PLANT_WITNESS.md).

### Controller input/output register and strobes

An AXI4-Lite peripheral on a fabric interface controller holds the sample register, the actuator
register and the cycle counter. It raises the `CONTROL` profile strobes:

| Event | Meaning |
|---|---|
| `SAMPLE_READY` | plant update complete |
| `SAMPLE_READ` | first bus read of the sample register in the cycle |
| `ACT_WRITE` | first timely actuator command in the cycle |
| `ACT_LATE` | first accepted out-of-cycle or deadline-edge command, tagged with its observation cycle |
| `DEADLINE` | next sample instant |
| `SAFE_STATE` | safe actuator value applied by the monitor |
| `FAULT_INJECTED` | fault injector action |
| `FAULT_DETECTED` | monitor detects the injected fault |

### Event witness and buffer

`rtl/event_witness.sv` connects `rtl/event_record_capture.sv` to a Gray-pointer dual-clock
FIFO and separate reset-release synchronisers. It accepts one event-code/cycle tuple per
capture-clock edge without stalling the measured source. The original timestamp is retained
through the capture pipeline and drain. Event codes are declared in `measurement-domain.json`
and `rtl/event_codes_pkg.sv`. Public ports and reset/overflow behaviour are specified in
[`FABRIC_WITNESS.md`](FABRIC_WITNESS.md). The integrated plant entry point uses `control_event_capture.sv` to preserve simultaneous
strobes before serialization; its ports are in [`PLANT_WITNESS.md`](PLANT_WITNESS.md). The AXI
board interface remains planned.

The default buffer holds 16 384 records. A full buffer drops the newest record, pulses
`event_dropped`, latches `overflowed` and increments a saturating 32-bit count. Reset starts a
new run and flushes both clock domains; there is no independent-domain reset. Capture-domain
status is not a coherent processor snapshot. A nonzero overflow count invalidates the host run.

Linux is planned to drain at least 20 times per second. At 20 kHz with four periodic events per
cycle the buffer fills in about 205 ms, longer than the 50 ms slowest drain interval; the
validator checks that inequality and the declared Gray-pointer capacity. Drain frequency alone
cannot establish sustained throughput or prevent loss during software stalls; board RAM sizing,
drain bandwidth and physical CDC constraints still require qualification.

Derived intervals per cycle:

| Interval | Definition |
|---|---|
| scheduling latency | `SAMPLE_READ − SAMPLE_READY` |
| compute time | `ACT_WRITE − SAMPLE_READ` |
| loop latency | `ACT_WRITE − SAMPLE_READY` |
| time to safe state | `SAFE_STATE −` first missed `DEADLINE` |

A cycle misses its deadline when `ACT_WRITE` does not arrive before `DEADLINE`.

### Deadline and safe-state monitor

The monitor counts misses in hardware. After a configurable number of consecutive misses it drives
the actuator to a defined safe value, raises a latched fault flag and interrupt, and records
`SAFE_STATE`.

### Fault injector

Drops a sample-ready interrupt, delays it by a number of periods, freezes the actuator register,
or requests a processor overload scenario from the software load generator. Every injection is an
event on the same timebase, so detection latency comes from the same clock as everything else.

### Fabric controller

`fixed_point_controller.sv` implements PID with conditional integration and discrete LQR.
`fabric_control_witness.sv` connects it to the sampled plant and existing independent monitor,
record capture and drain. In simulation the first read follows sample-ready by one tick and
the timely actuator write follows by another tick. This is a registered RTL schedule, not
physical timing closure. Arithmetic, reset, coefficients and native counterparts are specified
in [`CONTROLLERS.md`](CONTROLLERS.md). A board placement register remains planned.

### Device-under-test slot and the `COMPUTE` profile

The register, strobes and witness are built around a generic slot: an AXI4-Lite peripheral with
input and output registers, a start strobe and a done interrupt. The `COMPUTE` profile records
`INPUT_WRITE`, `COMPUTE_START`, `COMPUTE_DONE`, `OUTPUT_READ` and `INTERRUPT_ENTRY`, from which the
manifest derives input-to-start, compute duration, done-to-interrupt and input-to-output
intervals. In this repository the profile is exercised with a fixed-latency test peripheral
written for the purpose; accelerator-specific adapters live in the accelerator's own repository.

## Processor subsystem

| Placement | Where | How it runs |
|---|---|---|
| `linux_user_space` | U54 application cores | user-space task, registers and interrupt through UIO, `SCHED_FIFO` with CPU affinity; with and without a PREEMPT_RT kernel if one builds for the board support package |
| `bare_metal_amp` | one dedicated U54 core | interrupt-driven bare-metal loop; Linux on the remaining cores for logging |
| `fabric_logic` | FPGA fabric | fixed-point controller; the processors only log |

Controllers are textbook PID with anti-windup and discrete LQR, with identical coefficients in C,
Rust and fabric logic and bit-exact fixed-point parity checked in simulation. Native streaming
CLIs, the in-process Linux UIO entry and [dedicated-hart ISA capture](AMP_SIMULATION.md)
are implemented. The latter executes source-bound firmware against production RTL; Linux/HSS/PMP
deployment ownership and physical qualification remain pending. The [Linux AMP collector](AMP_LINUX.md)
maps separate explicit mailbox/fabric resources without owning the controller IRQ, using the same
firmware-ready handshake and actual run-contract checks. Physical mapping and boot ownership
remain unqualified. The implemented host load generator covers idle, CPU arithmetic,
memory/cache strides, private loopback UDP and owned-file storage/fsync profiles. Source-bound
captures retain policy readback, actual operation counters and worker/native time brackets; see
[host load profiles](HOST_ANALYSIS.md#linux-host-load-profiles). These do not qualify physical
processor timing, NIC traffic or uncached block-device load. A Linux run
controller configures the fabric registers, starts and stops runs, drains the buffer, reads the
power monitor and writes the run files.

## Power and energy

The selected Microchip [`pac1934` driver](https://raw.githubusercontent.com/linux4microchip/linux/linux-6.18-mchp/drivers/iio/adc/pac1934.c)
uses the Linux IIO interface. The logger must bind the selected BSP/driver revision, channel-to-rail
mapping, shunts, sampling configuration and accumulator units. An assumed `hwmon` interface or
automatic direct-I²C fallback cannot establish that acquisition contract.

The native UIO entry accepts `--power-config file --power-journal file` together. Its separate
normal-policy worker validates the actual IIO node, kernel release, driver, enabled accumulators,
labels, sample rate and unsigned shunt scales. It preserves each raw/scale attribute with its own
host and fabric read brackets. The journal is acquisition evidence; it is not the analyzer's
qualified `power.csv`. The current host has no PAC1934 device, so successful physical acquisition
and energy-window qualification remain unverified. See [`HOST_ANALYSIS.md`](HOST_ANALYSIS.md)
for the explicit configuration and units.

Fabric counter brackets around acquisition and the driver's cache/refresh timing must be retained.
Sequential channel reads do not establish an atomic four-rail snapshot or an exact common fabric
tick. Energy-window alignment remains unqualified until the acquisition timing contract is
validated on the board. The reported metric is mean energy per control cycle over windows of many
cycles, per rail and for the four rails together, with the limits stated in
[`MEASUREMENT_PROTOCOL.md`](MEASUREMENT_PROTOCOL.md).

## Run records

| File | Content |
|---|---|
| event file | little-endian 16-byte records: `event_type` u8, `reserved_byte` u8, `reserved_word` u16, `cycle` u32, `timebase_ticks` u64; SHA-256 recorded |
| power file | timestamped rail voltage, current and energy samples; SHA-256 recorded |
| run manifest | versioned schema with run identity, UTC start, source kind, a hash-bound measurement-domain snapshot, placement, controller, plant, period, load case, fault schedule, hash-bound inputs and artefacts, overflow count, acceptance fields and notes |

No run is reported without its manifest and hashes.

## Host analysis

`tools/analyze_run.py` validates the run manifest and referenced file hashes, interprets the
verified measurement-domain snapshot, decodes events, computes derived intervals and their
distributions (median, 95th, 99th and 99.9th percentile,
maximum), deadline-miss rate, tracking error (RMS and peak), mean rail energy per cycle over
power-sampling windows, fault detection and time to safe state. It writes JSON, CSV and SVG
reports tied to sample counts and observation duration. Inputs and limits are specified in
[`HOST_ANALYSIS.md`](HOST_ANALYSIS.md). Board qualification and measured results remain absent.

## Verification of the instrument

1. **Simulation** before hardware: witness, buffer, plant, monitor and fabric controller with a
   vendor-neutral simulator, directed and randomised tests, bit-exact parity of fabric, C and
   Rust controllers, including complete 64,000-sample trajectories per plant/controller.
2. **Known-period test:** a period generated from the same timebase must appear as an exact
   interval; any deviation is a witness defect.
3. **Injected-delay test:** a delay of k periods must measure as k periods within one tick.
4. **Bus-offset calibration:** the fabric placement, with no processor involvement, gives the
   minimum read and write path latency, recorded as the instrument floor.
5. **External cross-check (optional):** mirrored strobes on a logic analyser agree within the
   analyser's resolution.
6. **Overflow test:** an undrained buffer must be counted as overflow and invalidate the run.

## Repository layout and contracts

| Path | Role |
|---|---|
| `measurement-domain.json` | identity, boundary, non-claims and planned measurement contracts |
| `measurement-domain.schema.json` | structural schema (JSON Schema 2020-12) |
| `run-manifest.schema.json` | versioned schema for a hash-bound run package |
| `capability-inventory.json` | generated from the manifest, embeds its SHA-256, empty at `architecture_only` |
| `rtl/` | plants, references, monitor, injector, simultaneous capture and dual-clock event stream exercised in simulation |
| `controllers/`, `benchmarks/` | native kernels, streaming interfaces and local regression records |
| `docs/CONTROLLERS.md` | common arithmetic, PID/LQR design, parity and simulation boundaries |
| `docs/PLANT_WITNESS.md` | fixed-point models, event and injection semantics, fabric entry point |
| `docs/FABRIC_WITNESS.md` | RTL port, reset, overflow and CDC contracts |
| `docs/HOST_ANALYSIS.md` | host command, file formats, calculations and report limits |
| `docs/MEASUREMENT_PROTOCOL.md` | measurement procedure and stated limits |
| `docs/THREAT_MODEL.md` | assets, trust boundaries, misuse paths, residual risks |
| `docs/adr/` | decision records |
| `tools/`, `tests/` | validation tooling and its tests |

Schema identifiers are versioned (`loop-timing-witness.measurement-domain.v1`,
`loop-timing-witness.capability-inventory.v1`, `loop-timing-witness.workflow-inventory.v1`,
`loop-timing-witness.dependency-licences.v1`); a consumer must reject an identifier it does not
know.

## What would change this architecture

A board measurement that contradicts a planned fact (buffer RAM budget, power-monitor sampling,
asymmetric-multiprocessing support), a failed known-period or injected-delay test, or a change of
the event record format. Each is recorded as a new decision record together with the manifest,
schema and protocol change.
