<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — separate Linux AMP logging interface
-->

# Linux AMP logger

`make run-amp-uio` builds the Linux collector for the dedicated-hart controller. The collector
configures and starts the fabric, drains raw events and consumes firmware-published telemetry.
It does not calculate controller commands or claim, acknowledge or enable the controller IRQ.
Its output is marked `amp_uio_unqualified`; successful software compilation does not establish
physical mapping, cache coherence, HSS/OpenSBI ownership, PMP isolation or board acceptance.

## Startup and ownership

Telemetry ABI 2 contains a 112-byte header and 256 records of 64 bytes: 16,496 bytes in total.
On a fresh dedicated firmware boot, the producer initialises the header and copies its actual
compiled cycle count, period, controller selection, overload work and eleven coefficients into
the header. It publishes ABI 2 only after those writes are ordered. Old ring slots are not read
until the producer publishes them. Boot initialisation precedes Linux ownership of its cursor
and logger-status fields.

The producer waits for logger readiness before checking fabric configuration or arming the IRQ.
Linux requires the fresh initial state, configures the idle fabric and verifies every published
firmware contract word against the original run configuration. Only then does it publish
`LOGGER_READY`. Firmware validates registers and the fresh mailbox, installs its interrupt source
and publishes `ARMED`. The collector starts optional power acquisition before fabric `START`.
After both streams drain and the power worker finishes, it closes raw outputs before publishing
`LOGGER_COMPLETE`. Firmware then uses its selected exit mode. No readiness or completion marker
is written after a rejected startup contract or mailbox ownership check. The header
and run-contract reserved fields must remain zero throughout the run. A nonzero trap cause
or trap value cannot accompany an active or successfully finished firmware status. Telemetry, acquisition
and raw-output failures withhold final acknowledgement. A later original-file custody failure
refuses metadata even if the raw drain and target acknowledgement have already completed.

The UIO adapter requires one actual `uio_pdrv_genirq` device with two explicitly named physical
maps and a device-tree node without `interrupts` or `interrupts-extended`. Linux must not own this
controller's interrupt. It checks the character-device identity, holds an exclusive advisory
lock and repeats map/driver identity checks after mapping. Resource names, addresses, sizes and
zero offsets must match actual sysfs. Fabric mapping is exactly one host page; only its 256-byte
register window is accessible through this adapter. The mailbox mapping is a separate disjoint,
page-aligned reservation containing the entire ABI. Writes are restricted to fabric configuration,
START/reset/drain and the two consumer-owned mailbox fields. There is no `/dev/mem` or file-backed
hardware fallback.

The selected BSP must prove that these mappings and the firmware's shared address refer to the
same physical storage with compatible cache attributes. Fences cannot repair incoherent aliases.
Image admission refuses firmware or telemetry reservations that overlap another declared RAM
node, including a partial alias; it does not establish the runtime cache attributes.
The HSS/Linux boot configuration must assign the dedicated hart exclusively to the machine-mode
firmware and reserve its firmware and mailbox memory from Linux allocation. The mapping adapter
does not establish those deployment facts; use the original selected BSP and boot artifacts.

The original Icicle AMP payload templates in
[Yocto](https://github.com/linux4microchip/meta-mchp/blob/31c91afa5e89875894bf14f50d2eac98873f3d10/meta-mchp-polarfire-soc/meta-mchp-polarfire-soc-bsp/recipes-bsp/u-boot/files/mpfs-icicle-kit-amp/amp.yaml.in)
and [Buildroot](https://github.com/linux4microchip/buildroot-external-microchip/blob/ebdcfd7177ea87b7c65cec1bfcd233b269f2eed8/board/microchip/icicle_amp/config.yaml)
assign Linux harts 1–3 and a machine-mode application hart 4 at `0x91C00000`.
These are vendor demo layouts, not qualified WITNESS deployments. The current ISA test uses
hart 2 and links both C and Rust firmware at `0x80000000`; its mailbox is at `0x80080000`.
Both pinned vendor templates instead assign their machine-mode AMP payload to U54_4 at
`0x91C00000`. Their `skip-opensbi: true` setting starts that payload without OpenSBI on its hart,
so it cannot rely on SBI ECALL services ([HSS payload generator](https://github.com/polarfire-soc/hart-software-services/blob/19c8c0dbc0b37ae3b1197f6e817d2d766ad2af87/tools/hss-payload-generator/README.md)).
The simulator layout cannot be copied into a board image: the pinned vendor common Linux tree
declares `0x80000000`–`0x84000000` as kernel memory, covering both simulated reservations.

The unmodified engineering and production silicon device trees at Linux commit
`7fbe4f69684d19b9038beefbbc1d52bed3c141ab` compile and decode, but do not contain WITNESS
reservations or its fabric device. Their Linux PLIC description disables machine contexts.
Image preparation therefore refuses these trees. Integration requires separate, consistent
firmware and Linux resource descriptions, the generated HSS payload and its embedded OpenSBI
configuration, and the actual reference design. Compiling a vendor Linux tree or assigning a
hart in payload YAML alone does not establish exclusive ownership or coherent shared memory.

## Original resource configuration

Supply one complete whitespace file with these fourteen fields in order:

| Field | Meaning |
| --- | --- |
| `device` | Actual `uioN` basename |
| `name`, `version` | Exact UIO sysfs identity strings |
| `fabric_map`, `fabric_name` | Original map index and exact sysfs map name |
| `fabric_address`, `fabric_bytes` | Original page-aligned physical address and one host page |
| `mailbox_map`, `mailbox_name` | Different original map index and exact sysfs map name |
| `mailbox_address`, `mailbox_bytes` | Complete original reserved physical extent |
| `startup_ns` | Positive firmware-initialisation wait, at most 60 seconds |
| `completion_ns` | Positive overall collector wait, at most 24 hours |
| `poll_ns` | Positive nominal poll interval, at most 1 ms and no longer than a sample interval |

Numbers are unsigned decimal; identities and names are single tokens. Extra or incomplete fields,
overlapping extents, insufficient mailbox capacity and unaligned mappings are refused. Addresses
are supplied from original platform artifacts and actual sysfs; no DDR alias or board address is
inferred. The configuration and resource files are hashed before parsing and checked again before
device configuration and after completion.

```sh
make run-amp-uio
build/run_amp_uio run.conf resources.conf events.bin tracking_raw.csv --metadata metadata.json
```

The run file uses the [native run configuration](HOST_ANALYSIS.md). Outputs are exclusive.
CPU/scheduler/priority options use the same checked Linux policy as `run_uio`. Optional
`--power-config` and `--power-journal` require metadata and explicit separate logger and power
worker CPUs. The existing PAC1934 journal uses actual fabric clock reads from this IRQ-free
adapter; its original IIO identity, rail/shunt mapping and polling checks still apply.

The build accepts the [native and RV64 compiler options](HOST_ANALYSIS.md#linux-native-and-rv64-builds).
The actual host entry and missing-device/resource refusals are exercised without invented sysfs
nodes. Dedicated-hart startup and run-contract matching are executed against production RTL in
[Spike capture](AMP_SIMULATION.md). Successful physical UIO acquisition and IIO power logging
through this adapter, and complete native branch coverage, remain unverified.
