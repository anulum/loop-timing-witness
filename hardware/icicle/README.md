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
direction, by the 8 ns FIC0 period. That bound covers each crossing: handshake-held
transaction data is read two destination edges after its request toggle, a Gray pointer's
bits keep their skew below one source period, and synchroniser inputs and FIFO RAM reads
have no tighter requirement. Two `set_min_delay -8` lines release the hold check that the
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
  and does not instantiate PLL1, so no reference output is free for the witness.

Each change runs after the base design has generated with every input connected, because
SmartDesign refuses an unconnected input when it generates a component. The reference's
own bus interfaces differ in data and ID widths, and the reference project downgrades those
design-rule findings to warnings; the derivation keeps that setting, and the witness
target's widths are checked from the generation messages instead.

Libero SoC 2026.1 generates this project for MPFS250T. Its core generators need a display:
on a host without one, pass a wrapper that runs Libero under `xvfb-run` as the runner's
Libero executable. A host without internet access sets Libero's vault to the MegaVault of
the release (`change_vault_location`); it holds every core the reference requests. The
witness CCC's lock output is not used. The original board support package must establish the
interrupt's PLIC and device-tree identity before a processor may consume it. Source
derivation and RTL simulation do not qualify a board.

## Recorded Libero run

On 2026-11-15, Libero SoC 2026.1.0.17 ran `run_reference.sh` for MPFS250T (FCVG484 package,
STD speed grade, production timing data) on the tree derived at commit `f4bd98f`, whose
`witness_derivation.json` has SHA-256
`94785d6b7f20a9f71dbb94ce57a8271b1aee528b326c5c0fef5f5a5297f7991f`. Synthesis,
place-and-route and timing verification ran in the slow_lv_lt, fast_hv_lt and slow_lv_ht
corners. The run exited 0 after 35 minutes and reports that the timing constraints are not met.

| Clock | Period | Worst setup slack | Worst hold slack |
| --- | --- | --- | --- |
| FIC0 bus clock, reference CCC output 0 | 8 ns | +1.491 ns | +0.037 ns |
| FIC1 clock, reference CCC output 1 | 8 ns | +1.736 ns | +0.058 ns |
| FIC3 clock, reference CCC output 3 | 20 ns | +2.027 ns | +0.060 ns |
| Witness capture clock, `WITNESS_CCC` output 0 | 10 ns | **−2.419 ns** | +0.068 ns |

The failing setup paths lie in the witness plant model, the reference generator and the paths
from the configuration registers to the reference generator. Each computes a 32×32-bit product,
a wide sum and a saturation in one capture cycle. The documented 100 MHz capture clock is
therefore not met on this part and speed grade; closing it is open work. Timing constraint
coverage is 99.97 %.

The synthesis CDC check lists 50 witness crossings. Two are safe and two are FIFO RAM reads
that it does not analyse. It flags 46, mostly the transaction bridge's handshake-held data and
the Gray-pointer synchronisers. The reference constraint file makes the FIC0 clock asynchronous
to every other clock, so these crossings carry no timing constraint yet; witness-specific CDC
constraints are open work too. The whole design uses 26 515 4LUT (10.4 %), 19 846 DFF (7.8 %),
104 uSRAM, 127 LSRAM and 20 math blocks.

The reports stay with the run; their SHA-256 values are:

| Report | SHA-256 |
| --- | --- |
| `designer/…/BASE_DESIGN_9C34320F91E8E8A144_max_timing_multi_corner.xml` | `6906d4d1ac4d08ce41aa0d7b47373c39cc116e10b8fbc19150dabaf4353318ce` |
| `designer/…/BASE_DESIGN_9C34320F91E8E8A144_min_timing_multi_corner.xml` | `8c762208be63be501246562a1d95fc7c18a0314db997d86522ac271f5702609f` |
| `designer/…/BASE_DESIGN_9C34320F91E8E8A144_timing_constraints_coverage.xml` | `45db8c4e68f61a3a3cde4a515deae88e3eb4183e783ddc8058e6381a3d7a0c45` |
| `designer/…/max_report.json` | `89752023994ebe2a510154f7ba9cebb5fe179ffa9886488be4bcae6be3d720b1` |
| `synthesis/BASE_DESIGN_9C34320F91E8E8A144_cdc.csv` | `482785d3e6991414bf08ed7df48548c9c3b79c6aaead10163d69d417c23bdb1f` |
| `designer/…/BASE_DESIGN_9C34320F91E8E8A144_compile_netlist_resources.rpt` | `0cf8ee7616c63fc8c680fde4da571b6f773b522daf0f22fdd75f1a6e356c1a7d` |

A vendor timing report is not board evidence: no bitstream was programmed and no board was
measured.

In the pinned reference source, `FIC_0_PERIPHERALS_1:ACLK` takes
`CLOCKS_AND_RESETS:FIC_0_CLK` from the reference CCC's GL0_0 output configured for 125 MHz.
The witness `capture_clock` takes `WITNESS_CCC` output 0, configured for 100 MHz.
These settings identify the intended clock domains; only the timing reports can confirm
their implemented frequencies and paths.

The pinned reference imports `script_support/constraints/fic_clocks.sdc` for synthesis,
place-and-route and timing verification. That file groups the four FIC clocks as
asynchronous; it does not name the witness's Gray-pointer FIFO, request/acknowledge
bridge, reset-release or retained-interrupt crossings. Review the generated clock and
[SmartTime constraint-coverage and CDC reports](https://onlinedocs.microchip.com/oxy/GUID-AFCB5DCC-964F-4BE7-AA46-C756FA87ED7B-en-US-15/GUID-194FFBC5-DFC3-4718-9972-687F3B8B5982.html),
constrain the actual implemented CDC paths and check
placement-dependent skew before claiming timing closure. No witness-specific physical
constraint or timing report has been validated yet.
