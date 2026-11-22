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
9. The repeats of one configuration are listed in a repeat campaign manifest
   ([`repeat-campaign.schema.json`](../repeat-campaign.schema.json)). It numbers the repeats
   from 1, binds each run manifest by path and SHA-256 and records whether the board rebooted
   before the repeat. Runs whose configuration differs are refused as one campaign. The
   campaign report compares the repeats with the measurement-domain run plan; the contract is
   specified in [host analysis](HOST_ANALYSIS.md#repeat-campaigns).

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
  Pooled distributions are computed from the concatenated raw samples of valid repeats, never
  by averaging percentiles; adjacent-cycle jitter pairs never span two repeats. The spread
  between repeats is the minimum, maximum and range of each per-repeat statistic. Invalid and
  refused repeats stay listed with their reasons and contribute no samples.
- Every statistic states its sample count and run duration. No single-run number is presented
  without its distribution.
- Per-run latency jitter means the absolute change in the same periodic event interval
  between adjacent post-warm-up cycles. Both intervals must be complete; missing cycles
  are never bridged. Pair counts, expected pairs and missing-pair coverage accompany the
  distribution, with peak-to-peak latency spread reported separately. Fault and safe-state
  intervals remain latency-only. The exact definition, null/zero semantics and auditable
  pair outputs are specified in [host analysis](HOST_ANALYSIS.md#latency-jitter).
  This derived software metric changes no capture or input-manifest parameter; pooled
  repeats and physical jitter qualification still require their separate campaign evidence.
- Deadline misses are reported as counts and rates from the hardware monitor.
- Control quality is the tracking error of the emulated plant, RMS and peak.
- Energy is reported as mean energy per control cycle over windows of many cycles, per rail and
  for the four rails together; the report names the method `window_mean`. The marginal energy per
  cycle comes from a loop-frequency sweep, described under [Energy](#energy).
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
The run also binds `producer_context.json` and the actual parent project package,
packaged contracts and loaded tools. The context records source origins and hashes,
interpreter, platform and dependency versions. Source or context drift during
capture refuses producer acceptance while retaining the original native artifacts.

`tracking_sampling: observed` permits only the cycles actually read by the controller. Their
tracking rows must match the captured `SAMPLE_READ` cycles exactly. After warm-up exclusion,
the report states the expected cycle count, observed sample count, missing cycles and coverage
fraction. RMS and peak describe observed samples only. Incomplete coverage is `partial` and
invalidates the run; zero post-warm-up observations are `unavailable`. Neither missing samples
nor their errors are interpolated. Omitting this option or selecting `complete` retains the
complete-series contract in [`HOST_ANALYSIS.md`](HOST_ANALYSIS.md).

Optional hash-bound `native_metadata` preserves the final live miss, overflow, sample and record
counts and safe-state status. Its fault kind, cycle and delay duration must agree with
the declared schedule even when the metadata and manifest hashes are updated together.
Without FIFO loss, those counts must agree with the complete
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

## Energy

The Icicle Kit's PAC1934T-I/JQ measures four rails: VDD, VDD25, VDDA25 and VDDA
([Icicle Kit User Guide DS60001679E](https://www.microchip.com/en-us/development-tool/mpfs-icicle-kit-es),
section 3.7). Its configured sample rate (8, 64, 256 or 1024 samples/s) is part of the
hash-bound power configuration and of every row of the acquisition journal
([host analysis](HOST_ANALYSIS.md#native-pac1934-acquisition-journal)).

**Window mean.** A run's energy per cycle is each rail's cumulative-energy increase over the
sampler windows that hold analysed cycles, divided by those cycles: `E = ΔE_rail / N`. It is a
mean over many cycles at one cycle rate, not a per-cycle measurement, and it includes the rail's
static power: at mean rail power `P` and cycle rate `f`, `E = P / f`.

**Marginal energy per cycle.** Runs of one placement and one controller at three or more cycle
rates, at one temperature, give the mean power `P(f) = E(f)·f` of each rail. The least-squares line
`P = P0 + E_dyn·f` separates the static power `P0` from `E_dyn`, the energy each additional cycle
costs. `loop_timing_witness.energy_sweep` fits it from the run reports and a declaration of each
run's cycle rate and temperature, with standard errors and `r²`; it refuses runs of different
placements, reports without a valid window-mean energy, fewer than three distinct rates and
temperatures that spread beyond the declared tolerance, because static power depends on
temperature. The line assumes static power independent of the cycle rate; its residual and `r²`
show how well that holds. The core rail supplies both processors and fabric, so `E_dyn` belongs to
the whole rail, not to a core.

```bash
.venv/bin/python -m loop_timing_witness.energy_sweep sweep.json
```

## Uncertainty budget

The budget follows the [Guide to the expression of uncertainty in measurement](https://doi.org/10.59161/JCGM100-2008E)
(GUM): each component is a standard uncertainty, a bounded component of half-width `a` with no
preferred value inside the bound counts as rectangular (`a/√3`), and independent components
combine in quadrature. `T` is the capture period, 10 ns. Board values marked as measured come from
the acceptance tests and are reported with every result; no board has been measured yet.

**Timebase scale.** The 64-bit counter runs on the 100 MHz capture clock that `WITNESS_CCC` derives
from the Icicle Kit's 50 MHz fabric reference oscillator X5, a DSC1001DL5-050.0000
([Icicle Kit User Guide DS60001679E](https://www.microchip.com/en-us/development-tool/mpfs-icicle-kit-es),
section 3.13). Its frequency tolerance is ±10 ppm, including initial tolerance, temperature and
supply voltage, and its aging ±5 ppm in the first year at +25 °C
([DSC1001/3/4 data sheet DS20005529F](https://www.microchip.com/en-us/product/dsc1001), Table 1-1). A
locked PLL output keeps the reference's relative error, so an interval `L` read from the counter has
a scale error of at most 15 ppm in the first year: `u = 15·10⁻⁶ · L / √3`, 0.09 ns for 10 µs and
8.7 ns for 1 ms. The error is common to every interval of one board, so comparisons between
controller placements on the same board share it.

**Event phase.** Events raised in the capture domain (`SAMPLE_READY`, `DEADLINE`, `SAFE_STATE`) fall on
capture edges and carry no phase error. A processor access reaches the capture domain through
[`clock_request_bridge.sv`](../rtl/clock_request_bridge.sv), whose request toggle passes two capture
synchroniser stages: the recorded `SAMPLE_READ` or `ACT_WRITE` follows the bus edge of the access by a
fixed number of capture periods, which the bus offset contains, plus the time to the next capture
edge, between 0 and `T`. That phase gives `u = T/√12 = 2.9 ns` for an interval with one processor
end, and `T/√6 = 4.1 ns` for an interval between two processor accesses (independent phases).

**Bus offset.** The fixed part of each access path is the instrument floor: the bus-offset
calibration measures it with the fabric placement and reports it with every latency table. Its
standard uncertainty is the standard error of the calibration mean (measured).

**Oscillator jitter.** The oscillator's period jitter is at most 15 ps RMS (DS20005529F, 1.8 V,
100 MHz, measured over 50,000 cycles), three orders of magnitude below `T`; the capture PLL adds its
own jitter. Over long intervals the accumulated phase error is bounded by the scale term above. The
known-period test on the board, which requires a period from the same timebase to appear as an
exact interval, is the check that jitter and the PLL do not move edges by a capture period.

**Combined.** For the controller's service interval (`SAMPLE_READ` to `ACT_WRITE`), both ends are
processor accesses: `u_c = √((T/√6)² + u_scale² + u_offset²)`, 4.3 ns for a 100 µs interval with the
offset known to 1 ns, and 4.1 ns for short intervals with a negligible offset term. For `SAMPLE_READY` to `ACT_WRITE` (input
to actuation): `u_c = √((T/√12)² + u_scale² + u_offset²)`. The witness records when an access reaches
the fabric, not when the processor executes the instruction behind it.

### Pulse-per-second reference

A pulse-per-second source on the [reference input](../hardware/icicle/README.md#event-mirror-pins)
measures the timebase scale instead of bounding it. The witness timestamps each rising edge on the
64-bit counter after two synchroniser stages, a fixed latency of two capture periods plus the
edge's phase to the next capture edge, and the host analysis fits the counter against the edges'
whole seconds, taken from the counter so that a pulse the source skipped is not one second, with
edges off a whole second rejected ([`reference_timebase`](HOST_ANALYSIS.md#pulse-per-second-reference-timebase)).
The fixed latency cancels in the slope; the phase, between 0 and `T` for each edge and independent
between edges, enters the residuals and so the fit's standard uncertainty `u_fit` (in ppm), together
with the source's own edge jitter; `u_fit` never falls below that phase's quantization variance of
`T²/12` per edge. The scale error `δ` that the fit reports then corrects intervals,
`L = n·T / (1 + δ·10⁻⁶)`, and the scale term becomes `u_scale = L·10⁻⁶·√(u_fit² + u_ref²)`, where
`u_ref` is the standard uncertainty of the source's frequency over the run, in ppm, taken from its
declaration: a disciplined source with a stated bound `a` gives `a/√3`. Nothing in the witness
measures `u_ref`, so a result that uses the correction states the source and its declaration. The
fit holds for the run's duration only; it does not describe the oscillator at another temperature or
age. The input is a 3.3 V LVCMOS pin, so a source with another output level needs a level
translator, and an edge that arrives while the previous one still waits for a write slot is missing
from the sequence, which the report counts.

## Stated limits

These limits are part of every report:

- The PAC1934 rails do not separate processor cores from fabric: the core rail supplies both.
  Placement energy is whole-rail energy, not per-core energy.
- The power monitor samples far more slowly than a control cycle. Energy per cycle is a window
  mean, not a per-cycle measurement.
- Timestamps resolve 10 ns. Bus access inside the interconnect adds a fixed offset that is
  calibrated and reported. The [uncertainty budget](#uncertainty-budget) gives the standard
  uncertainty of each interval kind.
- The plant is emulated. Results describe controller timing and its effect on the emulated plant,
  not a physical machine. The events mark the digital boundary of the loop: sensor conversion,
  analog conditioning and actuator delays of a physical plant are outside every measured interval.
- A PREEMPT_RT comparison is included only if a matching kernel builds for the board support
  package.

## Acceptance of the instrument before any result

A result may be reported only after the instrument has passed, on the same bitstream, the
known-period test, the injected-delay test, the overflow test, the bus-offset calibration
described in [`ARCHITECTURE.md`](ARCHITECTURE.md) and the external cross-check below. Their records
are kept with the run records.

### External cross-check

The first four tests run on the witness's own timebase, so a fault shared by the counter and the
tests could pass them all. The cross-check measures the same run with an independent instrument:
a time tagger, or a logic analyser that timestamps edges, with a calibrated timebase of its own,
records the three [event mirror pins](../hardware/icicle/README.md#event-mirror-pins) while the
witness records the run.

The sample-ready and actuator-write pins toggle on the capture edge that records each
`SAMPLE_READY` and `ACT_WRITE`, and the safe-state pin rises on the edge that records `SAFE_STATE`.
The k-th edge of a toggling pin therefore belongs to the k-th record of its event, counted from the
release of the run reset, which clears all three pins; an edge that a later reset makes is not
compared. The cross-check requires as many pin edges as records, and for each compared pair of
records (successive `SAMPLE_READY`, giving the sample period; `SAMPLE_READY` to the following
`ACT_WRITE`, giving input to actuation; the first `SAMPLE_READY` to `SAFE_STATE`) it compares the witness interval `L_w = n·T` with the tagger interval `L_t` between
the corresponding pin edges:

`|L_w − L_t| ≤ (ε_w + ε_t)·L + s + 2r`

`ε_w` is the witness timebase bound, 15·10⁻⁶ (see the [uncertainty budget](#uncertainty-budget)),
`ε_t` the tagger's timebase bound, `r` the tagger's timing error bound for one edge, and `s` the
skew between the two pins: zero for edges of one pin, apart from the difference between rising and
falling output delays, and otherwise the spread of the pins' clock-to-output delays in the timing
report plus the difference of the board and cable paths and of the tagger's channels, which the
operator measures and declares. Capture-domain events fall on capture edges, so no `T` term
enters: a disagreement larger than the bound is a witness defect, such as a lost or added count.
A tagger with a smaller `ε_t` also measures the witness scale: the slope of `L_t` against `L_w` over
the run, reported with its standard error, may then replace the oscillator bound in the budget.
`ACT_WRITE` is recorded, and mirrored, on the capture edge after its two synchroniser stages, so
the cross-check covers the timebase and the capture path; the bus path before it is the
bus-offset calibration's.

## Plant simulation prerequisite

[`PLANT_WITNESS.md`](PLANT_WITNESS.md) specifies the implemented Q8.24 models, reference
quantisation, strict deadline and safe-state priority, simultaneous event capture and fault
injection. `ACT_WRITE` denotes the first timely command; `ACT_LATE` is the first accepted
late command in its observation cycle and does not satisfy a deadline. Late-command counts
come from the hardware status counter, not the number of `ACT_LATE` records. Preserve clipping
flags with sample output and include all coefficient values in source/configuration provenance.
The injected-delay simulation checks an exact k-period fabric delay; processor execution,
power-monitor energy and physical safe-state behaviour need separate board acceptance.
