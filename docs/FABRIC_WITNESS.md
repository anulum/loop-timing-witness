<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — fabric witness RTL
-->

# Fabric witness RTL

`rtl/event_witness.sv` connects the timestamp capture to a dual-clock FIFO. This is a
simulation-tested stream component. Peripheral event arbitration, AXI/UIO access, coherent
processor status snapshots, physical clock constraints and board qualification remain planned.
The domain maturity is `architecture_only`; the capability inventory remains empty.

## Event input and record output

| Port | Clock domain | Contract |
|---|---|---|
| `event_valid`, `event_code[7:0]`, `cycle_number[31:0]` | capture | One tuple per rising edge when `capture_active` is high. No backpressure. |
| `capture_active` | capture | Local run reset has released. |
| `counter_ticks[63:0]` | capture | Free-running counter, cleared by run reset; record samples the pre-increment value. |
| `buffer_full` | capture | No new record can be accepted at the current write edge. |
| `event_dropped` | capture | High for each edge rejecting a pending captured record. Consecutive drops keep it high. |
| `overflowed` | capture | Sticky loss flag until run reset. |
| `overflow_count` | capture | Saturating count of rejected records; a lower bound after saturation. |
| `drain_request` | drain | Request the next record; empty requests do not advance the pointer. |
| `drain_valid`, `drain_record[127:0]` | drain | Registered result of the request at this rising edge; consume only when valid. |
| `drain_empty` | drain | No record currently visible to the read domain. |

A source tuple is captured at an edge, then offered to the FIFO at the next capture edge.
It retains the original timestamp even if it later crosses into the drain domain. The write
status and overflow pulse therefore refer to the pending captured record. The source must
supply event codes from `rtl/event_codes_pkg.sv` and the hash-bound domain snapshot. The host
rejects unknown codes, nonzero reserved fields, regressing ticks/cycles and duplicate events.
Arbitrate simultaneous source strobes before this input; this module cannot represent two
events at one capture edge. Clock crossing of asynchronous source strobes is also upstream.

The 128-bit output is `{timebase_ticks[63:0], cycle[31:0], 16'd0, 8'd0, event_code[7:0]}`.
Write its least significant byte first for the published 16-byte little-endian host format.
The record payload is unspecified when `drain_valid` is low, including during reset.

## Capacity and loss

### Shared-counter channels

`rtl/shared_event_witness.sv` gives independent event FIFOs one common 64-bit capture
counter. Each channel supplies its own pre-edge valid bit, eight-bit code and 32-bit
identity. Channel buses are flat: channel `i` occupies bits `i*width +: width`,
with widths 8 for code, 32 for identity, 64 for run counts and 128 for a record.
Simultaneous tuples receive the same pre-increment timestamp, with zero
reserved fields in the existing 128-bit record layout. Codes and identities are supplied
by the caller's declared profile; the instrument does not interpret a neural state or
encode it in reserved bits.

The shared capture reset and counter release together. Each registered tuple enters its
channel FIFO on the next capture edge. `attempt_count` counts those FIFO write attempts;
`accepted_count` counts accepted writes. A full channel drops its newest record and
updates its own sticky flag, drop pulse and saturating overflow count. Other channels
continue independently. Attempt and acceptance counts are 64-bit run counters; the
admitted run must end before their wrap. Capture-domain status needs a coherent snapshot
before crossing to a processor or drain clock domain.

`CHANNEL_COUNT` accepts 1 through 32; `ADDRESS_BITS` and `OVERFLOW_COUNTER_BITS` retain
the FIFO and single-channel witness limits. Every channel has its own drain request,
valid record and empty flag. An unused channel remains empty. Common reset flushes all
channels and clears the shared timebase and counts. Reset release, conservative FIFO
flags, physical CDC constraints and RAM qualification follow the same rules below.

The dedicated simulation exports simultaneous known-edge records, continuously captures
1,000 records plus two markers per channel at 1,024-record capacity before drain, and
exercises isolated full-buffer loss, saturation, an empty channel and queued-data reset.
These are instrument-port controls. Neural wrapper, complete export/report integration
and board qualification have separate acceptance requirements.

