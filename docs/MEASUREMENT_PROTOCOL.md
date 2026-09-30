<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — measurement protocol
-->

# Measurement protocol

This document fixes how measurements will be taken and reported. It contains no board results:
none exist, and no physical board is currently available. Functional controller simulation
is specified in [`CONTROLLERS.md`](CONTROLLERS.md); native CLI wall times are local regression
evidence, not processor placement measurements. The numeric parameters that the validator can check live in
`measurement-domain.json` under `design_contracts`; a change to either place must change both.
The implemented host file formats and calculations are specified in
[`HOST_ANALYSIS.md`](HOST_ANALYSIS.md), with the input structure in
[`run-manifest.schema.json`](../run-manifest.schema.json).

## Configuration space

One configuration is one combination of:

- controller placement: `linux_user_space`, `bare_metal_amp` or `fabric_logic`;
- load case: idle, CPU stress, memory and cache stress, network stress, storage stress;
- sample rate: from 100 Hz to 20 kHz, 1 kHz by default;
- controller (PID with anti-windup or discrete LQR) with its coefficients, and plant
  (second-order mechanical or first-order thermal) with its fixed-point format;
- fault schedule, empty for timing runs.

## Procedure

1. The board is powered from its own supply only. Room temperature is recorded.
2. The same bitstream serves every placement; the placement changes through a register only.
3. Each repeat starts after a reboot.
4. A fixed warm-up period is discarded; its length is recorded in the run manifest.
5. Each repeat runs 1 000 000 control cycles (about 17 minutes at 1 kHz).
6. Each configuration is repeated five times.
7. Every repeat writes its event file, power file, measurement-domain snapshot and run manifest
   with SHA-256 of each referenced file, the bitstream, firmware, operating-system images and
   controller binary, and the tool versions.
8. A repeat with any event-buffer overflow is invalid and is reported as invalid, not dropped.

The buffered RTL witness produces event files for host-tool verification through its actual
drain stream, including known-period and overflow simulations. Its drop-newest buffer retains
accepted records, latches overflow and counts drops with a saturating 32-bit counter. The count
is a lower bound after saturation, and `overflowed` remains set until common run reset. Record
status before reset: reset flushes both domains and clears all run counters. A processor logger
must implement a coherent capture-domain status snapshot before using it in a manifest; raw CDC
sampling is insufficient. RTL ports and reset timing are specified in
[`FABRIC_WITNESS.md`](FABRIC_WITNESS.md). Those runs declare
`source.kind: rtl_simulation` and remain simulation evidence even when the input series are
internally valid. A board run declares the source, all input and build artefact paths and their
SHA-256 values; the host checks the referenced bytes. The board acceptance flags in the run
manifest are operator declarations, not a replacement for the separate same-bitstream acceptance
records required below.

## Reporting

- Latency and jitter are reported as distributions — median, 95th, 99th and 99.9th percentile and
  maximum — per repeat and pooled, with the spread between repeats.
- Every statistic states its sample count and run duration. No single-run number is presented
  without its distribution.
- Deadline misses are reported as counts and rates from the hardware monitor.
- Control quality is the tracking error of the emulated plant, RMS and peak.
- Energy is reported as mean energy per control cycle over windows of many cycles, per rail and
  for the four rails together.
- Fault runs report detection latency and time to safe state per injected fault.
- The instrument floor from the bus-offset calibration is reported with every latency table.
- The host report retains the observation duration in timebase ticks and the contributing sample
  count for each metric. Missing tracking or power input is reported as unavailable, not filled
  with a simulation substitute.

## Native simulation observations

The native capture path binds the executed source snapshot, configuration, executable, original
event stream, raw tracking and completion metadata to the run manifest. It declares
`source.kind: rtl_simulation`; its reports remain `simulation_only`, with physical acceptance
flags false and no power series. These captures verify software and RTL behaviour; they do not
satisfy the board procedure or instrument acceptance below.
The frozen source includes the production Makefile and its included Spike plugin make fragment,
even when the selected target builds only the native simulator.

