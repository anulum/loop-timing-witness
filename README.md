<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — README
-->

# Loop Timing Witness

An open measurement instrument, in design, that timestamps the events of a real-time control
loop in FPGA fabric and reports latency, jitter, deadline misses, fault response and energy per
control cycle on a PolarFire SoC board — independently of the processor whose software is being
measured.

**Evidence maturity: `architecture_only`.** No board instrument has been built or measured. The
repository contains measurement contracts, fabric timestamp capture and a dual-clock buffer
tested in RTL simulation, and a host analysis command that reports simulation provenance separately from
board evidence. The capability and claim inventories remain empty and checked by the manifest
validator.

## The measurement problem

Real-time control on embedded systems-on-chip is usually characterised by software that times
itself on the processor under test: a timer wake-up benchmark, or timestamps logged by the
control task. Those numbers share clock, scheduler and interrupts with the system being
measured, often describe a proxy task rather than the control loop, and rarely come with energy
per cycle or with the effect of latency on control quality. Moving a controller between a Linux
task, a bare-metal core and FPGA logic therefore changes the measurement method along with the
placement.

## What the instrument is designed to do

For one closed control loop on one PolarFire SoC Icicle Kit, the planned instrument:

1. timestamps every sample-ready, sample-read, actuator-write and deadline event in FPGA fabric
   on a 64-bit counter clocked at 100 MHz (10 ns resolution);
2. reports latency and jitter as distributions (median, 95th, 99th and 99.9th percentile,
   maximum) and counts deadline misses in hardware;
3. compares three controller placements under identical plant and controller definitions: Linux
   user space on the U54 application cores, a bare-metal loop on one U54 core in asymmetric
   multiprocessing, and fixed-point logic in fabric;
4. relates latency to the tracking error of an emulated plant in the same run;
5. estimates energy per control cycle from the board's PAC1934 power monitor, with the limits
   stated in [`docs/MEASUREMENT_PROTOCOL.md`](docs/MEASUREMENT_PROTOCOL.md);
6. injects faults and measures detection and time to a defined safe actuator state;
7. writes every run as raw event records plus a hashed manifest, so a run can be repeated and
   audited.

A second event profile, `COMPUTE`, applies the same event witness to fabric accelerators: input
write, compute start, compute done, output read and interrupt entry.

## Who it is for

Engineers and researchers who must show measured loop timing instead of estimates: motor,
power-electronics and motion control, laboratory hardware-in-the-loop set-ups, and teams that
place computation in FPGA fabric and need its end-to-end latency on real hardware.

## Evidence boundary and non-claims

- No latency, jitter, deadline, energy or control-quality number has been measured.
- No statement about PolarFire SoC performance is made before a measured run with its manifest
  and hashes exists.
- No comparison with other vendors or platforms is part of the project.
- The target board has not been used yet; the platform facts in the manifest come from the board
  user guide and are marked `verified_on_hardware: false`.
- Hardware timing measurement from FPGA fabric is established prior work (see below). The
  planned contribution is its application to complete control-loop events across three
  placements with control quality, energy and fault response in the same run, published as
  reproducible run records — not the idea of measuring from fabric.

## Related work

- Alonso et al., "Interrupt Latency Accurate Measurement in Multiprocessing Embedded Systems by
  Means of a Dedicated Circuit", *Electronics* 13(9), 1626, 2024,
  <https://doi.org/10.3390/electronics13091626> — a fabric circuit that measures the latency
  between two interrupt signals with one clock-cycle resolution and compares hypervisor and
  asymmetric-multiprocessing configurations on Zynq UltraScale+.
- Microchip Technology, "PolarFire SoC FPGA: Interrupt Latency and Data Transfer Throughput
  Measurements", white paper DS60001712B, 2021 — processor-side interrupt latency on the Icicle
  Kit measured with the RISC-V cycle counter.
- Puglisi et al., "Comparative evaluation of embedded platforms for real-time acquisition in
  plasma control and data acquisition systems", *Fusion Engineering and Design* 228, 115769, 2026,
  <https://doi.org/10.1016/j.fusengdes.2026.115769> — bare-metal, FreeRTOS, Linux and FPGA
  placements of one acquisition loop, timed by server-side packet timestamps and an oscilloscope.

