// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — separate Linux AMP mailbox and fabric ownership

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
    void *registers = nullptr, *telemetry = nullptr;
    std::size_t register_bytes = 0, telemetry_bytes = 0;
    std::uint64_t shared = 0;
    /** Unmap both actual apertures before releasing the sole device descriptor. */
    void close() noexcept;
    /** Refuse unaligned accesses beyond the complete original native mailbox. */
    std::size_t offset(std::uint64_t address) const;
public:
    /** Verify original named map extents and absence of a Linux-owned controller IRQ. */
    AmpUioDevice(const UioIdentity &identity, const AmpUioMap &fabric, const AmpUioMap &mailbox);
    /** Release mappings and the advisory lock without acknowledging firmware or its IRQ. */
    ~AmpUioDevice();
    AmpUioDevice(const AmpUioDevice &) = delete;
    AmpUioDevice &operator=(const AmpUioDevice &) = delete;
    /** Observe monotonic host nanoseconds for bounded polling, never fabric timing. */
    std::uint64_t time() const;
    /** Sleep while the independently running dedicated controller retains interrupt ownership. */
    void advance(std::uint64_t nanoseconds);
    /** Read a real full little-endian fabric register word. */
    ProtocolReply read(std::uint8_t address);
    /** Permit only host configuration, START and FIFO drain; refuse controller writes. */
    ProtocolReply write(std::uint8_t address, std::uint32_t value, std::uint8_t strobes);
    /** Read a firmware-owned slot using ordered aligned mapped-memory loads. */
    std::uint32_t read_memory32(std::uint64_t address);
    /** Write only the consumer cursor or logger readiness/final acknowledgement. */
    void write_memory32(std::uint64_t address, std::uint32_t value);
};
}
#endif
