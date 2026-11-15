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
checkout to be clean and verifies the two vendor source files it changes by SHA-256.
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
read boundaries for edited vendor Tcl, copied RTL and the unmodified reference remainder.
Each change must abort publication. A separate filesystem race creates the requested
destination immediately before publication; derivation must preserve that competing tree.

The derived tree contains the official reference plus narrowly changed Tcl sources, this
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

The derivation changes two vendor Tcl files. The reference script sources the witness
script once the base design has generated, and FIC0's interconnect gains target slot 2,
ending at `0x600200ff`. The witness script adds the rest to the generated design:

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
witness CCC's lock output is not used. Synthesis, place-and-route, timing and the CDC
review remain to be qualified. The original board support package must establish the
interrupt's PLIC and device-tree identity before a processor may consume it. Source
derivation and RTL simulation do not qualify a board.

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
