// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — complete native AMP resource and polling configuration parsing

#include "amp_uio_configuration.h"
#include <fstream>

namespace witness {
AmpUioConfiguration read_amp_uio_configuration(const std::string &path) {
    std::ifstream input(path);
    if (!input)
        throw std::runtime_error("cannot open AMP UIO resource configuration");
    AmpUioConfiguration result{};
    if (!(input >> result.identity.device >> result.identity.name >> result.identity.version))
        throw std::runtime_error("AMP UIO resource identity is incomplete");
    result.fabric.index = static_cast<std::uint32_t>(number(input, UINT32_MAX));
    if (!(input >> result.fabric.name))
        throw std::runtime_error("AMP fabric map name is absent");
    result.fabric.address = number(input, UINT64_MAX);
    result.fabric.bytes = number(input, UINT64_MAX);
    result.mailbox.index = static_cast<std::uint32_t>(number(input, UINT32_MAX));
    if (!(input >> result.mailbox.name))
        throw std::runtime_error("AMP mailbox map name is absent");
    result.mailbox.address = number(input, UINT64_MAX);
    result.mailbox.bytes = number(input, UINT64_MAX);
    result.startup_ns = number(input, UINT64_C(60000000000));
    result.completion_ns = number(input, UINT64_C(86400000000000));
    result.poll_ns = number(input, UINT64_C(1000000));
    end_request(input);
    if (!result.startup_ns || !result.completion_ns || !result.poll_ns ||
        result.poll_ns > result.startup_ns || result.poll_ns > result.completion_ns)
        throw std::runtime_error("AMP polling and lifetime bounds are invalid");
    result.identity.map = result.fabric.index;
    result.identity.physical_address = result.fabric.address;
    return result;
}
} // namespace witness
