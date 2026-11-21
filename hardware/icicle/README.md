<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — Icicle reference derivation
-->

# Icicle reference input

The reference source is fetched separately and is never committed here. Use an official
`polarfire-soc/icicle-kit-reference-design` checkout at commit
`9c34320f91e8e8a144c7d87bf299527fc5f02081`. The derivation command requires that
checkout to be clean and verifies the three vendor source files it changes by SHA-256.
It also verifies a path-and-content digest of every reference source file outside Git
metadata, including the timing constraints and MSS configuration. It writes a new output
tree on the repository's filesystem and refuses an existing path.
The requested output path must not be a symlink, including a dangling one;
derivation never follows an output alias to create a tree elsewhere.

```bash
hardware/icicle/derive_reference.sh /path/to/clean/icicle-kit-reference-design /path/to/new/icicle-witness-derived
```

The source-derivation integration test uses this public command, checks the produced
manifest and RTL snapshot, and exercises the pre-Libero refusal paths. It fetches the
exact reference commit when `WITNESS_ICICLE_REFERENCE` is unset. To reuse an existing
clean checkout and keep test output on the repository's filesystem, run:

```bash
WITNESS_ICICLE_REFERENCE=/path/to/clean/icicle-kit-reference-design \
  .venv/bin/pytest -q tests/test_icicle_reference_derivation.py \
  --basetemp=/path/to/new/icicle-derivation-pytest
```

The integration test also changes test-owned staging bytes at the actual filesystem
read boundaries for edited vendor files, copied RTL and the unmodified reference remainder.
Each change must abort publication. A separate filesystem race creates the requested
destination immediately before publication; derivation must preserve that competing tree.

The derived tree contains the official reference plus narrowly changed vendor sources, this
repository's [`LOOP_TIMING_WITNESS.tcl`](LOOP_TIMING_WITNESS.tcl) and
[`LOOP_TIMING_WITNESS.pdc`](LOOP_TIMING_WITNESS.pdc), and `witness_derivation.json`. It also contains `witness_rtl/`, an exact copy of the current
production SystemVerilog sources. The manifest hashes the derived vendor files, the connection
script, the pin constraints and each copied RTL source. Libero imports this snapshot so later repository edits
cannot silently change an already-derived design. Keep the source repository and its licence
with the derived tree; the manifest is provenance for source preparation, not a Libero result.
The pre-Libero verifier also checks the complete unmodified reference-file inventory against
the pinned commit and rejects extra files; changes to a constraint or MSS input cannot pass
through merely because the two edited Tcl files still match.
It rejects repeated JSON member names in the derivation manifest, including a repeated
member whose final value matches the expected receipt.
The witness connection requires the derived RTL snapshot and the reference Linux baseline;
optional reference variants are refused because their changes to the MSS, clock or FIC0
integration have not been qualified with this witness.

