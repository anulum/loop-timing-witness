// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — Linux UIO ownership and ordered register access

#ifndef WITNESS_UIO_DEVICE_H
#define WITNESS_UIO_DEVICE_H

#include "../process_protocol.h"
#include <cstddef>

namespace witness {
/** Owner-supplied identity and physical register address, verified before MMIO. */
struct UioIdentity {
    std::string device, name, version;
    std::uint32_t map;
    std::uint64_t physical_address;
};

/** Exclusive cooperative ownership of one generic platform UIO aperture. */
class UioDevice {
    int descriptor = -1;
    void *mapping = nullptr;
    std::size_t mapping_size = 0;
    std::size_t register_offset = 0;
    std::uint32_t interrupt_count = 0;
    bool irq_managed = false;

    /** Disable this owned IRQ, unmap and close; safe on failed construction. */
    void close() noexcept;
    /** Send one native-endian signed 32-bit generic UIO IRQ control value. */
    void irq_control(std::int32_t enabled);

public:
    /** Verify sysfs, generic driver and character-device identity before mapping. */
    explicit UioDevice(const UioIdentity &identity);
    /** Release ownership without resetting an active hardware run. */
    ~UioDevice();
    UioDevice(const UioDevice &) = delete;
    UioDevice &operator=(const UioDevice &) = delete;

    /** Absolute CLOCK_MONOTONIC nanoseconds; never fabric capture ticks. */
    std::uint64_t time() const;
    /** Perform exactly one ordered aligned little-endian volatile 32-bit load. */
    ProtocolReply read(std::uint8_t address);
    /** Full-word ordered store; refuse partial strobes before any MMIO access. */
    ProtocolReply write(std::uint8_t address, std::uint32_t data, std::uint8_t strobes);
    /** Sleep for a requested duration while physical fabric continues running. */
    void advance(std::uint64_t nanoseconds);
    /** Re-enable generic IRQ, wait with nanosecond timeout and read its 4-byte count. */
    bool wait_interrupt(std::uint64_t nanoseconds);
    /** Last actual cumulative UIO interrupt counter, separate from RTL generation. */
    std::uint32_t last_interrupt_count() const { return interrupt_count; }
};
} // namespace witness
#endif
