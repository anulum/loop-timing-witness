// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — separate Linux AMP mailbox and fabric ownership

/** @file amp_uio_device.h
 * separate Linux AMP mailbox and fabric ownership.
 */

#ifndef WITNESS_AMP_UIO_DEVICE_H
#define WITNESS_AMP_UIO_DEVICE_H
#include "uio_device.h"
extern "C" {
#include "../bare_metal/amp_contract.h"
}

namespace witness {
/** Exact named page-aligned physical extent of one selected original UIO resource. */
struct AmpUioMap {
    std::uint32_t index;
    std::uint64_t address, bytes;
    std::string name;
};

/** One exclusive IRQ-free UIO owner for fabric configuration/drain and the reserved mailbox. */
class AmpUioDevice {
    int descriptor = -1;
    void *registers = nullptr, *telemetry = nullptr, *faults = nullptr;
    std::size_t register_bytes = 0, telemetry_bytes = 0, fault_bytes = 0;
    std::uint64_t shared = 0;
    /** Unmap every actual aperture before releasing the sole device descriptor. */
    void close() noexcept;
    /** Unmap the fault page; writing START does this before the store reaches the fabric. */
    void close_fault_page() noexcept;
    /** Refuse unaligned accesses beyond the complete original native mailbox. */
    std::size_t offset(std::uint64_t address) const;

  public:
    /** Verify original named map extents and absence of a Linux-owned controller IRQ; a fault
     * page map, when given, is the page after the fabric's and closes before START. */
    AmpUioDevice(const UioIdentity &identity, const AmpUioMap &fabric, const AmpUioMap &mailbox,
                 const AmpUioMap *fault_map = nullptr);
    /** Release mappings and the advisory lock without acknowledging firmware or its IRQ. */
    ~AmpUioDevice();
    AmpUioDevice(const AmpUioDevice &) = delete;
    AmpUioDevice &operator=(const AmpUioDevice &) = delete;
    /** Observe monotonic host nanoseconds for bounded polling, never fabric timing. */
    std::uint64_t time() const;
    /** Sleep while the independently running dedicated controller retains interrupt ownership. */
    void advance(std::uint64_t nanoseconds);
    /** Read a real full little-endian fabric register word of the run page, or of the fault
     * page while it is mapped. */
    ProtocolReply read(std::uint16_t address);
    /** Permit only host configuration, START, FIFO drain and, before START, the fault
     * schedule; refuse controller writes. */
    ProtocolReply write(std::uint16_t address, std::uint32_t value, std::uint8_t strobes);
    /** Read a firmware-owned slot using ordered aligned mapped-memory loads. */
    std::uint32_t read_memory32(std::uint64_t address);
    /** Write only the consumer cursor or logger readiness/final acknowledgement. */
    void write_memory32(std::uint64_t address, std::uint32_t value);
};
} // namespace witness
/** @var witness::AmpUioMap::index
 * Selected sysfs UIO map index.
 */
/** @var witness::AmpUioMap::address
 * Exact page-aligned physical start address.
 */
/** @var witness::AmpUioMap::bytes
 * Exact mapped physical extent in bytes.
 */
/** @var witness::AmpUioMap::name
 * Expected sysfs map name.
 */

#endif
