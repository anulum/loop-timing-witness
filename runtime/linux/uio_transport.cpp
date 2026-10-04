// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — Linux UIO process transport entry point

#include "uio_device.h"

/** Require explicit UIO identity; never auto-select or bind a hardware device. */
int main(int argc, char **argv) {
    if (argc != 6) {
        std::cerr << "usage: uio_transport uioN name version map physical_address_decimal\n";
        return 1;
    }
    try {
        std::istringstream arguments(std::string(argv[4]) + " " + argv[5]);
        const auto map = witness::number(arguments, std::numeric_limits<std::uint32_t>::max());
        const auto physical = witness::number(arguments, std::numeric_limits<std::uint64_t>::max());
        witness::end_request(arguments);
        witness::UioDevice device(
            {argv[1], argv[2], argv[3], static_cast<std::uint32_t>(map), physical});
        return witness::serve(device);
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
