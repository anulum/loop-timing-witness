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
repository's [`LOOP_TIMING_WITNESS.tcl`](LOOP_TIMING_WITNESS.tcl), and
`witness_derivation.json`. It also contains `witness_rtl/`, an exact copy of the current
production SystemVerilog sources. The manifest hashes the derived vendor files, the connection
script and each copied RTL source. Libero imports this snapshot so later repository edits
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
interconnect gains target slot 2, ending at `0x600200ff`. In
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
  address and 32-bit data, covering the 256-byte AXI4-Lite aperture at `0x60020000`;
- MSS fabric-to-processor interrupt bit 11 for the retained witness interrupt, split out of
  the range 11–58 that the reference ties low;
- a separate CCC, `WITNESS_CCC`, that derives the 100 MHz capture clock from the 50 MHz
  reference clock. The reference CCC uses all four PLL0 outputs (125, 125, 125 and 50 MHz)
  and does not instantiate PLL1, so no reference output is free for the witness. Its lock
  output reaches the witness, which holds both of its clock domains in reset until that PLL
  locks and returns to reset if the lock drops.

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

## Recorded Libero run

On 2026-11-16, Libero SoC 2026.1.0.17 ran `run_reference.sh` for MPFS250T (FCVG484 package,
STD speed grade, production timing data) on the tree derived at commit `bb5c673`, whose
`witness_derivation.json` has SHA-256
`ac6490268c64ae69a37b100016d3c4c95e7f51979002040479156d3eba4932e9`. Synthesis,
place-and-route and timing verification ran in the slow_lv_lt, fast_hv_lt and slow_lv_ht
corners. The run exited 0 after 31 minutes and reports that the timing constraints are met.

| Clock | Period | Worst setup slack | Worst hold slack |
| --- | --- | --- | --- |
| FIC0 bus clock, reference CCC output 0 | 8 ns | +2.870 ns | +0.022 ns |
| FIC1 clock, reference CCC output 1 | 8 ns | +2.605 ns | +0.067 ns |
| FIC3 clock, reference CCC output 3 | 20 ns | +2.995 ns | +0.061 ns |
| Witness capture clock, `WITNESS_CCC` output 0 | 10 ns | +2.360 ns | +0.070 ns |

The witness clock's worst setup path lies inside the capture clock, from a plant velocity
product to its register. No path from the bus clock into the capture clock is among the 1000
worst setup paths, which end at +3.071 ns; the FIC0 figure is a crossing in the other
direction, into a bus-clock synchroniser, inside its 8 ns bound. The run at `f4bd98f` missed
the capture clock by 2.419 ns in the plant model and the reference generator, where a
32×32-bit product took most of the cycle. The plant and the reference now register four half
products one edge ahead, and the capture queue selects its records from a register copy of
the head ([plant witness](../../docs/PLANT_WITNESS.md#fixed-point-plant)). The run of the
previous commit, which added the capture lock reset, missed the 8 ns crossing bound by
0.051 ns, from the bus-held request through the capture domain's register decode; the
request bridge now registers the held request in the capture clock before any decode.
Timing constraint coverage is 99.97 %.

The synthesis CDC check lists 12 witness crossings. Two are safe and two are FIFO RAM reads
that it does not analyse. It flags eight: the held request and the held response, each now a
single register-to-register crossing whose enable the check does not trace to the handshake;
the request and acknowledge toggles and the two Gray pointers, as divergent synchroniser
inputs; and two synchronisers fed through logic, from the capture reset release and from the
run-finished flag. Its flags are structural; the timing of each crossing is bounded by the
derived constraints above, and the report meets them. The whole design uses 27 491 4LUT
(10.8 %), 20 684 DFF (8.1 %), 104 uSRAM, 127 LSRAM and 20 math blocks.

The reports stay with the run; their SHA-256 values are:

| Report | SHA-256 |
| --- | --- |
| `designer/…/BASE_DESIGN_9C34320F91E8E8A144_max_timing_multi_corner.xml` | `756f378e2e088eca2fac6264c0ef4d87b383185d2ccf985d412a457580cbe729` |
| `designer/…/BASE_DESIGN_9C34320F91E8E8A144_min_timing_multi_corner.xml` | `e5329dc325725fc76dcca616dc59bc2a328f90c63590bbb8b4718ca889424bd5` |
| `designer/…/BASE_DESIGN_9C34320F91E8E8A144_timing_constraints_coverage.xml` | `a51b89223ce7c270149c35109db8bfa487a9810600c6e44fc225f2e86a2971bc` |
| `designer/…/max_report.json` | `479143f40dfca1ebb99c530a77d92c65ecdc85329200eb8af9f3e7b7b94f89d2` |
| `synthesis/BASE_DESIGN_9C34320F91E8E8A144_cdc.csv` | `87a2376d259b63e302290bf681367467af92210ebc71b299aa570c91d63838ee` |
| `designer/…/BASE_DESIGN_9C34320F91E8E8A144_compile_netlist_resources.rpt` | `c4785b49b34abef1996efaf9c3a962c0c5a02c96e34d23b8ad952a01d3371e33` |

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
