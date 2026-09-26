<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — host analysis contract
-->

# Host analysis contract

`tools/analyze_run.py` accepts one versioned run manifest and writes a report directory. The
event-capture RTL and its testbench produce binary input in simulation. No board measurement or
instrument acceptance has been performed; a simulation report has `evidence_status:
simulation_only` and cannot be cited as a PolarFire SoC result.

```bash
.venv/bin/python tools/analyze_run.py path/to/manifest.json --output-dir path/to/new-report
```

The output directory must not exist. The tool validates the JSON and every referenced SHA-256,
decodes the binary events, analyses the series, writes all outputs to a sibling temporary
directory and renames it into place only after every write succeeds. An invalid run can still
produce a report: `valid: false` and `invalid_reasons` retain the reason. Malformed inputs fail
without a report. The source and hardware artefacts are checked as files, not accepted merely as
hash strings. The tool accepts relative paths within the run directory only.

## Inputs

[`run-manifest.schema.json`](../run-manifest.schema.json) is the Draft 2020-12 schema for
`loop-timing-witness.run-manifest.v1`. The manifest declares the UTC start, source kind and tool,
profile, placement, controller coefficients, plant and fixed-point format, sample period, run
length and warm-up, load case, fault schedule, file paths and SHA-256 values, instrument state and
operator notes. It includes a hash-bound copy of `measurement-domain.json` in the run directory;
the host interprets event codes, rails and interval definitions from that verified copy. A board
declaration additionally requires the hashed bitstream, firmware, Linux image and controller
binary files, complete tracking and power files, an instrument floor, four
acceptance flags, room temperature and board-only supply. Those declarations cannot substitute
for actual board acceptance records; independent board qualification remains a separate gate.
A report from such a declaration is labelled `board_declaration_unverified` until external
qualification verifies the board evidence.

The 16-byte event record is little-endian: `event_type` u8, zero reserved byte u8, zero reserved
word u16, `cycle` u32 and `timebase_ticks` u64. The repository
[`measurement-domain.json`](../measurement-domain.json) defines the current event codes and
intervals; each run keeps its own verified snapshot. The decoder refuses partial records,
nonzero reserved fields, unknown or wrong-profile codes, events outside the declared
cycle range, non-monotonic cycle or tick order, and duplicate event kinds in one cycle. Its
capture-module source and Icarus simulation testbench are under [`rtl/`](../rtl/) and
[`tests/rtl/`](../tests/rtl/).

The optional tracking CSV has the exact header `cycle,reference,output` and one finite decimal
observation per analysed control cycle. `reference` and `output` have the unit named by
`plant.tracking_unit`. The optional power CSV has the exact header
`timebase_ticks,rail,voltage_v,current_a,energy_j`; energy is a cumulative joule counter, and all
four rails from the measurement-domain contract must occur at each fabric tick. Voltage, current
and energy are finite and nonnegative. The run manifest may declare either auxiliary file as
`null` for an incomplete simulation run. A board run requires both files. Missing data remains
`unavailable` in the report; it is never substituted.

## Calculations

Same-cycle event intervals are differences of captured fabric ticks. For `CONTROL`, a deadline
is missed when no `ACT_WRITE` precedes that cycle's `DEADLINE`; a write at the deadline is late.
Fault-detection latency is `FAULT_DETECTED − FAULT_INJECTED`. Time to safe state is measured from
the first consecutive missed deadline to `SAFE_STATE`. A fault schedule must match the captured
injection cycles. The event file is invalid for a complete run if a cycle anchor is absent or
the FIFO overflow count is nonzero.

For every interval the tool reports the sample count, observation duration in ticks, median,
p95, p99, p99.9 and maximum. Percentiles use linear interpolation at position `(n − 1) × p` in
the sorted samples. Control error is the RMS and peak absolute value of `reference − output`
after warm-up. Power uses differences of the four cumulative rail counters between consecutive
fabric-tick samples. It divides the sum by the count of cycle anchors in those windows, reporting
mean joules per cycle per rail and total, plus window and cycle counts. It makes no instantaneous
per-cycle energy claim. A power series that does not cover every analysed cycle is refused. When
warm-up cycles are discarded, the first contributing power window must start at or after the
first analysed cycle; a window spanning warm-up and analysed cycles is refused.

Every report carries the run's source kind, input hashes, timebase resolution, instrument floor,
sample counts, observation duration and stated limits. The current `valid` flag means the input
series are complete and have no declared overflow; `simulation_only` remains simulation even when
`valid` is true. Physical instrument acceptance and public measured claims require the separate
hardware gates in [`MEASUREMENT_PROTOCOL.md`](MEASUREMENT_PROTOCOL.md).

## Outputs

| File | Content |
|---|---|
| `report.json` | Canonical JSON summary with evidence status, validity, metrics and limits |
| `interval_summary.csv` | One row per interval with count, distribution and duration |
| `cycle_intervals.csv` | Individual same-cycle intervals for audit and independent recalculation |
| `interval_p99.svg` | Labelled p99 comparison of available event intervals |
| `energy_per_cycle.svg` | Rail comparison when a complete power series exists |

Each CSV row and SVG title carries the evidence status, so a detached simulation artefact retains
its provenance. The SVG charts are visual summaries. The JSON and CSV carry numeric results.
