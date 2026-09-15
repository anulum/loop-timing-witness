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

Everything in this document is planned architecture. No fabric logic, processor software, host
analysis code or measured result exists. The machine-readable parts of the design are the
contracts in `measurement-domain.json`, validated by `tools/validate_measurement_domain.py`;
the prose parts are fixed here and change only together with the manifest, the schema and the
measurement protocol.

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
ramp, sine) provides the tracking target.

### Controller input/output register and strobes

An AXI4-Lite peripheral on a fabric interface controller holds the sample register, the actuator
register and the cycle counter. It raises the `CONTROL` profile strobes:

| Event | Meaning |
|---|---|
| `SAMPLE_READY` | plant update complete |
| `SAMPLE_READ` | first bus read of the sample register in the cycle |
| `ACT_WRITE` | bus write of the actuator register |
| `DEADLINE` | next sample instant |
| `SAFE_STATE` | safe actuator value applied by the monitor |
| `FAULT_INJECTED` | fault injector action |

### Event witness and buffer

On each strobe the witness captures event type, cycle number and counter value into a dual-clock
buffer of 16 384 records in fabric RAM. Linux drains the buffer at least 20 times per second. At
20 kHz with four periodic events per cycle the buffer fills in about 205 ms, longer than the 50 ms
slowest drain interval; the validator enforces this inequality from the manifest. Overflow is
counted, flagged and marks the run invalid; it is never silent.

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

Fixed-point PID with anti-windup and discrete LQR in fabric logic, with the same coefficients as
the software controllers, selected by a placement register and using the same strobes.

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

Controllers are textbook PID with anti-windup and discrete LQR, with identical coefficients in C
and in fabric logic and bit-exact fixed-point parity checked in simulation. A Linux load
generator provides idle, CPU, memory and cache, network and storage load cases. A Linux run
controller configures the fabric registers, starts and stops runs, drains the buffer, reads the
power monitor and writes the run files.

## Power and energy

Linux reads the PAC1934 in energy-accumulator mode on all four rails, through the kernel `hwmon`
driver where present and otherwise directly over I²C. Each power sample is paired with a counter
value read from fabric at the moment of the read, so energy windows align with control cycles. The
reported metric is mean energy per control cycle over windows of many cycles, per rail and for the
four rails together, per placement and load case, with the limits stated in
[`MEASUREMENT_PROTOCOL.md`](MEASUREMENT_PROTOCOL.md).

## Run records

| File | Content |
|---|---|
| event file | little-endian 16-byte records: `event_type` u8, `reserved_byte` u8, `reserved_word` u16, `cycle` u32, `timebase_ticks` u64; SHA-256 recorded |
| power file | timestamped rail voltage, current and energy samples; SHA-256 recorded |
| run manifest | run identifier, UTC start, placement, controller and coefficients, plant, sample period, load case, fault schedule, bitstream and firmware and image hashes, controller binary hash, tool versions, buffer overflow count, operator notes; schema-validated |

No run is reported without its manifest and hashes.

## Host analysis

A command-line tool validates the manifest and hashes, decodes events, computes the derived
intervals and their distributions (median, 95th, 99th and 99.9th percentile, maximum), the
deadline-miss rate, tracking error (RMS and peak), energy per cycle, fault detection and time to
safe state, and writes a JSON report, CSV tables and plots. Every statistic states its sample
count and run duration.

## Verification of the instrument

1. **Simulation** before hardware: witness, buffer, plant, monitor and fabric controller with a
   vendor-neutral simulator, directed and randomised tests, bit-exact parity of the fabric and C
   controllers.
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
| `capability-inventory.json` | generated from the manifest, embeds its SHA-256, empty at `architecture_only` |
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
