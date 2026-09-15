<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — architecture summary
-->

# Architecture summary

Loop Timing Witness is a measurement instrument for real-time control loops and fabric
accelerators on PolarFire SoC. The repository is `architecture_only`: the architecture below is
planned, and no fabric logic, processor software or host analysis code exists yet.

The authoritative architecture record is [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md); the
boundary decision is [`docs/adr/0001-repository-boundary.md`](docs/adr/0001-repository-boundary.md).

In one paragraph: a free-running 64-bit counter in FPGA fabric is the only clock of the
measurement. Strobes from a controller input/output register (or, in the `COMPUTE` profile, from
a generic accelerator slot) capture event type, cycle number and counter value into a fabric
buffer that Linux drains into little-endian 16-byte records. A fixed-point plant emulator closes
the loop; a deadline and safe-state monitor and a fault injector act on the same timebase. The
controller runs in one of three placements — Linux user space, a bare-metal core, or fabric
logic — selected by a register, so the witness logic never changes between placements. A Linux
run controller pairs power-monitor samples with counter reads and writes each run as raw event
and power files plus a manifest of every hash and version. A host analysis tool validates the
manifest and derives the latency, deadline, control-quality, energy and fault statistics.
