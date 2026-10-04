// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — actual architectural RAM and production AXI transport for AMP logging

/** @file spike_amp_transport.h
 * actual architectural RAM and production AXI transport for AMP logging.
 */

#ifndef WITNESS_SPIKE_AMP_TRANSPORT_H
#define WITNESS_SPIKE_AMP_TRANSPORT_H
#include "sim.h"
#include "../rtl/simulation.h"
extern "C" {
#include "../bare_metal/amp_contract.h"
}
#include <array>
#include <cstddef>
#include <stdexcept>

namespace witness {
/** Access a bounded reserved mailbox in actual Spike RAM and the actual production fabric. */
class SpikeAmpTransport {
    Simulation &fabric;
    abstract_mem_t *ram = nullptr;
    std::uint64_t ram_base = 0, shared;

    /** Refuse access outside the bound mailbox before translating to actual RAM offsets. */
    std::uint64_t offset(std::uint64_t address) const {
        if (address < shared || address - shared > sizeof(witness_amp_mailbox) - 4 || address % 4)
            throw std::invalid_argument("AMP memory access outside the reserved mailbox");
        return address - ram_base;
    }

  public:
    /** Bind an entire explicit mailbox to an existing real memory device, without allocating RAM.
     */
    SpikeAmpTransport(const sim_t &simulator, Simulation &model, std::uint64_t mailbox_address)
        : fabric(model), shared(mailbox_address) {
        if (!shared || shared % 8 || shared > UINT64_MAX - sizeof(witness_amp_mailbox))
            throw std::invalid_argument("AMP shared memory address outside bounds");
        for (const auto &entry : simulator.get_bus().get_devices()) {
            auto *candidate = dynamic_cast<abstract_mem_t *>(entry.second);
            if (!candidate || shared < entry.first)
                continue;
            const auto displacement = shared - entry.first;
            if (displacement > candidate->size() ||
                sizeof(witness_amp_mailbox) > candidate->size() - displacement)
                continue;
            ram = candidate;
            ram_base = entry.first;
            break;
        }
        if (!ram)
            throw std::invalid_argument("AMP mailbox does not fit actual simulator RAM");
    }

    /** Decode actual target little-endian bytes through the real RAM load entry. */
    std::uint32_t read_memory32(std::uint64_t address) {
        std::array<std::uint8_t, 4> bytes{};
        if (!ram->load(offset(address), bytes.size(), bytes.data()))
            throw std::runtime_error("actual AMP RAM load refused");
        std::uint32_t result = 0;
        for (unsigned index = 0; index < 4; ++index)
            result |= static_cast<std::uint32_t>(bytes[index]) << (index * 8);
        return result;
    }

    /** Release only consumer-owned fields through the real RAM store entry. */
    void write_memory32(std::uint64_t address, std::uint32_t value) {
        const auto displacement = address >= shared ? address - shared : UINT64_MAX;
        if (displacement != offsetof(witness_amp_mailbox, consumer) &&
            displacement != offsetof(witness_amp_mailbox, logger_status))
            throw std::invalid_argument("AMP logger cannot write firmware-owned memory");
        std::array<std::uint8_t, 4> bytes{};
        for (unsigned index = 0; index < 4; ++index)
            bytes[index] = static_cast<std::uint8_t>(value >> (index * 8));
        if (!ram->store(offset(address), bytes.size(), bytes.data()))
            throw std::runtime_error("actual AMP RAM store refused");
    }

    /** Read the production fabric through actual AXI AR/R channels. */
    Edge read(std::uint8_t address) { return fabric.read(address); }
    /** Write the production fabric through actual AXI AW/W/B channels. */
    Edge write(std::uint8_t address, std::uint32_t value, std::uint8_t strobes) {
        return fabric.write(address, value, strobes);
    }
    /** Observe the original fabric clock model, never host timing or a substituted counter. */
    std::uint64_t time() const { return fabric.time(); }
};
} // namespace witness
#endif
