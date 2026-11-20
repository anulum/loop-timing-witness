// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — shared native register process protocol

/** @file process_protocol.h
 * shared native register process protocol.
 */

#ifndef WITNESS_PROCESS_PROTOCOL_H
#define WITNESS_PROCESS_PROTOCOL_H

#include <charconv>
#include "refusal.h"
#include <cstdint>
#include <cstdio>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>

namespace witness {
/** First byte offset of the fault page of register map version 2: the fault kind, target
 * cycle, duration and arm registers lie at offsets 0, 4, 8 and 12 of this page, and register
 * addresses run to 0x1fff. */
constexpr std::uint16_t fault_page = 0x1000;
/** Maximum admitted simulated time advance in nanoseconds per protocol request. */
constexpr std::uint64_t advance_limit = 10000000;
/** Register response and raw word; UIO cannot expose AXI response signals. */
struct ProtocolReply {
    unsigned response;
    std::uint32_t data;
};

/** Reject signs, overflow and suffixes before narrowing protocol integers. */
inline std::uint64_t number(std::istream &input, std::uint64_t maximum) {
    std::string token;
    if (!(input >> token) || token.find_first_not_of("0123456789") != std::string::npos)
        throw witness::RuntimeRefused("invalid unsigned argument");
    std::uint64_t value = 0;
    const auto parsed = std::from_chars(token.data(), token.data() + token.size(), value);
    if (parsed.ec != std::errc{} || parsed.ptr != token.data() + token.size() || value > maximum)
        throw witness::RuntimeRefused("argument outside range");
    return value;
}

/** Validate a complete request before accessing either device. */
inline void end_request(std::istream &input) {
    std::string extra;
    if (input >> extra)
        throw witness::RuntimeRefused("unexpected argument");
}
/** Serve validated requests against either actual MMIO or production RTL. */
template <class Device> int serve(Device &device) {
    std::string line;
    while (std::getline(std::cin, line)) {
        std::istringstream input(line);
        std::string operation;
        input >> operation;
        ProtocolReply result{};
        if (operation == "R") {
            const auto address = number(input, 0x1fff);
            end_request(input);
            const auto reply = device.read(static_cast<std::uint16_t>(address));
            result = {reply.response, reply.data};
        } else if (operation == "W") {
            const auto address = number(input, 0x1fff);
            const auto data = number(input, std::numeric_limits<std::uint32_t>::max());
            const auto strobes = number(input, 15);
            end_request(input);
            const auto reply =
                device.write(static_cast<std::uint16_t>(address), static_cast<std::uint32_t>(data),
                             static_cast<std::uint8_t>(strobes));
            result = {reply.response, reply.data};
            result.data = 0;
        } else if (operation == "T" || operation == "I") {
            const auto duration = number(input, advance_limit);
            end_request(input);
            if (operation == "T")
                device.advance(duration);
            else
                result.data = device.wait_interrupt(duration);
        } else if (operation == "Q") {
            end_request(input);
            return 0;
        } else
            throw witness::RuntimeRefused("unknown request");
        std::cout << result.response << ',' << result.data << ',' << device.time() << std::endl;
        if (!std::cout)
            throw witness::RuntimeRefused("cannot write AXI response");
    }
    // std::cin reads through stdio, which reports a read error as end of file: ferror tells
    // the two apart, so a failed request stream is refused instead of ending as complete.
    if (std::ferror(stdin) || !std::cin.eof())
        throw witness::RuntimeRefused("cannot read AXI request");
    return 0;
}
} // namespace witness
/** @var witness::ProtocolReply::response
 * Actual transport response code; UIO cannot observe AXI response wires.
 */
/** @var witness::ProtocolReply::data
 * Raw 32-bit register word returned by the selected transport.
 */

#endif