`ADDRESS_BITS` accepts 1 through 14; capacity is `2**ADDRESS_BITS`, with the default 16,384
records. The capture pipeline is not an extra accepted storage slot. A full FIFO preserves
stored records and drops the newest pending record. There is no attempt to stall measured
source activity. `OVERFLOW_COUNTER_BITS` accepts 1 through 32, default 32. Invalid parameter
values fail elaboration/simulation. Any loss invalidates the run, including after the buffer
recovers. The host manifest must record the final capture-domain count before run reset.

The machine-readable `event_fifo` contract declares the Gray-pointer implementation,
drop-newest policy, 32-bit counter and reset policy. The schema requires those policy fields
when the implementation is declared; the validator checks a supported power-of-two depth.
Earlier v1 domain snapshots without that implementation declaration retain their original
sizing contract, so archived hash-bound runs remain interpretable.

## Clock crossing and reset

`event_record_fifo.sv` uses binary pointers with an extra wrap bit, Gray-coded pointers,
two destination-clock synchroniser stages, registered full/empty flags and a dual-clock
128-bit memory. Full compares the next write Gray pointer to the synchronised read pointer
with its top two bits inverted. Empty compares the next read Gray pointer to the synchronised
write pointer. Synchronisation makes flags conservative: newly written data or newly freed
space becomes visible after destination-clock edges, rather than immediately. Synchroniser
registers carry `ASYNC_REG` attributes. This follows FIFO style 1 in Clifford E. Cummings,
[Simulation and Synthesis Techniques for Asynchronous FIFO Design, SNUG 2002](https://www.researchgate.net/publication/252160343_Simulation_and_Synthesis_Techniques_for_Asynchronous_FIFO_Design).

Both clocks share `run_reset_n`. Assertion is asynchronous; each `clock_reset_release.sv`
instance waits for two local rising edges before release. A stopped clock remains in reset.
Assertion flushes the run, clears the timebase and loss state and prevents old records from
becoming valid. RAM contents and the invalid read payload are not cleared, preserving memory
inference. Independent reset of one pointer domain is unsupported. Hold the common reset low
for the device's required minimum pulse width and meet reset-recovery/removal constraints.

Capturing and draining need no coherent shared clock. Reading capture-domain status from
processor logic does require a separate coherent CDC snapshot; synchronising each counter
bit separately is insufficient. Gray-bus skew/max-delay constraints, placement of synchroniser
stages and RAM inference must be supplied and reviewed in the vendor integration. RTL simulation
and generic synthesis do not establish metastability rates, timing closure or physical RAM fit.

## Verification

Run the dedicated public-port simulations and real host integration:

```bash
.venv/bin/pytest -q tests/test_clock_reset_release.py tests/test_event_record_fifo.py tests/test_event_witness.py
yosys -s rtl/check_witness_memory.ys
yosys -s rtl/check_witness_equivalence.ys
verilator --lint-only --Wall --top-module event_witness rtl/clock_reset_release.sv rtl/event_record_capture.sv rtl/event_record_fifo.sv rtl/event_witness.sv
```

The FIFO scoreboard exercises full capacity, requests at empty, four complete fill/drain
rounds, deterministic random traffic, faster/slower/equal clock rates, queued-data reset and
recovery. The witness scoreboard checks every accepted record and its original timestamp,
continuous events, 17 counted drops, small-width saturation, recovery and a fresh run. The
host tests bind the sources, compiled simulation and binary stream by SHA-256, check 5,000-tick
periods and 20-tick loop latency, and mark an actual overflow stream invalid. Those values are
test schedules, not board performance claims.

Generic synthesis must retain one 128-bit by 16,384 dual-clock memory at default capacity.
Post-optimisation equivalence uses a small FIFO configuration with memory mapping and
`async2sync` normalisation before comparing the prepared and synthesised designs. That proof
checks logic transformations under the normalised model; it does not prove physical CDC safety.
Board acceptance still requires the same-bitstream tests in
[`MEASUREMENT_PROTOCOL.md`](MEASUREMENT_PROTOCOL.md).

## Simultaneous control strobes

The one-event input remains the generic stream contract. The plant entry point instead uses
`control_event_capture.sv` to snapshot simultaneous strobes before serialization and feeds this
same dual-clock FIFO. Its group-queue and combined loss semantics are specified in
[`PLANT_WITNESS.md`](PLANT_WITNESS.md).