## Relation to SC-NeuroCore

Loop Timing Witness is developed as hardware-validation tooling for
[SC-NeuroCore](https://github.com/anulum/sc-neurocore), an open neuromorphic computing library.
The `COMPUTE` profile is designed to measure the memory-mapped write, compute, read and interrupt
path that fabric neuron peripherals use. No SC-NeuroCore code, model or adapter is part of this
repository: adapters that place such peripherals in the instrument's device-under-test slot
belong to the SC-NeuroCore repository and consume this repository's published manifest format and
interface. No SC-NeuroCore latency or energy on PolarFire SoC has been measured.

## Explicit exclusions

- SC-NeuroCore source code, generated neuron peripherals, models or adapters.
- Controllers, plant models or physics from other projects; only textbook PID and discrete LQR
  controllers are in scope.
- Microchip Libero SoC binaries, licensed or encrypted IP cores and redistributed vendor
  reference designs; they are generated by scripts or fetched at a pinned revision.
- Measurement results, datasets and benchmark numbers until a measured run exists.

## Architecture

The instrument architecture, event record format and verification plan are described in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). The repository boundary is fixed by
[`docs/adr/0001-repository-boundary.md`](docs/adr/0001-repository-boundary.md), the measurement
procedure and its stated limits by [`docs/MEASUREMENT_PROTOCOL.md`](docs/MEASUREMENT_PROTOCOL.md),
and the threat model by [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md). The implemented simulation
and host file contract is in [`docs/HOST_ANALYSIS.md`](docs/HOST_ANALYSIS.md).

The [system block diagram](docs/contest/Loop_Timing_Witness_System_Block_Diagram.pdf)
illustrates the proposed PolarFire SoC Icicle Kit design for the 2026 contest.

The planned contracts are machine-readable in [`measurement-domain.json`](measurement-domain.json)
(schema [`measurement-domain.schema.json`](measurement-domain.schema.json)): timebase, event
record layout, event profiles and the intervals derived from them, event buffer sizing, controller
placements and the run plan. Each run manifest binds a snapshot of this file by SHA-256. The
validator checks their internal consistency, for example that
the event buffer outlasts the slowest permitted drain at the highest sample rate and that the
timebase counter cannot wrap during a repeat.

The RTL stream contract is described in [`docs/FABRIC_WITNESS.md`](docs/FABRIC_WITNESS.md).

## Repository layout

| Path | Content |
|---|---|
| `measurement-domain.json`, `measurement-domain.schema.json` | identity, boundary and planned measurement contracts |
| `run-manifest.schema.json` | versioned, provenance-bound run input contract |
| `capability-inventory.json` | generated public inventory, empty at `architecture_only` |
| `development-dependency-licences.json` | reviewed licence of every pinned development tool |
| `docs/` | architecture, measurement protocol, threat model, decision records |
| `papers/` | manuscript collection; no manuscript exists yet |
| `rtl/` | synthesizable timestamp capture, dual-clock buffer, reset release and event codes |
| `tools/` | host analysis, validators, inventory generator, repository guards and preflight runner |
| `tests/` | command-line, file and RTL-simulation tests |
| `.github/` | workflow definitions, workflow inventory and contribution metadata |

## Validation

Every gate and its exact scope are listed in [`VALIDATION.md`](VALIDATION.md). From a clean
checkout with Python 3.13:

```bash
make venv        # .venv from the hashed development lock
make preflight   # every local gate, failing closed on a missing tool
```

## Security

Report vulnerabilities privately as described in [`SECURITY.md`](SECURITY.md).

## Licence

AGPL-3.0-or-later, with a commercial licence available; see [`NOTICE.md`](NOTICE.md) and
[`LICENSES/`](LICENSES/). Licensing metadata follows REUSE 3.x ([`REUSE.toml`](REUSE.toml)).

## Citation

Citation metadata is in [`CITATION.cff`](CITATION.cff). No release, version or DOI exists yet;
cite the commit you inspected.