Microchip's [software downloads](https://www.microchip.com/en-us/products/fpgas-and-plds/fpga-and-soc-design-tools/fpga-software-downloads)
offer Linux web and full installers for Libero 2026.1, with SHA-256 checksums. Verify the
completed installer against the checksum listed for the exact Linux package. Microchip's
[Linux installation guide](https://www.microchip.com/content/dam/mchp/documents/FPGA/swdocs/libero/Libero_SoC_Design_Suite_Software_Installation_Guide_2025_1.pdf)
states that the installer defaults its cache to `/tmp`. Before launching the extracted
installer, create separate cache and temporary directories on a disk with room for the suite
and its generated projects, set `TMPDIR` to the temporary directory, and pass `--cache-path`
with the existing cache directory. Select an installation destination on that disk; the
installer's unattended form names it with `--root`. These options are documented for the 2025.1
installer; inspect the selected 2026.1 package's own help before reusing their spelling.

After confirming the board's silicon marking and installing a compatible Libero release,
use the verified runner. It refuses any stale manifest or source snapshot and an existing
generated project. A confirmed production-device invocation has this form:

```bash
hardware/icicle/run_reference.sh /path/to/new/icicle-witness-derived /path/to/libero MPFS250T
```

Select `MPFS250T_ES` only for a confirmed engineering-silicon device; the runner omits
the production-device script argument in that case, matching the official reference.
For either variant, the runner requests the reference script's `VERIFY_TIMING` flow,
which runs synthesis, place-and-route and timing verification. A completed Libero run
and inspected reports are required before claiming timing closure.
The source keeps the reference's Linux MSS configuration, so processor I²C remains
available for PAC1934 access. No I²C loopback variant is selected.

The derivation changes two vendor Tcl files and the reference clock constraints. The
reference script sources the witness script once the base design has generated, and FIC0's
interconnect gains target slot 2, ending at `0x60021fff`. In
`script_support/constraints/fic_clocks.sdc`, the FIC0 clock group also holds the witness
capture clock, so the paths between the two clocks are analysed instead of being cut as
asynchronous, and two appended `set_max_delay 8` lines bound every path between them, in each
direction, by the 8 ns FIC0 period. That bound covers each crossing: the capture clock
registers handshake-held request data one period after first sampling its request toggle,
the bus clock reads the held response two edges after its acknowledge toggle, a Gray
pointer's bits keep their skew below one source period, and synchroniser inputs and FIFO
RAM reads have no tighter requirement. Two `set_min_delay -8` lines release the hold check that the
shared group would derive from the two clocks' phases; hold has no meaning between them, and
the synchronisers resolve metastability. Both clocks stay asynchronous to every other clock,
as before.
The witness script adds the rest to the generated design:

- the witness HDL core as an AXI4 target on FIC0 slot 2, with the reference FIC0's 38-bit
  address and 32-bit data, covering the 8 KiB AXI4-Lite aperture of register map version 2:
  the run page at `0x60020000` and the fault page at `0x60021000`
  ([plant witness](../../docs/PLANT_WITNESS.md#register-pages));
- MSS fabric-to-processor interrupt bit 11 for the retained witness interrupt, split out of
  the range 11–58 that the reference ties low;
- a separate CCC, `WITNESS_CCC`, that derives the 100 MHz capture clock from the 50 MHz
  reference clock. The reference CCC uses all four PLL0 outputs (125, 125, 125 and 50 MHz)
  and does not instantiate PLL1, so no reference output is free for the witness. Its lock
  output reaches the witness, which holds both of its clock domains in reset until that PLL
  locks and returns to reset if the lock drops;
- the three [event mirror pins](#event-mirror-pins) as top-level outputs. The script imports
  their constraints and replaces the place-and-route constraint association, which the
  reference has already made for its baseline configuration, by the same list with the
  witness pins added.

Each change runs after the base design has generated with every input connected, because
SmartDesign refuses an unconnected input when it generates a component. The reference's
own bus interfaces differ in data and ID widths, and the reference project downgrades those
design-rule findings to warnings; the derivation keeps that setting, and the witness
target's widths are checked from the generation messages instead.

Libero SoC 2026.1 generates this project for MPFS250T. Its core generators need a display:
on a host without one, pass a wrapper that runs Libero under `xvfb-run` as the runner's
Libero executable. A host without internet access sets Libero's vault to the MegaVault of
the release (`change_vault_location`); it holds every core the reference requests. The
original board support package must establish the interrupt's PLIC and device-tree identity
before a processor may consume it. Source derivation and RTL simulation do not qualify a
board.

## Event mirror pins

The witness drives three capture-clock registers to device pins for the
[external cross-check](../../docs/MEASUREMENT_PROTOCOL.md#external-cross-check) with a time
tagger. The sample-ready and actuator-write pins toggle on the capture edge that records each
`SAMPLE_READY` and `ACT_WRITE` event; the safe-state pin rises on the edge that records
`SAFE_STATE` and stays high while the safe state is latched. A run reset clears all three. A
fourth pin takes the [pulse-per-second reference](../../docs/PLANT_WITNESS.md#pulse-per-second-reference)
into the witness.

| Signal | Top-level port | Ball | Board net | Connector |
| --- | --- | --- | --- | --- |
| Sample ready, toggle | `WITNESS_SAMPLE_READY` | A6 | `RPi_GPIO4_GCLK` | J26 pin 7 |
| Actuator write, toggle | `WITNESS_ACT_WRITE` | D8 | `RPI_GPIO6` | J26 pin 31 |
| Safe state, level | `WITNESS_SAFE_STATE` | C15 | `PF_C15` | J12 |
| Pulse per second, input | `WITNESS_PPS` | C14 | `PF_C14` | J13 |

The balls and nets come from the Icicle Kit schematic (bank 1 and Raspberry Pi connector sheets
of the engineering-sample board). Its bank 1 ball assignments agree with every ball that the
reference's `ICICLE_RPi.pdc` and `ICICLE_MIKROBUS.pdc` place on the same nets. No constraint
of the reference's baseline configuration uses the four balls; J26 is the Raspberry Pi
connector, and J12 and J13 are single-pin connectors on nets `PF_C15` and `PF_C14`, which the
schematic routes as a pair. These two balls are the device's live probe pins `LPRB_B` and
`LPRB_A`: the reference reserves them for SmartDebug live probes, and the first Libero run of
the derivation refused both as user-reserved pins, so the witness script releases them
(`RESTRICTPROBEPINS:0`) and the derived design offers no live probe. On the Raspberry Pi
connector every other GPIO is already constrained by the reference. The mirrors
are LVCMOS33 outputs and the reference input an LVCMOS33 input with a weak pull-down, as the
reference's mikroBUS interrupt input has, so an open connector records no edge; all four are in
bank 1, which the reference fixes at 3.3 V, and a source with another output level needs a level
translator. The reference input has no I/O timing constraint: it is asynchronous by design and
enters two capture-clock synchroniser stages. Only the I²C loopback variant, which the witness
refuses, uses D8. The output delay of each pin is in the timing report; the pins are not a board result until a programmed board has
passed the cross-check.

## Recorded Libero run

On 2026-11-16, Libero SoC 2026.1.0.17 ran `run_reference.sh` for MPFS250T (FCVG484 package,
STD speed grade, production timing data) on the tree derived at commit `0fea6ea`, whose
`witness_derivation.json` has SHA-256
`1be0dd1e55531a404c3c76adbda41ff43d9538bf96a68faef1c5ea66d0ebb129`. Synthesis,
place-and-route and timing verification ran in the slow_lv_lt, fast_hv_lt and slow_lv_ht
corners. The run exited 0 after 28 minutes and reports that the timing constraints are met.

| Clock | Period | Worst setup slack | Worst hold slack |
| --- | --- | --- | --- |
| FIC0 bus clock, reference CCC output 0 | 8 ns | +3.071 ns | +0.040 ns |
| FIC1 clock, reference CCC output 1 | 8 ns | +2.508 ns | +0.068 ns |
| FIC3 clock, reference CCC output 3 | 20 ns | +3.110 ns | +0.017 ns |
| Witness capture clock, `WITNESS_CCC` output 0 | 10 ns | +2.152 ns | +0.069 ns |

The witness clock's worst setup path lies inside the capture clock, from the cycle state to a
plant velocity product. No path between the bus clock and the capture clock, in either
direction, is among the 1000 worst setup paths, which end at +3.138 ns. The run at `f4bd98f`
missed the capture clock by 2.419 ns in the plant model and the reference generator, where a
32×32-bit product took most of the cycle. The plant and the reference now register four half
products one edge ahead, and the capture queue selects its records from a register copy of
the head ([plant witness](../../docs/PLANT_WITNESS.md#fixed-point-plant)). A later run missed
the 8 ns crossing bound by 0.051 ns, from the bus-held request through the capture domain's
register decode; the request bridge now registers the held request in the capture clock
before any decode. Timing constraint coverage is 99.97 %.

The synthesis CDC check lists 12 witness crossings, none fed through logic. Three are safe:
the bank-ready and reset-permission registers and the interrupt generation's Gray code. Two
are FIFO RAM reads that it does not analyse. It flags seven: the held request and the held
response, each a single register-to-register crossing whose enable the check does not trace
to the handshake; and, as divergent synchroniser inputs, the request and acknowledge toggles,
the two FIFO Gray pointers and the capture quiescence register. Its flags are structural; the
timing of each crossing is bounded by the derived constraints above, and the report meets
them. The whole design uses 27 502 4LUT (10.8 %), 20 700 DFF (8.1 %), 104 uSRAM, 127 LSRAM
and 20 math blocks.

This run and the engineering-sample run below predate the [event mirror pins](#event-mirror-pins)
and the two-page register map, which change the derived RTL, connection script, constraints and
interconnect.

The reports stay with the run; their SHA-256 values are:

| Report | SHA-256 |
| --- | --- |
| `designer/…/BASE_DESIGN_9C34320F91E8E8A144_max_timing_multi_corner.xml` | `2ee7435f6a164c7f3f0b7ec517b93d68584e9d247eaa1f110939a60dd398ccc6` |
| `designer/…/BASE_DESIGN_9C34320F91E8E8A144_min_timing_multi_corner.xml` | `6e22d11f2e9c066f8ce8668c90afd19d10f10cae217b52d93e4db79eb864ed76` |
| `designer/…/BASE_DESIGN_9C34320F91E8E8A144_timing_constraints_coverage.xml` | `11043d1786af566f259a812b170298ce775c6b115187e29154cb20082e8f26d7` |
| `designer/…/max_report.json` | `d43e0b72b52a16424eb7c0e4e611db6b68c96b58c3e530ad2f06e61d1561d7fa` |
| `synthesis/BASE_DESIGN_9C34320F91E8E8A144_cdc.csv` | `dc98f763f79b40fb9a9f5c48dce57d39166177825e607b442bf87ec037124dff` |
| `designer/…/BASE_DESIGN_9C34320F91E8E8A144_compile_netlist_resources.rpt` | `01045e7ee7692bf38541eaa6782ee0d642b0a6e68576ae40caed24f450798633` |

A vendor timing report is not board evidence: no bitstream was programmed and no board was
measured.

In the pinned reference source, `FIC_0_PERIPHERALS_1:ACLK` takes
`CLOCKS_AND_RESETS:FIC_0_CLK` from the reference CCC's GL0_0 output configured for 125 MHz.
The witness `capture_clock` takes `WITNESS_CCC` output 0, configured for 100 MHz.
These settings identify the intended clock domains; only the timing reports can confirm
their implemented frequencies and paths.

The pinned reference imports `script_support/constraints/fic_clocks.sdc` for synthesis,
place-and-route and timing verification. That file groups the four FIC clocks as
asynchronous; the derivation adds the witness capture clock to the FIC0 group and bounds the
paths between the two clocks, which cover the witness's Gray-pointer FIFO, request/acknowledge
bridge, reset-release and retained-interrupt crossings. Review the generated clock and
[SmartTime constraint-coverage and CDC reports](https://onlinedocs.microchip.com/oxy/GUID-AFCB5DCC-964F-4BE7-AA46-C756FA87ED7B-en-US-15/GUID-194FFBC5-DFC3-4718-9972-687F3B8B5982.html),
constrain the actual implemented CDC paths and check
placement-dependent skew on a programmed board before relying on them. The recorded run is
static timing analysis of one placement; no physical timing has been validated yet.

### Engineering-sample device

On 2026-11-20, Libero SoC 2026.1.0.17 ran `run_reference.sh` for MPFS250T_ES on the same
derived input: the tree derived at commit `fb2ca90`, whose RTL equals that of `0fea6ea`, has the
same `witness_derivation.json` SHA-256,
`1be0dd1e55531a404c3c76adbda41ff43d9538bf96a68faef1c5ea66d0ebb129`. The reports name the FCVG484
package, STD speed grade and production timing data, as for MPFS250T. Synthesis gave the same
resource counts and a byte-identical CDC report. The run exited 0 after 34 minutes and reports
that the timing constraints are met in the three corners, with 99.97 % constraint coverage.

| Clock | Period | Worst setup slack | Worst hold slack |
| --- | --- | --- | --- |
| FIC0 bus clock, reference CCC output 0 | 8 ns | +2.610 ns | +0.029 ns |
| FIC1 clock, reference CCC output 1 | 8 ns | +2.152 ns | +0.067 ns |
| FIC3 clock, reference CCC output 3 | 20 ns | +2.966 ns | +0.059 ns |
| Witness capture clock, `WITNESS_CCC` output 0 | 10 ns | +2.206 ns | +0.071 ns |

The witness clock's worst setup path is the one of the MPFS250T run, from the cycle state to a
plant velocity product. No path between the bus clock and the capture clock is among the 1000
worst setup paths, which end at +2.972 ns. Setup slack is smaller than on MPFS250T for the three
reference clocks and 0.054 ns larger for the capture clock; hold slack stays positive for every
clock. Like the production run, this is static timing analysis of one placement: no
engineering-sample board was programmed or measured.

| Report | SHA-256 |
| --- | --- |
| `designer/…/BASE_DESIGN_ES_9C34320F91E8E8A_max_timing_multi_corner.xml` | `faf01e4d2ed8946c188dc9d57d3eebe53ab926580bd84db41c1b51e3156221d8` |
| `designer/…/BASE_DESIGN_ES_9C34320F91E8E8A_min_timing_multi_corner.xml` | `de7f6bf6c89da3c51d7cadb626d05134f0ef585f9b7b8768ddbbbd12658a3039` |
| `designer/…/BASE_DESIGN_ES_9C34320F91E8E8A_timing_constraints_coverage.xml` | `d1951b98f9893727d59fa6b035cb46a9418d55781da71dc189e0a0248caa1f18` |
| `designer/…/max_report.json` | `5c4e5cb0d40e2c45f90e85a6e8fa4b0266690eba902aebc9eec02d59caaee293` |
| `synthesis/BASE_DESIGN_ES_9C34320F91E8E8A_cdc.csv` | `dc98f763f79b40fb9a9f5c48dce57d39166177825e607b442bf87ec037124dff` |
| `designer/…/BASE_DESIGN_ES_9C34320F91E8E8A_compile_netlist_resources.rpt` | `8052e2662106de2c432dd0bacd69d47964c115f6508f852ca608f37100913969` |