`tracking_sampling: observed` permits only the cycles actually read by the controller. Their
tracking rows must match the captured `SAMPLE_READ` cycles exactly. After warm-up exclusion,
the report states the expected cycle count, observed sample count, missing cycles and coverage
fraction. RMS and peak describe observed samples only. Incomplete coverage is `partial` and
invalidates the run; zero post-warm-up observations are `unavailable`. Neither missing samples
nor their errors are interpolated. Omitting this option or selecting `complete` retains the
complete-series contract in [`HOST_ANALYSIS.md`](HOST_ANALYSIS.md).

Optional hash-bound `native_metadata` preserves the final live miss, overflow, sample and record
counts and safe-state status. Without FIFO loss, those counts must agree with the complete
captured event stream. With loss, the report retains live counts separately: missing actuator
records cannot establish controller deadline misses, and the completion receipt cannot repair
lost events or make the run valid. Finalisation waits for the configured final deadline,
capture quiescence and receiver drain, including events after safe state first latches.

Dedicated-hart ISA capture uses a separate hash-bound `amp_capture` receipt, reconciled with
original firmware inputs, original pre-generation/pre-compilation plugin inputs and captured
native plugin build/source snapshot, raw observations
and actual logger completion. It declares
`bare_metal_amp` with `rtl_simulation`; neither parked companion harts nor the functional clock
map qualifies Linux coexistence or physical U54 latency. See [the AMP capture contract](AMP_SIMULATION.md).

Optional hash-bound `host_load` identifies the idle, CPU, memory/cache, private loopback UDP or
owned-file storage/fsync profile. Its worker interval must enclose the actual native interval;
policy readback and complete operation counters describe the whole worker interval. Host
monotonic time is separate from fabric event time. CPU affinity does not reserve a core,
loopback traffic does not establish NIC load, and fsync does not establish uncached storage
load. These receipts do not qualify board processor timing or energy.

The Linux PAC1934 journal retains raw accumulator attributes, units and individual host/fabric
read brackets. It is not a qualified `power.csv`: physical acquisition, rail calibration and
energy-window alignment remain unverified. The journal cannot substitute for the power series
required by the board procedure. Formats and validation are in
[`HOST_ANALYSIS.md`](HOST_ANALYSIS.md); register snapshots, reset custody and final drain are in
[`PLANT_WITNESS.md`](PLANT_WITNESS.md).

## Stated limits

These limits are part of every report:

- The PAC1934 rails do not separate processor cores from fabric: the core rail supplies both.
  Placement energy is whole-rail energy, not per-core energy.
- The power monitor samples far more slowly than a control cycle. Energy per cycle is a window
  mean, not a per-cycle measurement.
- Timestamps resolve 10 ns. Bus access inside the interconnect adds a fixed offset that is
  calibrated and reported.
- The plant is emulated. Results describe controller timing and its effect on the emulated plant,
  not a physical machine.
- A PREEMPT_RT comparison is included only if a matching kernel builds for the board support
  package.

## Acceptance of the instrument before any result

A result may be reported only after the instrument has passed, on the same bitstream, the
known-period test, the injected-delay test, the overflow test and the bus-offset calibration
described in [`ARCHITECTURE.md`](ARCHITECTURE.md). Their records are kept with the run records.

## Plant simulation prerequisite

[`PLANT_WITNESS.md`](PLANT_WITNESS.md) specifies the implemented Q8.24 models, reference
quantisation, strict deadline and safe-state priority, simultaneous event capture and fault
injection. `ACT_WRITE` denotes the first timely command; `ACT_LATE` is the first accepted
late command in its observation cycle and does not satisfy a deadline. Late-command counts
come from the hardware status counter, not the number of `ACT_LATE` records. Preserve clipping
flags with sample output and include all coefficient values in source/configuration provenance.
The injected-delay simulation checks an exact k-period fabric delay; processor execution,
power-monitor energy and physical safe-state behaviour need separate board acceptance.
